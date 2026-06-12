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
make up      # gateway + transactions + Mongo (replica set) + Redis
make seed    # 500k transacciones con distribuciones realistas (~1 min)
make front   # http://localhost:4200  (antes: cd frontend && npm ci)
make help    # todos los comandos (tests, drift, regenerar cliente…)
```

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
- **JWT RS256 (Fase 2):** solo `auth` posee la clave privada; ningún otro
  servicio puede emitir tokens.

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
- [ ] Fase 2 — Auth: JWT RS256, RBAC, rotación de refresh tokens
- [ ] Fase 3 — Consola completa: todos los filtros, detalle, errores mapeados
- [ ] Fase 4 — Flujo transaccional: máquina de estados, maker-checker,
  idempotencia, bloqueo optimista, auditoría atómica
- [ ] Fase 5 — Dashboard con `$facet` + cache Redis TTL
- [ ] Fase 6 — K8s, Schemathesis con auth, logs estructurados + correlation ID
- [ ] Fase 7 — Playwright, k6, narrativa completa
