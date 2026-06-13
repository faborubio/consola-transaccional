# Fase 7 — Plan aprobado y punto de retome

> **Estado (2026-06-13):** plan APROBADO, **sin código aún**. Árbol de git limpio
> (Fase 6 cerrada/pusheada/CI verde). Retomar por el **Entregable 1 (e2e Playwright)**.
> Se pausó justo antes de `npm i -D @playwright/test`.

## Dónde quedamos / orden de retome

1. **Entregable 1 — E2e Playwright** ← EMPEZAR AQUÍ
2. Entregable 2 — k6 load test
3. Entregable 3 — README narrativa
4. Entregable 4 — Compose de producción (edge + Caddy/DuckDNS + hardening)
5. Entregable 5 — Despliegue GCP con CD (necesita auth del usuario)
6. Entregable 6 — Pasada de seguridad

Trabajo local primero (E1–E4 + workflow CD), verificable sin GCP; el despliegue en la
VM se coordina con el usuario al final.

## Qué necesito del usuario (para el despliegue, sin prisa)

- `gcloud auth login` hecho + **project id** de GCP (free trial: ~USD 300, 81 días).
- Subdominio de **DuckDNS** + su **token**.
- ¿Reutilizar VM/demo existente o provisiono una fresca **e2-standard-2** (2 vCPU/8GB)?

## Decisiones acordadas (no re-preguntar)

- Demo en **GCP Compute Engine**, VM **e2-standard-2 (2 vCPU/8GB)** + docker-compose,
  **seed 500k**.
- TLS con **Caddy + DuckDNS** (Let's Encrypt automático, HTTP-01). NO sslip.io, NO
  dominio pago.
- **CD real**: GitHub Actions → **Artifact Registry** → deploy por SSH a la VM
  (auth GH→GCP por Workload Identity Federation; fallback SA key documentado).
- Imágenes se construyen **en CI** y la VM hace `pull` (compilar Angular en 8GB podría
  dar OOM, y es más producción).
- e2e corre **en CI** (Playwright necesita libs de navegador con sudo; el WSL2 no
  tiene) y **contra la imagen edge** (el artefacto real same-origin).

## Ya hecho en fases previas (NO rehacer)

Los dos primeros bullets del plan de Fase 7 ya están desde Fase 4:
`services/transactions/tests/test_state_machine.py` (20 combinaciones estado×acción) y
`test_transitions.py` (camino feliz, transición inválida, versión stale, reuso de
idempotency-key, segregación, fail-closed sin Redis).

---

## Entregable 1 — E2e con Playwright (contra el artefacto real)

Camino feliz: **login → listado → filtro → detalle → transición**.

Selectores ya investigados:
- Login: inputs `#username` / `#password`, botón "Ingresar". Demo: `supervisor1` /
  `Demo1234!`.
- Filtro estado: checkbox `#st-EN_REVISION` (id = `'st-' + s`); al togglear, el estado
  va a la URL (`?status=EN_REVISION`).
- Listado: filas `<tr [routerLink]="['/transactions', txn.id]">`, ID en `<code>`.
- Detalle: badge de estado `<span class="badge fs-6">{{ txn.status }}</span>`; botones
  de acción solo si `isSupervisor && actionsFor(status)` — EN_REVISION → "Aprobar" /
  "Rechazar". APROBAR no pide `reason`.

Plan: `playwright.config.ts` + `frontend/e2e/flujo-feliz.spec.ts`. Corre contra la
imagen edge (compose). `baseURL` por env (`E2E_BASE_URL`, default
`http://localhost:8080`). Job de CI `e2e` (`npx playwright install --with-deps`).
`make e2e`. Selectores estables (`#id` + `data-testid` puntuales donde el DOM sea
ambiguo).

**Archivos:** `frontend/package.json`, `frontend/playwright.config.ts` (nuevo),
`frontend/e2e/*.spec.ts` (nuevo), `Makefile`, `.github/workflows/ci.yml`.

## Entregable 2 — Load testing con k6

`infra/load/listado.js`: login una vez → camino caliente `GET /api/transactions` con
filtros indexables (estado + rango de fecha) + paginación por cursor; stages + thresholds
(p95, error rate). Se mide **en la VM** (e2-standard-2, 500k) y se publican p95/throughput
+ entorno en el README. `make load` (URL parametrizable).

## Entregable 3 — README narrativa de decisiones

Reestructurar a *pregunta → por qué*: RS256 vs HMAC; máquina de estados como datos;
cursor compuesto vs offset; SET NX idempotencia; replica set día uno; bases separadas;
**qué NO construí y por qué**. Añadir link de demo, números k6 con entorno, e2e y
Schemathesis. Tono honesto.

## Entregable 4 — Compose de producción (la VM)

`infra/docker-compose.prod.yml` + `infra/Caddyfile` (+ `infra/gcp/consola.service`
systemd, `infra/gcp/reseed.cron`):
- gateway = **imagen edge** (SPA + proxy /api).
- **Caddy al frente** (:443/:80 → edge:8080), TLS automático para el dominio DuckDNS.
- **NO publicar Mongo/Redis** (`ports: []`) — hoy el base publica 27017/6379; en una VM
  pública es una base abierta a internet. **Crítico.**
- Higiene prod: `restart: unless-stopped`, **límites de memoria por contenedor**,
  **rotación de logs** Docker, **systemd** (levanta al boot).
- **Reset periódico de datos demo** (cron) para que las mutaciones públicas no ensucien
  la demo. Datos ficticios, etiquetados.
- (Sugerencia de estructura: un `docker-compose.edge.yml` con el gateway=edge,
  compartido por e2e y prod; prod stackea Caddy/hardening encima.)

## Entregable 5 — Despliegue GCP con CD

- `gcloud` CLI local sin sudo (tarball en `~/`). Usuario hace `gcloud auth login` + set
  project.
- `infra/gcp/provision.sh`: `gcloud compute instances create` e2-standard-2 (Ubuntu
  22.04, 30GB); **firewall mínimo** (22 solo desde la IP del usuario; 80/443 público);
  startup-script instala Docker. Apuntar A record de DuckDNS a la IP.
- **Artifact Registry**: repo Docker; las 3 imágenes se construyen en CI y se empujan.
- `.github/workflows/deploy.yml` (push a main/tag): build+push a AR → `gcloud compute
  ssh` → `docker compose ... pull && up -d`. Auth por **WIF** (fallback SA key).
- `make gcp-up` / `gcp-deploy` / `gcp-down`.

## Entregable 6 — Pasada de seguridad

`/security-review` sobre el diff: datastores no expuestos, firewall mínimo, rate-limit,
credenciales demo etiquetadas, claves JWT en la VM (no en git/imagen), sin debug, WIF.
Verificar con `ss`/`nmap` que solo 22/80/443 abiertos. Documentar "entorno demo".

---

## Verificación (hito de Fase 7)

1. e2e verde en CI (login→listado→filtro→detalle→transición contra la imagen edge).
2. k6 con números reales en la VM (p95/throughput + entorno en README).
3. Demo pública `https://<sub>.duckdns.org` navegable, TLS válido.
4. CD: push a main reconstruye → Artifact Registry → redespliega la VM.
5. README: un desconocido entiende en 30s y lee el porqué.
6. Regresión: `make test` + `drift` + `schemathesis` verdes.

## Riesgos / notas

- Playwright sin sudo (WSL2): e2e en CI; local solo vía Docker.
- Build Angular en la VM = OOM → imágenes en CI + pull en la VM.
- gcloud auth interactivo: el usuario lo corre una vez.
- Datastores expuestos por defecto: el override prod DEBE cerrar 27017/6379 — verificar
  con `ss`/`nmap`.
- Demo mutable: reset periódico la mantiene limpia. `make gcp-down` para no quemar
  crédito.
- DuckDNS/Caddy: el subdominio debe resolver a la IP antes de pedir el cert (HTTP-01).
