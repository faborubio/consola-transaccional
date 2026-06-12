# Consola de Operaciones Transaccionales

Back-office bancario de portafolio (objetivo: oferta Desarrollador Angular en SONDA).
Plan por fases: `docs/plan-consola-transaccional-sonda.md` — seguirlo en orden; cada
fase cierra con su hito verificable. Estado actual: **Fase 0 cerrada y validada**.

## Reglas duras del proyecto

- **`contracts/openapi.yaml` es la fuente de verdad.** Todo cambio de API empieza
  ahí, luego se implementa en FastAPI y se regenera el cliente (`npm run generate:api`
  en `frontend/`). El candado anti-drift en CI (`infra/ci/check_drift.py`) rompe el
  build si el runtime diverge del contrato.
- **`frontend/src/app/api-client/` es generado:** no se edita, no se lintea; los
  componentes consumen la capa propia en `frontend/src/app/services/`.
- Al implementar endpoints nuevos, ampliar el `--match-path` del job `anti-drift`
  en `.github/workflows/ci.yml`.
- Toda ruta FastAPI con parámetros declara `responses={422: {"model": Error}}` y el
  contrato lista ese 422 (FastAPI mete su propio 422 si no).
- Mongo siempre en replica set (`infra/docker-compose.yml` ya lo hace); nunca
  standalone — las transacciones multi-documento de Fase 4 lo requieren.
- Angular queda en **v21** hasta que ng-bootstrap soporte v22.
- Frontend: filtros en la URL (query params), `async pipe`/`takeUntilDestroyed`,
  sin `.subscribe()` sueltos, paginación clásica (no virtual scroll).

## Entorno (WSL2 Ubuntu 24.04)

- Node/uv/Java se instalaron sin sudo. En comandos no interactivos anteponer:
  `export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"`
  (el PATH hereda el node de Windows en `/mnt/c` — nunca usarlo).
- Para regenerar el cliente: `export JAVA_HOME=$(ls -d ~/.local/java/jdk*)` y
  `$JAVA_HOME/bin` al PATH.
- Docker Engine nativo en WSL con systemd. Si un shell da `permission denied`
  con docker: `sg docker -c "…"` o reabrir la terminal.

## Comandos

```bash
docker compose -f infra/docker-compose.yml up -d --build   # stack completo :8080
cd infra/seed && uv run seed.py --drop                     # 500k transacciones
cd services/transactions && uv run pytest -q && uv run ruff check .
cd frontend && npm start                                   # consola :4200
cd frontend && npx ng lint && npx ng test && npx ng build
# Candado anti-drift local (igual que CI):
cd services/transactions && PYTHONPATH=. uv run python scripts/export_openapi.py > /tmp/txn.json
uv run --script infra/ci/check_drift.py contracts/openapi.yaml /tmp/txn.json \
  --match-path '^/(health$|transactions$|transactions/\{id\}(/audit)?$)'
```

## Registro de problemas resueltos (leer antes de depurar)

@docs/problemas-resueltos.md

Cuando se resuelva un problema no trivial nuevo, **agregar la entrada** a ese
archivo (Problema → Causa → Solución → Cómo evitarlo) en la misma sesión.
