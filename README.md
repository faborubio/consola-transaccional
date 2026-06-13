# Consola de Operaciones Transaccionales

Back-office bancario en miniatura: un operador revisa transacciones, filtra y
pagina sobre cientos de miles de registros, ve el detalle con su auditoría, y
ejecuta acciones controladas (aprobar / rechazar / revertir) bajo una máquina
de estados, segregación de funciones (maker-checker), idempotencia y bloqueo
optimista.

> **Encuadre honesto:** demostración técnica de los patrones del dominio
> transaccional (banca/retail), no experiencia bancaria de producción.

## Arquitectura

```
Angular 21 (Bootstrap, cliente TS generado del contrato)
        │
        ▼
Gateway Nginx :8080  ──  CORS, rate limiting, única puerta de entrada
        │
        ├──► transactions (FastAPI)  ──► MongoDB (replica set 1 nodo)
        │         router → servicio → repositorio        │
        │                                                └─ auditoría append-only
        ├──► auth (FastAPI, Fase 2: JWT RS256, RBAC)
        │
        └──  Redis: idempotencia (SET NX), rate limit, cache de agregados
```

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

Verificación rápida: `curl http://localhost:8080/health` y
`curl 'http://localhost:8080/transactions?limit=3'`.

## Decisiones de diseño (resumen — se expande en Fase 7)

- **Mongo en replica set de un nodo desde el día uno:** standalone rechaza las
  transacciones multi-documento en *runtime*; sin esto la atomicidad
  estado + auditoría de la Fase 4 no existe.
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
- [ ] Fase 5 — Dashboard con `$facet` + cache Redis TTL
- [ ] Fase 6 — K8s, Schemathesis con auth, logs estructurados + correlation ID
- [ ] Fase 7 — Playwright, k6, narrativa completa
