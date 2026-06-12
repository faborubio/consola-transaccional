# Comandos del día a día. `make help` lista todo.
SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(HOME)/.nvm/versions/node/v24.16.0/bin:$(PATH)
COMPOSE := docker compose -f infra/docker-compose.yml
DRIFT_PATHS := ^/(health$$|transactions$$|transactions/\{id\}(/audit)?$$)

.PHONY: help up down seed test test-backend test-frontend lint drift front generate-api keys

keys: ## Genera el par RS256 local en infra/keys (fuera de git)
	mkdir -p infra/keys
	test -f infra/keys/jwt-private.pem || openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out infra/keys/jwt-private.pem
	openssl pkey -in infra/keys/jwt-private.pem -pubout -out infra/keys/jwt-public.pem
	@echo "Claves en infra/keys/ — solo auth monta la privada"

help: ## Lista los comandos disponibles
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

up: ## Levanta el stack completo (gateway + servicios + Mongo RS + Redis)
	$(COMPOSE) up -d --build

down: ## Baja el stack (conserva el volumen de datos)
	$(COMPOSE) down

seed: ## Siembra 500k transacciones (borra las existentes)
	cd infra/seed && uv run seed.py --drop

test: test-backend test-frontend ## Toda la suite

test-backend: ## Lint + tests de ambos servicios (los de Mongo se saltan si no está)
	cd services/transactions && uv run ruff check . && uv run pytest -q
	cd services/auth && uv run ruff check . && uv run pytest -q

test-frontend: ## Lint + tests + build del frontend
	cd frontend && npx ng lint && npx ng test && npx ng build

drift: ## Candado anti-drift: contrato vs OpenAPI runtime de ambos servicios
	cd services/transactions && PYTHONPATH=. uv run python scripts/export_openapi.py > /tmp/txn-openapi.json
	uv run --script infra/ci/check_drift.py contracts/openapi.yaml /tmp/txn-openapi.json --match-path '$(DRIFT_PATHS)'
	cd services/auth && PYTHONPATH=. uv run python scripts/export_openapi.py > /tmp/auth-openapi.json
	uv run --script infra/ci/check_drift.py contracts/openapi.yaml /tmp/auth-openapi.json --match-path '^/auth/'

front: ## Dev server de Angular en :4200
	cd frontend && npm start

generate-api: ## Regenera el cliente TS desde contracts/openapi.yaml (requiere JRE local)
	cd frontend && JAVA_HOME=$$(ls -d $(HOME)/.local/java/jdk*) PATH=$$JAVA_HOME/bin:$$PATH npm run generate:api
