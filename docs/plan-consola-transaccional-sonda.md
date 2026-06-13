# Plan: Consola de Operaciones Transaccionales (Angular + Microservicios Python)

> Proyecto de portafolio #2 — orientado a la oferta de **Desarrollador Angular en SONDA** (sistemas transaccionales, alto volumen, banca/retail). Complementa al Grafo de Conocimiento: aquel cubre el eje IA/datos; este cubre el eje **transaccional serio + disciplina de empresa grande**, que es justo lo que SONDA evalúa.
>
> **Archivo acompañante:** `openapi.yaml` — el contrato completo de la API (OpenAPI 3.0.3), ya construido. Ver Fase 0 para su detalle y decisiones de diseño.

## Contexto y objetivo

La oferta de SONDA repite dos veces su núcleo: *"procesos complejos, transaccionales, con altos volúmenes de información, tipo banca o retail"*. Todo el resto (Angular, REST/JSON, Bootstrap, Python, microservicios, OpenAPI, Docker/K8s, CI/CD, NoSQL, desarrollo seguro) son los **medios** con que esperan que lo construyas. Este proyecto es ese sistema en miniatura, hecho con los patrones reales del mundo bancario.

**Dominio elegido:** un **back-office bancario / consola de operaciones** — el panel interno donde un operador revisa transacciones, las filtra y pagina sobre cientos de miles de registros, ve el detalle, y ejecuta acciones controladas (aprobar, rechazar, marcar para revisión, revertir) bajo una máquina de estados y controles de seguridad. Es deliberadamente *aburrido y profesional*: ese es exactamente el mensaje ("puedo operar en tu mundo").

**Qué demuestra (señal para SONDA):** contract-first con OpenAPI, frontend Angular consumiendo microservicios, paginación/filtrado server-side a volumen real, máquina de estados transaccional con auditoría, control maker-checker (segregación de funciones), idempotencia, JWT/RBAC, contenedorización y CI/CD. No "sé Angular" sino "construí un sistema transaccional como los que ustedes hacen".

**Encuadre honesto:** el proyecto demuestra que *puedo* trabajar en este dominio con sus patrones, no que ya lo hice en producción para un banco. Se presenta como demostración técnica, no como experiencia bancaria inventada.

## Mapeo oferta → proyecto (la tabla que se vuelve argumento en entrevista)

| Requisito SONDA | Cómo lo cubre el proyecto |
|---|---|
| Desarrollador **Angular** | Frontend principal en Angular (se prioriza sobre Vue porque el título lo nombra). |
| HTML5/CSS + **Bootstrap** | UI con Bootstrap (ng-bootstrap) — estándar en banca/retail; no es el momento de lucir Tailwind. |
| **REST/JSON** | API REST con contratos JSON tipados de punta a punta. |
| **OpenAPI 3.0** | Contrato OpenAPI **primero** (contract-first); cliente TS de Angular **generado** desde el contrato. |
| **Python** + microservicios + POO | Backend FastAPI en 2-3 microservicios (transacciones, auth, notificaciones), POO + capas. |
| **Altos volúmenes** | Seed de 300k-500k transacciones; paginación, filtro y búsqueda **server-side** con índices. |
| **NoSQL** | MongoDB para el store de transacciones + log de auditoría; Redis para cache/sesiones/idempotencia. |
| **Docker/Kubernetes** | Docker Compose para todo; manifiestos K8s para correr en kind/minikube local. |
| **CI/CD** | GitHub Actions: lint + tests + build de imágenes (+ push opcional). |
| **Desarrollo seguro** | JWT, RBAC, segregación de funciones (maker-checker), validación en backend, rate limiting. |
| *springbatch* (equivalente) | **Conciliación batch** (Fase 8): job nocturno que ingiere una cartola CSV y la concilia contra las transacciones. |

> Requisitos como **Cloudera Hadoop, GWT, Pro*C, JBoss, Ant, XSLT** son "nice to have" legacy de clientes específicos. **No se cubren** — nadie espera que un postulante los tenga todos. Foco en el núcleo que se repite.

## Decisiones de stack

- **Frontend:** Angular (última LTS estable, standalone components, TypeScript en modo estricto), RxJS para flujos async con `async pipe` y `takeUntilDestroyed` obligatorios (sin suscripciones sin liberar), ng-bootstrap para UI, Angular Router con lazy loading. **Sin NgRx** — signals + servicios alcanzan para este alcance; NgRx aquí es sobre-ingeniería. **Estado de filtros en la URL** (query params), no en memoria. Runner de tests: **Jest o Vitest** desde el día uno (Karma está deprecado).
- **Cliente API:** generado desde el contrato OpenAPI con `openapi-generator` (typescript-angular). **Nunca se usa directamente en componentes** — se envuelve en una capa de servicios propios; eso aisla al frontend de las regeneraciones. No se edita a mano.
- **Backend:** Python + **FastAPI** (genera su propio OpenAPI desde el código; ver candado anti-drift en Fase 0). POO + arquitectura por capas (router → servicio → repositorio).
- **Microservicios v1: solo dos** — `transactions` (núcleo) y `auth`. `notifications` se elimina de v1: es decorativo sin el outbox que lo justifica, y un servicio decorativo es un pasivo en entrevista. Nace en Fase 8 junto con el patrón que le da razón de existir. Un **gateway delgado (Nginx o Traefik)** como única puerta de entrada: routing, CORS y rate limiting centralizados.
- **Datos:** **MongoDB en modo replica set de un nodo** (`--replSet rs0`) — obligatorio para transacciones multi-documento (estado + auditoría + outbox en una operación atómica). Mongo standalone no soporta transacciones. **Redis** para claves de idempotencia (SET NX atómico), rate limiting y blacklist de JWT. **Sin cache de listados** — con índices compuestos correctos sobre 500k documentos no se necesita, y su invalidación con filtros combinables es un problema combinatorio sin solución elegante. El cache va solo en agregados del dashboard (Fase 5).
- **JWT: firma asimétrica RS256**, no secreto HMAC compartido. Con RS256 solo `auth` firma con la clave privada; `transactions` y el gateway verifican con la pública — ningún servicio puede emitir tokens. Con HMAC cualquier servicio que conozca el secreto puede firmar. Una línea de configuración, señal de diseño mayor.
- **Infra local:** Docker Compose levanta todo (servicios + Mongo replica set + Redis). Manifiestos K8s (Deployment/Service/ConfigMap) para demostrar el patrón en kind/minikube.
- **CI/CD:** GitHub Actions — lint (ruff/eslint), tests (pytest + Jest/Vitest), build de imágenes Docker, **Schemathesis con hook de autenticación** (ver Fase 6), **candado anti-drift** de contratos (ver Fase 0).
- **Observabilidad:** logs estructurados (JSON) en cada servicio + **correlation ID** generado en el interceptor de Angular y propagado por header a través del gateway y los microservicios.
- **Despliegue demo:** frontend en Vercel/Netlify; backend + Mongo + Redis en un VPS con Docker Compose, o servicios gestionados (Mongo Atlas free, Upstash Redis free, Render/Railway para los servicios).

## Estructura del repositorio (monorepo)

```
/contracts
  openapi.yaml          # CONTRATO PRIMERO — fuente de verdad de la API
/services
  /transactions         # FastAPI: núcleo transaccional
    /app
      /api              # routers REST
      /domain           # modelos de dominio, máquina de estados como datos (dict, no if/else)
      /repository       # acceso a Mongo (sesiones transaccionales)
      /services         # lógica: idempotencia (SET NX), transiciones, auditoría
      main.py
    Dockerfile
    /tests
  /auth                 # FastAPI: usuarios, roles, JWT RS256
    /app
      /api
      /domain
      /repository
      /services         # hashing argon2, rotación de refresh tokens
      main.py
    Dockerfile
    /tests
  # notifications → v2 (Fase 8), nace con el outbox que lo justifica
/frontend
  /src/app
    /core               # interceptores HTTP (JWT + correlation ID), guards de ruta
    /api-client         # cliente GENERADO — no editar; envuelto por /services
    /services           # capa propia sobre el cliente generado (aísla regeneraciones)
    /features
      /transactions     # listado server-side, filtros en URL, detalle, acciones
      /dashboard        # métricas con cache Redis
      /auth             # login
    /shared             # componentes Bootstrap reutilizables
/infra
  docker-compose.yml    # gateway + servicios + Mongo (replica set) + Redis
  /gateway              # Nginx/Traefik: routing, CORS, rate limiting
  /mongo-init           # script rs.initiate() para levantar replica set de 1 nodo
  /k8s                  # manifiestos para kind/minikube
  /seed                 # script Faker: 300k-500k transacciones (insert_many por lotes)
.github/workflows       # CI/CD (lint, tests, build, anti-drift, Schemathesis)
README.md               # diagrama de arquitectura + narrativa de decisiones
```

## Fases de construcción

### Fase 0 — Fundación, contrato y rebanada vertical

**Regla de construcción de todo el proyecto:** no construir por capas horizontales ("todo el backend, luego todo el front"). La primera semana cierra una **rebanada vertical completa**: `GET /transactions` de punta a punta — contrato → FastAPI → Mongo → cliente generado → servicio Angular → componente → render en browser. Feo está bien; el objetivo es validar toda la tubería antes de invertir en cada capa. Cada fase siguiente repite el patrón sobre terreno ya probado.

- Monorepo scaffold (servicios FastAPI vacíos + app Angular, TypeScript estricto, Jest/Vitest configurado desde el día uno — Karma está deprecado).
- **MongoDB en modo replica set de un nodo:** Docker Compose levanta Mongo con `--replSet rs0` + script `/infra/mongo-init` que ejecuta `rs.initiate()`. **Sin esto las transacciones multi-documento no existen** — Mongo standalone las rechaza en runtime, no en compilación, y el error aparece recién en Fase 4.
- **Contrato OpenAPI v1.1.0** (`/contracts/openapi.yaml`) — ya construido; ver tabla y decisiones de diseño abajo.
- **Candado anti-drift en CI (paso obligatorio):** FastAPI genera su propio OpenAPI desde el código Python; sin vigilancia los dos contratos divergen silenciosamente desde la semana dos. El pipeline descarga el `/openapi.json` que FastAPI emite en runtime y lo diffea contra `contracts/openapi.yaml` con `oasdiff` — build falla si divergen. Schemathesis verifica *comportamiento*; este paso verifica *igualdad de contratos*. Los dos son necesarios y distintos.
- Generar el cliente TypeScript con `openapi-generator` (typescript-angular); **pinar versión del generador**. El cliente generado **nunca se usa directo en componentes** — se envuelve en una capa de servicios propios (`/services`), que aísla el frontend de las regeneraciones futuras.
- Gateway Nginx/Traefik levantado como única puerta de entrada (routing, CORS).
- **Hito:** rebanada vertical verde — `GET /transactions` responde datos reales desde Mongo; cliente Angular generado compila; componente renderiza la lista; `/health` responde; candado anti-drift corre en CI.

#### Contrato OpenAPI 1.1.0 — endpoints definidos

| Método | Ruta | Propósito | Seguridad |
|---|---|---|---|
| `GET` | `/health` | Liveness probe | Pública |
| `POST` | `/auth/login` | Login → par de tokens (access + refresh) | Pública |
| `POST` | `/auth/refresh` | Renovar access token | Pública |
| `GET` | `/auth/me` | Perfil del usuario en sesión | JWT |
| `GET` | `/transactions` | Listado paginado server-side (cursor) + filtros | JWT |
| `GET` | `/transactions/{id}` | Detalle de transacción | JWT |
| `GET` | `/transactions/{id}/audit` | Historial de auditoría (append-only) | JWT |
| `POST` | `/transactions/{id}/transitions` | Transición de estado (aprobar/rechazar/revisar/revertir) | JWT + rol supervisor |

#### Decisiones de diseño del contrato (defendibles en entrevista)

- **Transiciones por un solo endpoint** (`/transitions` con campo `action`) en vez de `/approve`, `/reject`, `/reverse` separados → centraliza la validación de la máquina de estados; el estado solo cambia de forma controlada.
- **`Idempotency-Key` como header obligatorio (UUID)** → reintentos no re-ejecutan la acción. El `409` distingue tres casos: transición inválida, versión desactualizada (`STALE_VERSION`) y conflicto de idempotencia.
- **Bloqueo optimista (`version` + `expectedVersion`)** → dos actores distintos mutando en paralelo no se pisan. Complementa la idempotencia: ella cubre reintentos del *mismo* intento; el bloqueo cubre la carrera entre *actores distintos*.
- **Segregación de funciones en el contrato** → `403` con ejemplo propio (`SEGREGATION_OF_DUTIES`). El control de negocio es visible en el contrato, no escondido en el código.
- **Paginación por cursor** → `OFFSET 400000` recorre 400k filas para descartarlas; el cursor salta directo. `totalEstimate` (aproximado) en vez de `count()` exacto, costoso a volumen.
- **Esquema de error uniforme** (`code` + `message` + `details`) → manejo limpio en un solo interceptor Angular.
- **RBAC en el contrato:** roles `operador`, `supervisor`, `auditor`; la mutación exige `supervisor`.

> **Pendientes deliberados v1:** no incluye `POST /transactions` (las transacciones llegan de sistemas externos, se siembran con Faker). `notifications` eliminado de v1 — nace en Fase 8 junto con el outbox que lo justifica.

### Fase 1 — Backend núcleo: transacciones a volumen

- Modelo de dominio (POO): id, monto, moneda, origen/destino, tipo, **estado**, **versión**, timestamps, metadatos.
- **Índices compuestos siguiendo la regla ESR** (Igualdad → Sort → Rango): elegir los 2-3 patrones de acceso dominantes (estado + fecha, estado + monto) y crear índices para ellos. No es posible indexar todas las permutaciones de 6 filtros — Mongo no intersecta índices bien. **Test obligatorio:** un test corre `explain()` sobre cada query de listado y falla si detecta `COLLSCAN`. Eso sí es defendible; afirmar "tiene índices" sin probarlo no.
- **Cursor compuesto, no simple:** el cursor codifica el campo de orden *más* un desempate por `_id` (`{createdAt, _id}`); la query usa comparación compuesta `(createdAt, _id) < (cursor_date, cursor_id)`. Un cursor sobre un solo campo con timestamps duplicados salta o repite filas — bug silencioso que solo aparece a volumen.
- **Sin cache de listados en Redis.** Con índices correctos sobre 500k documentos no hace falta, y la invalidación con filtros combinables es un problema combinatorio sin solución elegante. Redis gana su lugar con idempotencia y rate limiting; el cache va solo en los agregados del dashboard (Fase 5).
- **Seed a volumen con `insert_many` por lotes de 5-10k** (no one-by-one, que tarda horas). Distribuciones realistas: sesgo de estados (mayoría APROBADA, minoría EN_REVISION), fechas distribuidas en 6-12 meses, montos con distribución log-normal. Sin esto el dashboard se verá sintético.
- **Hito:** listar y filtrar sobre 500k registros responde en ms; test de `explain()` verde (sin COLLSCAN); el seed corre en minutos, no en horas.

### Fase 2 — Auth, RBAC y desarrollo seguro

- Microservicio `auth`: usuarios, roles (`operador`, `supervisor`, `auditor`), login con JWT + refresh tokens.
- **JWT con firma asimétrica RS256**, no secreto HMAC compartido. Con RS256 solo `auth` firma con la clave privada; `transactions` y el gateway verifican con la clave pública — ningún servicio puede emitir tokens. Con HMAC cualquier servicio que conozca el secreto puede firmar. Una línea de configuración, señal de diseño real.
- **Hashing con argon2** (o bcrypt como mínimo) — jamás sha256 a mano ni md5.
- **Rotación de refresh tokens con detección de reuso:** cada uso del refresh emite uno nuevo y revoca el anterior; si un refresh ya revocado se usa de nuevo, se invalida *toda la familia de tokens* de esa sesión (señal de robo). Es el patrón correcto, no solo "el refresh expira en X días".
- **RBAC como dependency reutilizable en FastAPI** (`require_role("supervisor")`), no `if` regados por los routers. La autorización del cliente (ocultar botones) es UX; la del servidor es seguridad real.
- Interceptor HTTP en Angular adjunta el JWT; interceptor de error maneja 401 (refresh automático) y 403 (redirección).
- **Hito:** un `operador` no puede acceder a endpoints de `supervisor` ni vía API directa (test automatizado); un refresh token reutilizado invalida la sesión; rutas Angular protegidas por rol.

### Fase 3 — Frontend Angular: la consola

- Listado de transacciones con paginación server-side, filtros (estado, rango de fecha, monto, contraparte), ordenamiento y búsqueda — todos disparando queries al backend, sin filtrar en cliente.
- **Estado de filtros en la URL** (query params sincronizados con Angular Router): los filtros son deep-linkeables, el botón atrás funciona, y se puede pegar "pendientes sobre $1M de marzo" como link en el README. No en memoria ni en un servicio.
- **Paginación clásica ("cargar más" o páginas numeradas)**, no virtual scroll del CDK. Con datos remotos el virtual scroll requiere gestión compleja del viewport + buffer + prefetch; la paginación clásica es suficiente, más simple y más predecible. El virtual scroll del CDK brilla con listas locales, no con fuentes remotas paginadas.
- **Reglas RxJS no negociables:** `async pipe` en plantillas siempre que sea posible (Angular desuscribe automáticamente); `takeUntilDestroyed()` donde no se pueda. Una suscripción `.subscribe()` sin liberar es un memory leak garantizado en un listado que se navega repetidamente.
- Los componentes consumen los **servicios propios** (`/services`), no el cliente generado directamente — la capa de envoltura definida en Fase 0 paga su precio aquí.
- Vista de detalle con historial de estados y auditoría; manejo de errores del API (400/403/409/5xx) mapeado a mensajes claros en UI.
- **Hito:** la consola navega 500k registros con fluidez; los filtros persisten en la URL; no hay suscripciones sin liberar (detectado con linting); filtrar/ordenar/paginar se siente instantáneo.

### Fase 4 — Flujo transaccional completo (el corazón senior)

- **Máquina de estados implementada como datos, no como if/else.** Un dict/mapa `{estado_actual: {accion: estado_siguiente}}` define todas las transiciones válidas. Testeable exhaustivamente con un loop sobre todas las combinaciones de estado × acción, incluidas las prohibidas. Una cadena de `if/elif` crece sin control y deja combinaciones sin probar.
- **Segregación de funciones (maker-checker):** el `createdBy` de la transacción se valida contra el actor de la transición en el servicio — el iniciador no puede aprobar su propia transacción. Control clásico de banca.
- **Idempotencia con `SET NX` atómico en Redis:** la clave de idempotencia se reserva *atómicamente* (`SET key "processing" NX EX 30`) al inicio de la operación y se actualiza al resultado al final. Un GET seguido de SET separados tiene su propia carrera: dos requests con la misma clave llegan en el mismo milisegundo y ambos ven la clave ausente. La atomicidad de `SET NX` es la solución, no un detalle.
- **Transacción Mongo multi-documento** (disponible por el replica set de Fase 0): estado + auditoría + (en v2) evento outbox se escriben en una sesión transaccional. Sin esto, un crash entre la escritura del estado y la de auditoría deja el registro inconsistente — auditoría que puede mentir es peor que no tener auditoría.
- **Bloqueo optimista:** el update de Mongo filtra por `{_id, version: expectedVersion}` — si el documento cambió, el update afecta 0 documentos y se responde `409 STALE_VERSION`. El cliente recarga y reintenta con la versión nueva.
- **Auditoría inmutable:** colección append-only, sin update ni delete. Cada entrada registra actor, acción, estado anterior y nuevo, timestamp y motivo.
- **Hito:** transiciones inválidas rechazadas; maker no puede ser checker; dos requests idempotentes simultáneos → solo uno ejecuta; dos actores distintos en paralelo → el segundo recibe `409 STALE_VERSION`; auditoría refleja todo; un crash simulado entre escrituras no deja estado inconsistente.

### Fase 5 — Dashboard y métricas

- Panel con métricas agregadas: volumen por estado, montos por período, tasa de aprobación/rechazo, transacciones en revisión.
- **Un solo aggregation pipeline con `$facet`** para traer todas las métricas en una pasada — no cinco queries separadas al dashboard.
- **Cache Redis con TTL corto (30-60s) en los endpoints de agregados.** Aquí sí tiene sentido: la invalidación es por tiempo (no por evento), el resultado es un objeto pequeño, y correr el aggregation pipeline sobre 500k en cada carga del dashboard degrada sin necesidad.
- Gráficos con ng2-charts/Chart.js.
- **"Mi actividad" (accountability por actor — pregunta del usuario, Fase 4):** un supervisor necesita ver qué transacciones envió a revisión / aprobó / rechazó *él*, distinto de la bandeja compartida (`status=EN_REVISION`). La fuente correcta es la **auditoría**, no `reviewedBy`: con varios supervisores, `reviewedBy` guarda solo el último actor, así que "yo envié a revisión y otro aprobó" se pierde; la auditoría guarda el `actor` en cada paso (append-only) y no se pierde. Falta solo poder consultarla cruzando transacciones por actor (hoy `/audit` es por-transacción) + índice `(actor, at)`. Decisión de negocio que conlleva: supervisor ve lo suyo; el rol `auditor` ve el historial de todos (accountability vs. need-to-know). El correlation ID ya persistido en cada entrada (auditoría Fase 4) suma trazabilidad forense.
- **Hito:** dashboard carga todas las métricas en una pasada; un segundo reload sirve desde cache; los números son coherentes con el seed.

### Fase 6 — DevOps y observabilidad: contenedores, CI/CD, orquestación

- Dockerfile por servicio (multi-stage, imágenes delgadas).
- **GitHub Actions:** lint (ruff + eslint), tests (pytest + Jest/Vitest), build de imágenes, candado anti-drift (`oasdiff`), Schemathesis.
- **Schemathesis con hook de autenticación:** sin el hook, Schemathesis recibe 401 en todos los endpoints protegidos y el paso de CI es un teatro verde que no prueba nada. El hook hace login antes de la suite e inyecta el token en cada request generado.
- **Separación de base de datos entre servicios:** `auth` usa una base Mongo distinta a `transactions` (o instancia distinta). Tres servicios compartiendo una sola instancia Mongo es un monolito distribuido — el anti-patrón que los artículos de microservicios usan de ejemplo negativo. Mínimo: bases lógicas separadas, con acceso restringido por credenciales.
- **Observabilidad mínima viable:** logs estructurados JSON + correlation ID (generado en el interceptor Angular, propagado por header a través del gateway y presente en cada línea de log). Un request se sigue de punta a punta. Prometheus/Grafana quedan para v2.
- Manifiestos Kubernetes (Deployment, Service, ConfigMap, Secret) en kind/minikube.
- Healthchecks, readiness probes y secrets fuera del código.
- **Hito:** `kubectl apply` levanta el stack; CI verde con candado anti-drift + Schemathesis con auth; un correlation ID atraviesa todos los servicios en los logs; `auth` y `transactions` acceden a bases distintas.

### Fase 7 — Pulido, pruebas y narrativa

- Tests unitarios de la máquina de estados (todas las combinaciones estado × acción, incluidas las prohibidas — es un loop, no 20 tests individuales) y reglas de segregación.
- Tests de integración del flujo transaccional completo (happy path + casos de error: transición inválida, versión stale, reuso de idempotency-key).
- **E2e con Playwright** (no Cypress — mejor soporte de Angular, más rápido, más moderno). Camino feliz: login → listado → filtro → detalle → transición.
- **Load testing con k6:** medir y publicar los números **con su contexto de entorno** en el README ("p95 X ms, throughput Y req/s, sobre 500k documentos, VPS de 2 vCPU / 4GB RAM, Mongo en el mismo host"). Números sin entorno son marketing; con entorno son ingeniería reproducible.
- **README con narrativa de decisiones** — las secciones que valen en entrevista con SONDA: *"por qué RS256 y no HMAC"*, *"por qué máquina de estados como datos y no if/else"*, *"por qué cursor compuesto y no offset"*, *"por qué SET NX atómico para idempotencia"*, *"por qué replica set desde el día uno"*, *"por qué bases separadas entre servicios"*, *"qué no construí y por qué"*.
- Datos demo precargados; desplegar demo pública.
- **Hito:** un desconocido entra al link, entiende qué hace en 30 segundos, opera una transacción, y lee en el README por qué cada decisión.

### Fase 8 — Evolución (v2): roadmap documentado

> Se documenta en el README *aunque no esté construido* — diseñar pensando en cómo crece el sistema es señal en sí misma. Regla dura: la v2 solo arranca con la v1 cerrada y desplegada.

- **Eventos de dominio + patrón outbox (la mejora con mejor ratio señal/esfuerzo):** cada transición escribe su evento en una colección outbox *en la misma operación* que el cambio de estado; un relay lo publica a **Redis Streams**; `notifications` lo consume y deja de ser decorativo. Resuelve el problema del dual-write (¿qué pasa si guardo en Mongo pero falla el publish?) — el tema de diseño distribuido transaccional por excelencia.
- **Consola en vivo (SSE):** sobre esos mismos eventos, el frontend se suscribe vía Server-Sent Events y el listado se actualiza solo. Momento de demo: dos navegadores abiertos, apruebas en uno, el otro se actualiza al instante — consecuencia de la arquitectura, no un gimmick.
- **Conciliación batch (el "springbatch" del proyecto):** job nocturno que ingiere una cartola simulada (CSV de un sistema externo) y la **concilia** contra las transacciones, marcando discrepancias como `EN_REVISION`. Proceso bancario clásico; responde directamente a la mención de springbatch en la oferta.
- **Motor de reglas simple:** reglas configurables ("monto > X y contraparte nueva → enviar a revisión") evaluadas al ingresar transacciones. Llena `EN_REVISION` con casos realistas y es semilla de detección de fraude.
- **Descartado deliberadamente (y documentado como tal):** multi-tenancy (complejidad grande, señal marginal para esta oferta) y Kafka real (Redis Streams demuestra el patrón sin el peso operacional). Saber qué NO construir también es criterio senior.
- **Hito:** roadmap visible en el README con justificación de cada pieza y de cada descarte.

## Verificación (end-to-end)

- **Volumen:** seed corre en minutos (insert_many por lotes); listar/filtrar/paginar sobre 500k responde en ms; test de `explain()` verde (sin COLLSCAN); números de k6 con contexto de entorno publicados en README.
- **Contrato:** cliente Angular regenerado desde `openapi.yaml` sin edición manual; frontend compila; candado anti-drift (`oasdiff`) falla el build si FastAPI diverge del contrato; Schemathesis con hook de auth valida comportamiento.
- **Seguridad:** RBAC rechazado a nivel de API (no solo UI); JWT RS256 — ningún servicio distinto a `auth` puede emitir tokens; refresh reutilizado invalida la sesión completa; rate limit en gateway.
- **Transaccional:** transiciones inválidas rechazadas por la máquina de estados (loop de tests sobre todas las combinaciones); maker no puede ser checker; `SET NX` atómico evita doble ejecución concurrente; bloqueo optimista — dos actores simultáneos, el segundo recibe `409 STALE_VERSION`; escritura de estado + auditoría es atómica (sesión Mongo transaccional); auditoría append-only sin posibilidad de edición.
- **DevOps:** `docker compose up` y `kubectl apply` en minikube levantan el stack; Mongo levanta en modo replica set; CI verde con todos los pasos; `auth` y `transactions` acceden a bases distintas; correlation ID atraviesa todos los servicios en los logs.

## Riesgos y mitigaciones

- **Explosión de alcance (alto):** "un sistema bancario" es infinito. **Mitigación:** acotar a UN flujo transaccional completo (gestión + aprobación + reversa) bien hecho, no diez a medias.
- **Curva de Angular si vienes de React (medio-alto):** TypeScript estricto, RxJS, DI y módulos son otro mundo. **Mitigación:** asumirlo como parte del valor; arrancar Angular desde Fase 0 en paralelo, no al final. No es un fin de semana.
- **Poco "wow" visual (medio):** un back-office Bootstrap no deslumbra. **Mitigación:** su impacto es la solidez — volumen paginando instantáneo, contrato versionado, CI verde, números de k6. El público técnico lo lee.
- **Monolito distribuido (medio):** tres servicios con una sola base Mongo es el anti-patrón. **Mitigación:** bases lógicas separadas por servicio desde Fase 0; documentar la decisión en el README.
- **Replica set olvidado (medio-alto):** si se levanta Mongo standalone, las transacciones multi-documento fallan en runtime en Fase 4, no antes. **Mitigación:** replica set desde Fase 0, con test de smoke que verifica que las transacciones están disponibles.
- **Schemathesis ciego (bajo con mitigación):** sin hook de auth verifica solo los endpoints públicos. **Mitigación:** hook de login en la configuración de Schemathesis desde que se agrega al CI.
- **Sobre-ingeniería (medio):** dos servicios con razón clara > tres donde uno es decorativo. **Mitigación:** `notifications` en v2, donde el outbox le da razón de existir; documentar los descartes en el README.
- **Costo/hosting demo (bajo-medio):** free tiers (Mongo Atlas, Upstash Redis) + VPS básico o Render/Railway. Dataset precargado.
- **Experiencia bancaria real (bajo):** presentar honestamente como demostración técnica de los patrones del dominio.

## Cómo encaja en el portafolio

Dos proyectos, dos mensajes complementarios:

- **Grafo de Conocimiento** → "sé hacer cosas innovadoras con IA y datos" (eje innovación).
- **Consola Transaccional** → "y también opero en el mundo transaccional serio, con las herramientas y la disciplina que SONDA usa" (eje empresa grande).

Para SONDA específicamente, el segundo es el que abre la puerta; el primero es el que te hace memorable una vez dentro.

## Registro de cambios

### v1.7 → v1.8 (Fase 5 — 2026-06-13)

1. **Dashboard sin `$facet`, contra lo que el plan pedía — con evidencia.** Medido sobre 500k: `$facet` 69s vs dos `$group` separados 1.2s (55×). `$facet` materializa todo en memoria y no usa índices. Los rollups corren en paralelo (`asyncio.gather`); el total se deriva de los conteos por estado. El cache Redis (TTL 30s) sigue: MISS 0.9s, HIT 0.07s. **Corrección del plan**: la regla pasa a ser "agregaciones separadas que puedan usar índices > un `$facet` sobre toda la colección".
2. **"Mi actividad" implementada** (pregunta del usuario): `GET /activity` sobre la auditoría por actor (índice `actor, at`), con filtro por acción. Responde "qué envié a revisión / aprobé / rechacé" de forma estable con varios supervisores.
3. **Header `X-Cache: HIT/MISS`** (fuera del contrato) hace observable el cache en la demo.
4. **`ng2-charts` 10 + Chart.js** para los gráficos; `@angular/cdk` pinado a v21 (mismo motivo que ng-bootstrap).

### v1.6 → v1.7 (auditoría post-Fase 4 — 2026-06-13)

1. **Handler global de `Exception` → `500 {code: INTERNAL}`** en ambos servicios: una excepción no manejada ya no escapa al `detail` por defecto de FastAPI; cumple el esquema del contrato (lo iba a cazar Schemathesis en Fase 6) y loguea con correlation ID.
2. **Redis caído → `503 SERVICE_UNAVAILABLE` (fail-closed)** en transiciones: sin store de idempotencia NO se muta el estado. Re-ejecutar una transición sin esa garantía es peor que rechazarla con un mensaje accionable. Nuevo en el contrato.
3. **Correlation ID persistido en cada entrada de auditoría** (solo en Mongo; el response model lo filtra): del click del operador al registro inmutable, todo enlazado por un id. Cimiento de la feature "Mi actividad" de Fase 5.
4. **`release()` de idempotencia tolera fallos de Redis:** no enmascara la excepción original que gatilló el release.
5. **Feature "Mi actividad" documentada en Fase 5** (pregunta del usuario): accountability por actor sobre la auditoría, no sobre `reviewedBy`.

### v1.5 → v1.6 (auditoría post-Fase 3 — 2026-06-13, gatillada por hallazgo del usuario)

> El usuario encontró la consola "pegada" en el spinner. El diagnóstico reveló
> queries de hasta 212s acumuladas en Mongo. Tres fixes estructurales:

1. **`maxTimeMS` en las queries de listado** (10s, configurable) + `503 QUERY_TIMEOUT` en el contrato: una combinación de filtros demasiado amplia falla rápido y accionable. Lección de fondo: la cancelación HTTP del cliente NO cancela la query en la base.
2. **Prefijo mínimo de 3 caracteres en `counterparty`** en los tres niveles (contrato `minLength`, validación backend 422, el frontend no envía prefijos cortos): un prefijo de 1-2 letras matchea una fracción enorme del índice multikey.
3. **Estado de error renderizable en el listado** con botón Reintentar — un error ya no deja spinner eterno; el toast pasajero no es representación válida de un error de página.

### v1.4 → v1.5 (auditoría post-Fase 2 — 2026-06-12)

1. **`POST /auth/logout` agregado al contrato (v1):** revoca la familia de refresh server-side; siempre 204 (no revela validez del token; revocar es inocuo). Sin esto, "cerrar sesión" dejaba la familia viva hasta su TTL de 7 días.
2. **El 429 del gateway cumple el contrato:** nginx devolvía su página HTML; ahora `error_page 429` retorna el esquema `Error` JSON + `Retry-After`.
3. **Test del interceptor de refresh:** dos 401 paralelos → exactamente UN llamado a `/auth/refresh` y ambos requests reintentados con el token nuevo. Es la garantía que evita que la rotación con detección de reuso queme la familia ante concurrencia normal del frontend.
4. **Blacklist de JWT en Redis: descartada y documentada** (README): access de 15 min + logout que revoca familia + detección de reuso cubren el riesgo; una blacklist por request agrega estado y latencia desproporcionados. Punto de entrada documentado si v2 exigiera revocación inmediata.

### v1.3 → v1.4 (refuerzos post-Fase 1 — 2026-06-12)

> Revisión deliberada al cierre de las fases de tubería: qué ajustar barato hoy
> para no pagarlo caro en Fases 2-4.

1. **`counterparty` pasa de substring a prefijo anclado** sobre `searchKeys` (nombres/cuentas normalizados en minúsculas, índice multikey). Un substring sin anclar es COLLSCAN sin remedio; el prefijo usa índice. Documentado en el contrato como decisión (full-text descartado en v1). Test propio en `test_indexes.py`.
2. **Test de caminata de páginas** (`test_pagination_walk.py`): 50 documentos con `createdAt` y `amount` idénticos (peor caso del cursor), se caminan todas las páginas en 4 ordenamientos y se exige cada documento exactamente una vez. Cubre el "bug silencioso a volumen" con comportamiento real, no solo unit tests de forma.
3. **Observabilidad mínima adelantada de Fase 6 a ahora:** middleware de correlation ID + logs JSON (stdlib) en ambos servicios. Razón: retrofitear logging en Fase 6 obligaría a tocar todo el código de Fases 2-4; ahora ese código nace logueando bien. El hito de Fase 6 (seguir un request de punta a punta) no cambia.
4. **Makefile en la raíz** (`make help`): estandariza PATH de WSL, JAVA_HOME y los comandos del día a día; `DRIFT_PATHS` es el espejo local del candado de CI.

### v1.2 → v1.3 (implementación real de Fase 0 — 2026-06-12)

1. **Angular 21, no 22:** ng-bootstrap aún no soporta Angular 22 (peer deps); 21 es la LTS estable que el plan pide. Revisar cuando ng-bootstrap publique soporte.
2. **Candado anti-drift con normalizador propio, no oasdiff a secas:** el contrato es OpenAPI 3.0.3 (`nullable:`) y FastAPI emite 3.1 (`anyOf: [..., null]`); `infra/ci/check_drift.py` canonicaliza ambos estilos y compara estructura path por path. oasdiff directo daba falsos positivos en masa.
3. **Ajustes al contrato durante Fase 0:** `nullable: true` en campos que el server serializa como null (`reference`, `updatedAt`, `metadata`, `details`); `422` agregado a `GET /transactions/{id}` y `/audit` (FastAPI lo emite siempre que hay parámetros); `required` en la respuesta de `/health`.
4. **pymongo async en vez de Motor:** Motor está en mantenimiento; el cliente async oficial de PyMongo es el camino actual.
5. **uv como gestor Python** (proyectos y scripts PEP 723: seed y check_drift autocontenidos).
6. **Registro vivo de problemas-soluciones:** `docs/problemas-resueltos.md`, cargado en cada sesión vía `CLAUDE.md`, para que ningún problema resuelto se vuelva a investigar.

### v1 → v1.1
1. Bloqueo optimista (`version` + `expectedVersion` + `409 STALE_VERSION`).
2. Gateway Nginx/Traefik definido con rate limiting centralizado.
3. Observabilidad mínima: logs JSON + correlation ID.
4. Load testing con k6 y números publicados en README.
5. Schemathesis en CI para testing de contrato.
6. Fase 8: roadmap de evolución v2 (outbox, SSE, conciliación batch, motor de reglas).

### v1.1 → v1.2
1. **Rebanada vertical como regla de construcción** (Fase 0): validar toda la tubería en la semana uno, no capas horizontales.
2. **Candado anti-drift (`oasdiff`) en CI** (Fase 0): dos contratos vivos sin vigilancia divergen silenciosamente.
3. **Capa de envoltura del cliente generado** (`/services`) + versiones del generador pinadas (Fase 0).
4. **Mongo en modo replica set desde Fase 0**: sin esto las transacciones multi-documento de Fase 4 no existen en runtime.
5. **Cursor compuesto** (campo de orden + `_id`) en vez de cursor simple — evita saltos/duplicados con timestamps iguales (Fase 1).
6. **Índices ESR con test de `explain()`** que falla en COLLSCAN; eliminado el cache de listados (Fase 1).
7. **Seed con `insert_many` por lotes** y distribuciones realistas (Fase 1).
8. **JWT RS256** (firma asimétrica): solo `auth` puede emitir tokens (Fase 2).
9. **Argon2 para hashing** + rotación de refresh tokens con detección de reuso (Fase 2).
10. **RBAC como dependency reutilizable** en FastAPI, no if/else en routers (Fase 2).
11. **Filtros en URL** (query params) en vez de en memoria (Fase 3).
12. **Paginación clásica** en vez de virtual scroll del CDK con datos remotos (Fase 3).
13. **`async pipe` y `takeUntilDestroyed` obligatorios** — sin suscripciones sin liberar (Fase 3).
14. **Máquina de estados como datos** (dict), no if/else; testeable con loop sobre todas las combinaciones (Fase 4).
15. **`SET NX` atómico** para idempotencia (no GET-luego-SET) (Fase 4).
16. **Sesión transaccional Mongo multi-documento** para estado + auditoría (Fase 4).
17. **Cache Redis solo en agregados del dashboard** con TTL + `$facet` en un solo pipeline (Fase 5).
18. **Schemathesis con hook de autenticación** (Fase 6).
19. **Bases separadas por servicio** — `auth` y `transactions` no comparten instancia Mongo (Fase 6).
20. **Playwright** en vez de Cypress para e2e (Fase 7).
21. **Números de k6 con contexto de entorno** en README (Fase 7).
