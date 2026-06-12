"""Exporta el OpenAPI que FastAPI emite, sin levantar el servidor.

Insumo del candado anti-drift: CI lo diffea contra contracts/openapi.yaml.
Uso: uv run python scripts/export_openapi.py > openapi-runtime.json
"""

import json
import sys

from app.main import app

json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
