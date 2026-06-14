# Consola de Operaciones Transaccionales

Back-office bancario en miniatura: un operador revisa transacciones, filtra y
pagina sobre cientos de miles de registros, ve el detalle con su auditoría, y
ejecuta acciones controladas (aprobar / rechazar / revertir) bajo una máquina
de estados, segregación de funciones (maker-checker), idempotencia y bloqueo
optimista.

> **Encuadre honesto:** demostración técnica de los patrones del dominio
> transaccional (banca/retail), no experiencia bancaria de producción.

## Demo en vivo

🔗 **<https://traconsole.duckdns.org>** · entorno demo, datos ficticios; se re-siembra
periódicamente.

Entra con `supervisor1` / `Demo1234!` y aprueba una transacción en revisión, o explora
como `operador1` / `auditor1`. Desplegada en una VM GCP e2-standard-2 (2 vCPU/8GB) con
`docker-compose`, detrás de Caddy (TLS automático). Misma imagen que corre en CI y kind.

## Arquitectura

```
Navegador
        │  (mismo origen: el SPA y el API salen del gateway, sin CORS)
        ▼
Edge / Gateway Nginx :8080  ──  sirve el SPA Angular 21 en /  ·  rate limiting
        │                       proxea /api/* → servicios (reescribe a los paths
        │                       del contrato)  ·  única puerta de entrada
        ├──► transactions (FastAPI)  ──► MongoDB (replica set 1 nodo)
        │         router → servicio → repositorio        │
        │                                                └─ auditoría append-only
        ├──► auth (FastAPI: JWT RS256, RBAC)  ──► MongoDB (base auth_db separada)
        │
        └──  Redis: idempotencia (SET NX), rate limit, cache de agregados
```

Empaquetado en dos formas: **Docker Compose** (dev) y **Kubernetes** (`infra/k8s`,
sobre kind/minikube) — `kubectl apply` levanta el stack completo con probes y las
claves RS256 como Secret fuera del código.

**Contract-first:** [contracts/openapi.yaml](contracts/openapi.yaml) es la
fuente de verdad. El cliente Angular se **genera** desde el contrato
(`npm run generate:api`) y un **candado anti-drift** en CI
([infra/ci/check_drift.py](infra/ci/check_drift.py)) compara el OpenAPI que
FastAPI emite en runtime contra el contrato — el build falla si divergen.

## Correr el proyecto

Requisitos: Docker (con Compose), Node 20+, [uv](https://docs.astral.sh/uv/).

```bash
make keys    # par RS256 local (solo auth recibe la privada) — una vez
make up      # gateway + transactions + auth + Mongo (replica set) + Redis
make seed    # 500k transacciones con distribuciones realistas (~1 min)
make front   # http://localhost:4200  (antes: cd frontend && npm ci)
make help    # todos los comandos (tests, drift, regenerar cliente…)
```

Usuarios demo (contraseña `Demo1234!`): `operador1`, `supervisor1`, `auditor1`.

Verificación rápida (el API cuelga de `/api` en el gateway):
`curl http://localhost:8080/api/health` y
`curl 'http://localhost:8080/api/transactions?limit=3'`.

### Sobre Kubernetes (kind)

```bash
make k8s-tools   # instala kind + kubectl en ~/.local/bin (sin sudo) — una vez
make k8s-up      # construye imágenes, crea el cluster y despliega el stack
kubectl -n consola port-forward svc/edge 8080:8080   # consola en :8080
make k8s-down    # borra el cluster
```

### Fuzzing del contrato (Schemathesis)

```bash
make schemathesis   # property-based testing autenticado contra auth + transactions
```

Hace login real e inyecta el bearer en cada request generado (sin el hook sería un
paso verde que solo recibe 401). Cazó dos bugs reales en Fase 6 — ver
[problemas-resueltos](docs/problemas-resueltos.md) #29 y #30.

## Decisiones de diseño (las que valen en entrevista)

Cada decisión como *qué elegí y por qué no la alternativa obvia*.

- **Mongo en replica set de un nodo desde el día uno:** standalone rechaza las
  transacciones multi-documento en *runtime*; sin esto la atomicidad
  estado + auditoría de la Fase 4 no existe.
- **Máquina de estados como datos, no `if/else`:** las transiciones válidas son un
  diccionario `(estado, acción) → estado`. Un test exhaustivo recorre las 20
  combinaciones (5 estados × 4 acciones) en un loop —no 20 tests que dejan huecos—;
  un `if/else` regado por los handlers no es testeable así ni se audita de un vistazo.
- **Idempotencia con `SET NX` atómico, no GET-luego-SET:** la idempotency-key se reclama
  con un único `SET NX` (test-and-set atómico); dos requests simultáneos con la misma
  clave → solo uno ejecuta la mutación, el otro recibe el resultado original. Un
  GET-luego-SET tiene una ventana de carrera. Fail-closed: sin Redis NO se muta (503).
- **Cursor compuesto (`createdAt` + `_id`), no offset ni cursor simple:**
  `OFFSET 400000` recorre 400k filas para descartarlas; un cursor sobre un solo
  campo con timestamps duplicados salta o repite filas.
- **Candado anti-drift con normalización propia:** el contrato es OpenAPI 3.0.3
  (`nullable:`) y FastAPI emite 3.1 (`anyOf: [..., null]`); el checker
  canonicaliza ambos estilos y compara la estructura path por path.
- **Cliente generado envuelto en una capa de servicios propia:** los
  componentes nunca tocan el cliente generado; las regeneraciones del contrato
  no se propagan por la app.
- **Filtros en la URL, no en memoria:** deep-linkeables y el botón atrás
  funciona. El cursor de paginación es estado efímero y queda fuera.
- **Sin cache de listados:** con índices ESR correctos sobre 500k documentos no
  hace falta, y la invalidación con filtros combinables no tiene solución
  elegante. Redis gana su lugar con idempotencia y rate limiting.
- **Búsqueda de contraparte por prefijo, no substring:** el prefijo anclado
  sobre un campo normalizado (`searchKeys`, índice multikey) usa índice; un
  substring a volumen sería COLLSCAN siempre (full-text descartado en v1).
- **Dashboard sin `$facet` (medido, no asumido):** sobre 500k, `$facet` tardó
  69s (materializa todo en memoria, sin índices) vs 1.2s con dos `$group`
  separados en paralelo. "Una sola pasada" suena eficiente pero es 55× peor
  aquí; `$facet` sirve tras un `$match` selectivo, no para barrer la colección.
- **JWT RS256:** solo `auth` posee la clave privada; `transactions` y el
  gateway verifican con la pública — ningún otro servicio puede emitir tokens.
- **Rotación de refresh tokens con detección de reuso:** cada refresh emite un
  par nuevo y revoca el anterior atómicamente; un refresh ya usado que vuelve a
  aparecer es señal de robo y quema la familia completa de la sesión.
- **Tokens en localStorage:** tradeoff consciente de demo; un banco real usaría
  cookies httpOnly tras un BFF. El interceptor comparte el refresh en vuelo
  para que N requests con 401 simultáneos no quemen la familia.
- **Sin blacklist de access tokens en Redis (descarte deliberado):** con access
  de 15 minutos, logout server-side que revoca la familia de refresh y
  detección de reuso, la ventana de exposición de un access robado es ≤15 min.
  Una blacklist consultada en cada request agrega estado compartido y latencia
  a todos los servicios para cubrir solo esa ventana — costo desproporcionado
  aquí. Si el requisito fuera revocación inmediata (v2), este es el punto de
  entrada documentado.

- **SPA + API en el mismo origen tras el gateway (sin CORS):** el edge sirve el SPA
  y proxea el API bajo `/api` (reescrito a los paths del contrato). Las rutas de
  cliente de Angular chocaban con los paths del API en la raíz; el prefijo `/api` lo
  resuelve **sin tocar el contrato** — el backend sigue en `/transactions` y el
  candado anti-drift no se entera.
- **Schemathesis autenticado, no decorativo:** un fuzzer de contrato que recibe 401
  en todo no prueba nada. Un auth provider hace login real e inyecta el bearer en cada
  request; corre directo contra cada app (el rate-limit del gateway ahogaría al
  fuzzer). Encontró dos respuestas fuera del esquema del contrato (cuerpo ilegible,
  byte nulo en un filtro→regex) que ya se corrigieron.
- **Bases Mongo separadas por servicio:** `auth_db` y `transactions_db` — tres
  servicios sobre una instancia compartida es el anti-patrón de monolito distribuido.
- **Kubernetes con secrets fuera del código:** `kubectl apply` levanta el stack
  (StatefulSet de Mongo con init de replica set, probes de readiness/liveness); las
  claves RS256 se inyectan como Secret montado, nunca en git ni en una imagen.

### Qué cambiaría a escala real (lectura honesta)

Este sistema opera 500k documentos (~1GB, cabe en RAM) con un operador. Un
core bancario real maneja miles de millones de filas y ~10.000 sesiones
concurrentes — 3 y 4 órdenes de magnitud más. A esa escala aparecen piezas
que aquí no existen: particionamiento caliente/frío (la consola opera sobre
90 días; lo histórico vive en otro tier), búsqueda en motor dedicado
alimentado por CDC (nunca regex contra el store transaccional), réplicas de
lectura/CQRS y agregados materializados. **Lo que no cambia son los
patrones**: cursor compuesto (no offset), conteo estimado (no exacto),
búsqueda por prefijo acotado, `maxTimeMS` con fallo rápido accionable,
idempotencia y auditoría atómica — son los mismos a cualquier escala; lo que
se reemplaza alrededor es infraestructura. Un diseño basado en
`OFFSET`/`COUNT(*)`/substring sí se tira entero al crecer.

## Rendimiento sobre 500k (k6)

Números **con su entorno** (sin entorno son marketing). El camino caliente es el listado
filtrado por estado + orden por fecha (índice ESR) con paginación por cursor —la query
dominante del operador— medido directo contra el backend para aislar la capacidad del
servicio del rate-limit del edge.

**Entorno:** 500.000 documentos · VM GCP **e2-standard-2 (2 vCPU / 8 GB)**, Mongo en el
mismo host · k6 con **25 VUs**, ~1:45 min (login una vez → listado filtrado → 2ª página
por cursor) · **directo al backend** (sin el rate-limit de 20 r/s del edge).

| Métrica | Valor |
|---|---|
| Latencia **p95** | **26 ms** |
| Latencia p50 / p90 | 7.5 ms / 17 ms |
| Errores | **0.00 %** (0 de 4.075 requests) |
| Checks | 100 % (login + listado + paginación) |
| Throughput | 38,5 req/s |

p95 de **26 ms sobre medio millón de filas** confirma que los índices ESR + el cursor
compuesto hacen su trabajo: la query dominante no degrada a volumen. El throughput está
acotado por el think-time del test (25 VUs, `sleep(1)`), no por el servicio — con p95
estable y 0 errores hay holgura de sobra.

## Pruebas y CI

`make test` (ruff+pytest backend, eslint+vitest+build frontend), `make drift`
(candado de contrato), `make schemathesis` (fuzzing autenticado), `make e2e`
(Playwright: login→listado→filtro→detalle→transición contra la imagen edge), `make load`
(k6). Todo corre en GitHub Actions en cada push.

Plan completo de fases: [docs/plan-consola-transaccional-sonda.md](docs/plan-consola-transaccional-sonda.md).
Registro de problemas → causa → solución: [docs/problemas-resueltos.md](docs/problemas-resueltos.md).

## Estado

- [x] **Fase 0 — Fundación, contrato y rebanada vertical:** contrato OpenAPI,
  servicio `transactions` (listado con cursor compuesto + filtros, detalle,
  auditoría), Mongo replica set + Redis + gateway en Compose, cliente Angular
  generado, consola con filtros en URL, CI con candado anti-drift.
- [x] **Fase 1 — Volumen:** seed 500k en ~64s, índices ESR (+ monto sin filtro),
  test de `explain()` que falla con COLLSCAN o SORT en memoria — corre en CI
  contra un Mongo replica set real; listado filtrado responde en ~10ms
- [x] **Fase 2 — Auth y desarrollo seguro:** JWT RS256 (solo `auth` firma),
  argon2id, rotación de refresh con detección de reuso (familia revocada),
  RBAC como dependency (`require_role`), rechazo a nivel de API testeado,
  rate limit estricto en login (429 verificado), login + interceptor con
  refresh automático compartido + guard en Angular; base `auth_db` separada
- [x] **Fase 3 — Consola completa:** barra de filtros íntegra en la URL
  (estado, tipo, moneda, montos, fechas, contraparte con debounce, orden) —
  deep-linkeable y con botón atrás; vista de detalle con historial de
  auditoría; errores del API mapeados a mensajes de operador (toasts
  ng-bootstrap); 16 tests de frontend
- [x] **Fase 4 — Flujo transaccional (el corazón):** máquina de estados como
  datos con test exhaustivo (loop 5 estados × 4 acciones); maker-checker
  validado contra el actor del token; idempotencia con `SET NX` atómico
  (reintento devuelve el resultado original; concurrencia → una sola
  ejecución); bloqueo optimista (`409 STALE_VERSION`); estado + auditoría en
  UNA transacción Mongo — un crash simulado entre escrituras no deja
  inconsistencia; acciones de supervisor en la consola con manejo de 409
- [x] **Fase 5 — Dashboard y métricas:** KPIs (total, tasa de aprobación, en
  revisión) + gráficos (Chart.js) de volumen por estado y por mes; rollups con
  cache Redis (TTL 30s, header `X-Cache`: MISS 0.9s → HIT 0.07s). **Medimos y
  descartamos `$facet`**: 69s vs 1.2s con `$group` separados sobre 500k (ver
  decisión abajo). "Mi actividad": acciones por actor leídas de la auditoría
- [x] **Fase 6 — DevOps y observabilidad:** Schemathesis autenticado en CI
  (auth provider con login real; cazó y se corrigieron 2 respuestas fuera del
  esquema del contrato); SPA + API en el mismo origen tras el gateway (API bajo
  `/api`, sin CORS); **Kubernetes** sobre kind (`kubectl apply` levanta el stack:
  StatefulSet de Mongo con init de replica set, probes, claves RS256 como Secret);
  un correlation ID atraviesa edge→auth→transactions en los logs; bases `auth_db` y
  `transactions_db` separadas — verificado en vivo
- [x] **Fase 7 — Pulido, pruebas y narrativa:** e2e Playwright (login→listado→filtro→
  detalle→transición) contra la imagen edge en CI; load test k6 (p95 26 ms sobre 500k);
  README como narrativa de decisiones; **demo pública en vivo** en GCP (VM e2-standard-2
  + docker-compose, Caddy/TLS automático sobre DuckDNS, datastores cerrados, reseed
  periódico) — <https://traconsole.duckdns.org>
