# Fase 7 — Estado y trabajo pendiente

> **Estado (2026-06-14):** Fase 7 **CERRADA Y AUDITADA**. Demo pública EN VIVO:
> **https://traconsole.duckdns.org** (GCP e2-standard-2 + docker-compose, Caddy/TLS sobre
> DuckDNS, 500k docs). e2e Playwright verde en CI; k6 **p95 26 ms sobre 500k, 0% errores**;
> README como narrativa de decisiones. Auditoría aplicada en vivo. Todo en GitHub, CI
> verde, árbol limpio. Entregables E1–E4 + demo + auditoría: HECHOS (detalle histórico abajo).

## ⏭️ Pendiente para la próxima sesión

### A. CD — GitHub Actions → Artifact Registry → VM (el usuario lo eligió)

Hoy la VM **construye las imágenes localmente** (`deploy-on-vm.sh` → `up -d --build`).
El CD las construye en CI, las empuja a **Artifact Registry**, y la VM hace `pull`. Pasos:

1. **Refactor de imágenes (local, testeable SIN GCP):** añadir
   `image: ${REGISTRY:-consola}/<svc>:${TAG:-local}` a `auth`/`transactions` (base
   `infra/docker-compose.yml`) y al `gateway` (override `infra/docker-compose.edge.yml`),
   parametrizado. Dev sigue construyendo local (defaults); CI/VM usan `REGISTRY=<AR>`
   `TAG=<sha>`. **Verificar que `make up` y `make e2e` siguen funcionando.**
2. **GCP:** crear repo de Artifact Registry (docker); **service account** para que la VM
   haga `pull` (`gcloud auth configure-docker <region>-docker.pkg.dev`); auth GH→GCP por
   **Workload Identity Federation** (keyless, lo correcto) — fallback: SA key como secreto.
3. **`.github/workflows/deploy.yml`** (push a main o tag): build+push de las 3 imágenes a
   AR → `gcloud compute ssh` (o SSH con llave) a la VM → `docker compose ... pull && up -d`.
   El deploy en la VM YA es idempotente/CD-safe (no re-siembra — hallazgo #3 de auditoría).
4. `make gcp-deploy` opcional para disparo manual.

**Del usuario:** project id GCP; permiso para crear AR + SA/WIF; configurar secretos en
GitHub (o que me deje guiarlo). **La VM debe seguir ARRIBA** para que el CD deploye.

### B. Limpieza / costos

- **Quitar mi llave SSH** de la VM (Compute Engine → VM `consola` → Editar → Claves SSH →
  borrar el item `ssh-ed25519 … claude`). **OJO:** si quieres que yo siga ayudando con la
  VM (probar el CD), **DÉJALA** — la privada vive en `~/.ssh/gcp_consola` de mi entorno
  (persiste en esta máquina). Bórrala al terminar todo.
- **Costos:** la VM consume crédito mientras corre. **IP estática recomendada** (gratis si
  está adjunta a una VM corriendo) → el link y el target SSH del CD quedan estables sin
  re-apuntar DuckDNS en cada restart. Si la apagas, al reiniciar cambia la IP → re-apuntar.

### C. (Opcional) Fase 8 — roadmap v2 documentado

Solo documentación en el README: outbox + Redis Streams, `notifications`, conciliación
batch, motor de reglas. El plan: "se documenta aunque no esté construido".

## Cómo está desplegado hoy (referencia para operar la VM)

- **Deploy/redeploy:** `DOMAIN=traconsole.duckdns.org bash ~/consola/infra/gcp/deploy-on-vm.sh`
  corrido en la VM **como `fabian_rubiocs`** (clona/pull, claves, `up -d --build` con el
  override prod, siembra si vacío, force-recreate de Caddy, instala cron).
- **Acceso:** `ssh -i ~/.ssh/gcp_consola claude@traconsole.duckdns.org` (mi llave, en esta
  máquina). Para correr el deploy como fabian:
  `ssh … "sudo -u fabian_rubiocs bash -lc 'cd ~/consola && DOMAIN=traconsole.duckdns.org bash infra/gcp/deploy-on-vm.sh'"`.
- **Stack:** base + `docker-compose.edge.yml` (gateway=imagen edge) + `docker-compose.prod.yml`
  (Caddy/TLS, datastores cerrados con `!reset`, restart, mem-limits, logs).
- **GOTCHA CRÍTICO (problemas-resueltos #38):** NUNCA correr compose en la VM **sin la env
  `UID` correcta** ni **como root** — recrea `auth` como uid 1000 → no lee la clave → login
  500. La clave es 644 para mitigarlo, pero usar `deploy-on-vm.sh` como `fabian_rubiocs` es
  lo seguro. El Caddyfile es bind-mount por inodo (#37): tras `git pull`, `--force-recreate`,
  no `reload`.

---

## Decisiones acordadas (referencia histórica — ya implementadas)

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
