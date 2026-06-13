# Registro de problemas y soluciones

> Propósito: que ningún problema ya resuelto se vuelva a investigar desde cero.
> Cada entrada: **Problema → Causa → Solución → Cómo evitar que se repita.**
> Este archivo se carga en cada sesión vía `CLAUDE.md`. Agregar entradas nuevas
> arriba (orden cronológico inverso) y marcar `RESUELTO` o `ABIERTO`.

---

## 2026-06-13 — Fase 5

### 26. `$facet` es 55× más lento que dos `$group` separados sobre 500k — RESUELTO
- **Problema:** el dashboard con `$facet` (que el plan pedía como "una sola pasada") tardaba **69s** sobre 500k → 504 del gateway y `ExecutionTimeout`. Los mismos `$group` por separado: **1.2s** en total.
- **Causa:** `$facet` materializa toda su entrada en memoria y sus sub-pipelines **no usan índices ni streaming**. La intuición "una pasada < N queries" es falsa cuando esa pasada es un `$facet` sobre una colección grande.
- **Solución:** se eliminó `$facet`; los rollups (por estado, por mes) corren como `$group` separados en paralelo (`asyncio.gather`), ~1.2s. El total se deriva de los conteos por estado (una query menos). Medido en vivo: MISS 0.9s, HIT 0.07s.
- **Cómo evitarlo:** `$facet` sirve para reutilizar un sub-conjunto YA filtrado (tras un `$match` selectivo), no para escanear toda la colección en paralelo. A volumen, medir antes de asumir; preferir agregaciones que puedan usar índices.

---

## 2026-06-13 — Auditoría Fase 4

### 25. Una excepción no manejada rompe el esquema de error del contrato — RESUELTO
- **Problema:** solo `ApiError` y validación tenían handler; un bug o dependencia caída caía al `{"detail": "Internal Server Error"}` por defecto de FastAPI, que no es el esquema `code/message` del contrato. Schemathesis (Fase 6) lo iba a cazar.
- **Solución:** handler global `@app.exception_handler(Exception)` → `500 {code: INTERNAL}` en ambos servicios, con `logger.exception` (el correlation ID lo inyecta el formatter).
- **Cómo evitarlo:** el handler genérico es parte del scaffold de cualquier servicio nuevo. En tests usar `TestClient(app, raise_server_exceptions=False)` para ver la respuesta en vez de que propague.

### 24. Redis caído ejecutaba mutaciones sin garantía de idempotencia — RESUELTO
- **Problema:** si Redis no respondía, `claim()` lanzaba `ConnectionError` → 500 críptico; peor, conceptualmente la operación podía re-ejecutarse sin protección.
- **Solución:** `IdempotencyUnavailableError` → `503 SERVICE_UNAVAILABLE` (fail-closed): sin store de idempotencia NO se muta el estado. Nuevo en el contrato.
- **Cómo evitarlo:** toda mutación que dependa de un recurso externo para su corrección debe decidir explícitamente fail-open vs fail-closed. En banca, fail-closed.

### 23. `release()` de idempotencia podía enmascarar el error original — RESUELTO
- **Problema:** si la operación fallaba y además Redis fallaba al liberar la clave, la excepción de Redis tapaba la causa real en el log.
- **Solución:** `try/except RedisError: pass` en `release()` — el caller ya propaga el error verdadero.

---

## 2026-06-13 — Auditoría Fase 3 (hallazgo del usuario: spinner pegado)

### 22. Queries canceladas por el frontend siguen corriendo en Mongo y se acumulan — RESUELTO
- **Problema:** la consola quedó "pegada" en el spinner. Los logs mostraron la verdad: las queries respondían 200 pero con latencias de 30s, 36s y hasta **212 segundos**.
- **Causa (cadena completa):** (1) prefijos de contraparte de 1-2 letras (`c`, `co` mientras se tipea) matchean una fracción enorme del índice multikey `searchKeys` → scan gigante + top-k sort; (2) al cambiar filtros, `switchMap` cancela el request del frontend pero **el servidor no cancela la query en Mongo** — siguen corriendo; (3) avalancha de queries pesadas concurrentes → degradación en bola de nieve.
- **Solución (tres niveles):** `maxTimeMS` (10s, `TXN_QUERY_TIMEOUT_MS`) en la query de listado → `503 QUERY_TIMEOUT` con mensaje accionable (nuevo en el contrato); `minLength: 3` para counterparty en contrato + backend; el frontend no envía prefijos <3 chars y muestra el mínimo en el placeholder.
- **Cómo evitarlo:** toda query expuesta a filtros de usuario lleva cota de tiempo server-side. La cancelación HTTP del cliente NO cancela la operación en la base — diseñar siempre asumiendo eso.

### 21. Spinner eterno cuando el listado falla o tarda — RESUELTO
- **Problema:** ante un error, el stream emitía solo un toast (que expira en 8s) y nada más: la UI quedaba en spinner indefinido sin acción posible.
- **Causa:** `catchError → EMPTY` dentro del stream del listado: el error no producía estado visible.
- **Solución:** el error es parte del view-model (`ListVm.error`) → alert persistente con botón **Reintentar** (`reload$`). El toast del listado se eliminó: un error de carga es estado de página, no notificación pasajera.
- **Cómo evitarlo:** regla de UI: todo stream que alimenta una vista debe tener representación de error renderizable, no solo efectos secundarios.

### 20. El test de caminata hacía COLLSCAN de 500k por página — RESUELTO
- **Problema:** con `maxTimeMS` activo, el test de caminata empezó a fallar con `ExecutionTimeout` (y la suite tardaba 9 minutos con Mongo degradado).
- **Causa:** filtraba solo por `currency=TST` (sin índice) → COLLSCAN completo por cada página caminada.
- **Solución:** el test acota además por rango de fechas alrededor del instante de los documentos → usa el índice `(createdAt, _id)`; la suite volvió a 2.5s.
- **Cómo evitarlo:** los tests de integración también deben usar queries indexables — un test lento es un test que se deja de correr.

---

## 2026-06-12 — Fase 3

### 19. `HttpTestingController` no puede flushear requests canceladas por forkJoin — RESUELTO
- **Problema:** test del detalle: al simular 404 en la transacción, flushear la request de audit lanzaba `Cannot flush a cancelled request`.
- **Causa:** `forkJoin` cancela las requests hermanas cuando una falla; la request queda en `match()` pero cancelada.
- **Solución:** filtrar con `if (!pending.cancelled)` antes de flushear.
- **Cómo evitarlo:** en tests de componentes con `forkJoin`/`switchMap`, asumir que habrá requests canceladas y filtrarlas.

---

## 2026-06-12 — Fase 2

### 18. La clave privada montada (0600) no es legible por el usuario del contenedor — RESUELTO
- **Problema:** `auth` arrancaba pero login daba 500: `PermissionError: /keys/jwt-private.pem`.
- **Causa:** la clave es `0600` del usuario host (uid 1000); el contenedor corre como `appuser` (otro uid). El bind mount conserva uid/permisos del host.
- **Solución:** `user: "${UID:-1000}:${GID:-1000}"` en el servicio `auth` del compose. NO relajar los permisos de la clave.
- **Cómo evitarlo:** todo secreto montado como archivo necesita pensar uid del proceso del contenedor. En K8s (Fase 6) esto se resuelve con Secrets + fsGroup.

### 17. PyJWT bloquea el ataque de confusión HS256/RS256 en el encode — RESUELTO (era el test)
- **Problema:** el test que intentaba firmar HMAC usando la clave pública como secreto (ataque clásico contra validadores mal configurados) fallaba en `jwt.encode`, no en `decode`.
- **Causa:** PyJWT se niega a usar un PEM asimétrico como secreto HMAC, precisamente para prevenir ese ataque.
- **Solución:** el test correcto firma RS256 con OTRA clave RSA y verifica el rechazo. La defensa real del validador es `algorithms=["RS256"]` fijo en `jwt.decode` — nunca aceptar el `alg` del header.

### 16. argon2 lanza `InvalidHashError` con hashes corruptos — RESUELTO
- **Problema:** `verify_password` explotaba (500 potencial) si el hash guardado no era un hash argon2 válido.
- **Causa:** `InvalidHashError` no hereda de `VerificationError` en argon2-cffi.
- **Solución:** capturar `(VerifyMismatchError, VerificationError, InvalidHashError)` y devolver False.

---

## 2026-06-12 — Fase 1

### 15. `docker compose wait` no sirve para one-shots ya salidos — RESUELTO
- **Problema:** `docker compose wait mongo-init` → "no containers for project" si el init ya terminó.
- **Causa:** `wait` solo considera contenedores corriendo.
- **Solución:** `docker compose run --rm mongo-init` — arranca la dependencia `mongo` (espera healthcheck), corre el init en foreground y propaga su exit code. Es lo que usa el job `indexes` del CI y es idempotente.

### 14. `AsyncMongoClient` se ata al event loop donde nació — RESUELTO
- **Problema:** los tests async de índices fallaban con `Cannot use AsyncMongoClient in different event loop`.
- **Causa:** pytest-asyncio crea un loop por test; el cliente global cacheado en `transactions_repo.get_db()` quedó atado al loop del primer test.
- **Solución:** `asyncio_default_fixture_loop_scope = "session"` y `asyncio_default_test_loop_scope = "session"` en `pyproject.toml` — un solo loop para toda la sesión de tests.
- **Cómo evitarlo:** cualquier servicio nuevo que use pymongo async + pytest-asyncio necesita esas dos líneas desde el día uno.

### 13. Ordenar por monto sin filtro hacía COLLSCAN + SORT — RESUELTO (atrapado por el test)
- **Problema:** `sort=-amount` sin filtro de estado escaneaba la colección completa y ordenaba en memoria (a 500k revienta el límite de 32MB de sort).
- **Causa:** los índices ESR cubrían estado+fecha y estado+monto, pero la API permite ordenar por monto sin filtros y ese patrón no tenía índice.
- **Solución:** índice `(amount: -1, _id: -1)` en `ensure_indexes()` y en el seed.
- **Cómo evitarlo:** este es exactamente el trabajo del test `tests/test_indexes.py`: todo patrón de listado nuevo (filtro o campo de orden) se agrega a `DOMINANT_QUERIES` y el test exige plan sin COLLSCAN ni SORT bloqueante.

---

## 2026-06-12 — Fase 0

### 1. `node`/`npm` de Windows contaminan el PATH de WSL — RESUELTO
- **Problema:** `node --version` fallaba o resolvía a `/mnt/c/...` (binarios de Windows); builds de Angular lentísimos o rotos desde WSL.
- **Causa:** WSL hereda el PATH de Windows; el Node de Windows aparece antes que cualquier instalación Linux en shells no interactivos.
- **Solución:** Node 24 LTS nativo vía nvm (`~/.nvm/versions/node/v24.16.0/bin`).
- **Cómo evitarlo:** en scripts/comandos no interactivos, anteponer siempre `export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"`. Nunca usar el node de `/mnt/c`.

### 2. `oasdiff` a secas no sirve como candado anti-drift — RESUELTO
- **Problema:** el contrato (`contracts/openapi.yaml`) es OpenAPI 3.0.3 con `nullable: true`; FastAPI emite 3.1 con `anyOf: [X, {type: null}]`. Diferían sintácticamente siendo semánticamente idénticos: cualquier diff directo da falsos positivos en masa.
- **Causa:** dos dialectos de OpenAPI para expresar lo mismo.
- **Solución:** [infra/ci/check_drift.py](../infra/ci/check_drift.py) — deref-ea ambos documentos, canonicaliza (nullable/anyOf, defaults implícitos, claves cosméticas, orden de parámetros) y compara estructura path por path.
- **Cómo evitarlo:** no reemplazar el checker por oasdiff/diff genérico. Al implementar endpoints nuevos, ampliar el `--match-path` del job `anti-drift` en `ci.yml` (Fase 2: `/auth/*`; Fase 4: `/transitions`).

### 3. FastAPI inyecta su 422 `HTTPValidationError` automático — RESUELTO
- **Problema:** el candado detectaba un 422 con esquema `HTTPValidationError` en toda ruta con parámetros, que no existe en el contrato (esquema de error uniforme `code/message/details`).
- **Causa:** FastAPI agrega ese 422 por defecto a cada operación con params/body.
- **Solución:** declarar `responses={422: {"model": Error}}` en cada ruta + handler global de `RequestValidationError` en [errors.py](../services/transactions/app/api/errors.py) que emite el esquema del contrato.
- **Cómo evitarlo:** toda ruta nueva con parámetros debe declarar su 422 con `Error` y el contrato debe listar ese 422. El candado lo atrapa si se olvida.

### 4. Campos serializados como `null` deben ser `nullable` en el contrato — RESUELTO
- **Problema:** drift en `reference`, `updatedAt`, `metadata`, `details`: el server los serializa como `null` (pydantic incluye campos None por defecto) pero el contrato los declaraba opcionales no-nullables.
- **Causa:** "opcional" (puede faltar) ≠ "nullable" (puede venir null). Pydantic `X | None` es nullable.
- **Solución:** `nullable: true` en el contrato para esos campos.
- **Cómo evitarlo:** al agregar un campo `X | None` a un modelo de respuesta, marcarlo `nullable: true` en el contrato desde el inicio (o usar `exclude_none` y no marcarlo — elegir uno y ser consistente; hoy el proyecto serializa nulls).

### 5. Cursor malformado lanzaba `UnicodeDecodeError` sin capturar — RESUELTO
- **Problema:** un cursor con basura no-base64 producía 500 en vez de 422.
- **Causa:** `urlsafe_b64decode` tolera basura y devuelve bytes inválidos; `json.loads` lanza `UnicodeDecodeError`, que no estaba en el `except`.
- **Solución:** capturar `ValueError` (cubre `binascii.Error`, `JSONDecodeError` y `UnicodeDecodeError`) en `decode_cursor`.
- **Cómo evitarlo:** para entrada opaca del cliente, capturar la excepción base más amplia que tenga sentido y testear con basura real (hay test: `test_malformed_cursor_rejected`).

### 6. ng-bootstrap no soporta Angular 22 — RESUELTO
- **Problema:** `npm install @ng-bootstrap/ng-bootstrap` fallaba por peer deps con la app generada en Angular 22.
- **Causa:** Angular 22 salió hace semanas; ng-bootstrap 20 soporta hasta Angular 21.
- **Solución:** app en **Angular 21** (la LTS estable, que es lo que pide el plan).
- **Cómo evitarlo:** antes de subir de major de Angular, verificar `npm view @ng-bootstrap/ng-bootstrap peerDependencies`. No subir a 22 hasta que ng-bootstrap lo soporte.

### 7. ESLint linteaba el cliente generado: 147 errores — RESUELTO
- **Problema:** `ng lint` reportaba 147 errores, casi todos en `src/app/api-client/`.
- **Causa:** el cliente generado por openapi-generator no cumple (ni debe cumplir) las reglas del proyecto.
- **Solución:** bloque `ignores: ['src/app/api-client/**']` en [eslint.config.js](../frontend/eslint.config.js).
- **Cómo evitarlo:** el cliente generado no se edita ni se lintea, solo se regenera (`npm run generate:api`). Cualquier herramienta nueva (prettier, etc.) debe excluirlo también.

### 8. `ng add @angular/eslint` falla — el paquete cambió de nombre — RESUELTO
- **Problema:** `ng add @angular/eslint` no encuentra versión compatible.
- **Causa:** el paquete se renombró a `angular-eslint`.
- **Solución:** `ng add angular-eslint --skip-confirmation`.

### 9. openapi-generator necesita Java y no hay sudo — RESUELTO
- **Problema:** `openapi-generator-cli` requiere JRE; no hay Java en WSL y sudo pide contraseña.
- **Causa:** el generador es un jar; el wrapper npm solo lo descarga.
- **Solución:** JRE Temurin 21 descomprimido en `~/.local/java/jdk-21.0.11+10-jre` (sin sudo). Exportar `JAVA_HOME=$(ls -d ~/.local/java/jdk*)` y agregar `$JAVA_HOME/bin` al PATH antes de `npm run generate:api`.
- **Cómo evitarlo:** la versión del generador está pinada en `frontend/openapitools.json` (7.12.0) — no actualizar sin regenerar y compilar.

### 10. `export_openapi.py` no encuentra el módulo `app` — RESUELTO
- **Problema:** `uv run python scripts/export_openapi.py` → `ModuleNotFoundError: app`.
- **Causa:** Python pone `scripts/` como `sys.path[0]`, no la raíz del servicio.
- **Solución:** correr con `PYTHONPATH=. uv run python scripts/export_openapi.py` desde `services/transactions` (así lo hace el CI).

### 11. Grupo `docker` no aplica a sesiones abiertas — RESUELTO
- **Problema:** tras `usermod -aG docker`, `docker ps` seguía dando `permission denied`.
- **Causa:** la membresía de grupo se toma al iniciar sesión; los shells existentes no la ven.
- **Solución:** reabrir la terminal, o transitoriamente `sg docker -c "docker …"`.

### 12. GitHub Actions sobre Node 20 deprecado — RESUELTO
- **Problema:** el primer run de CI quedó verde pero con advertencias: `checkout@v4` y `setup-uv@v5` corren sobre Node 20, que GitHub retira el 16-06-2026.
- **Solución:** `actions/checkout@v5`, `astral-sh/setup-uv@v6`, `actions/setup-node@v5`.
- **Cómo evitarlo:** revisar las anotaciones de los runs aunque estén verdes; un warning de deprecación hoy es un build roto mañana.

---

## Riesgos conocidos (aún no ocurren — vigilar)

- **Mongo standalone por accidente:** si alguien levanta Mongo sin `--replSet rs0` + `rs.initiate()`, las transacciones multi-documento de Fase 4 fallan en runtime. El Compose ya lo hace bien; no levantar Mongo de otra forma.
- **Drift del cliente generado:** si se edita `contracts/openapi.yaml` sin correr `npm run generate:api`, el cliente TS queda desfasado (el candado cubre backend↔contrato, no contrato↔cliente). Regenerar siempre tras tocar el contrato.
- **`totalEstimate` null con filtros:** es deliberado (count exacto a 500k es costoso), no un bug. El UI debe tolerarlo siempre.
