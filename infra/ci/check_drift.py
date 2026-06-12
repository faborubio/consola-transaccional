# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Candado anti-drift: contracts/openapi.yaml vs el OpenAPI que FastAPI emite.

Por qué no basta oasdiff a secas: el contrato es OpenAPI 3.0.3 (`nullable: true`)
y FastAPI emite 3.1 (`anyOf: [X, {type: null}]`). Son semánticamente idénticos
pero sintácticamente distintos. Este script deref-ea ambos documentos, los
canonicaliza (nullable/anyOf, defaults implícitos, campos cosméticos) y compara
la estructura path por path. Cualquier diferencia real — parámetro, tipo,
required, enum, código de respuesta — rompe el build.

Uso:
  uv run check_drift.py CONTRATO RUNTIME --match-path '^/(health$|transactions)'
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

COSMETIC_KEYS = {"description", "example", "examples", "title", "summary"}
NULLABLE = "x-nullable-normalized"


def load(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text) if path.endswith(".json") else yaml.safe_load(text)


def deref(node: Any, root: dict, stack: tuple[str, ...] = ()) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref in stack:  # ciclo: se deja la referencia como marcador estable
                return {"$circular": ref}
            target: Any = root
            for part in ref.removeprefix("#/").split("/"):
                target = target[part]
            return deref(target, root, (*stack, ref))
        return {k: deref(v, root, stack) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(v, root, stack) for v in node]
    return node


def normalize(node: Any, *, in_parameter: bool = False) -> Any:
    if isinstance(node, list):
        return [normalize(v, in_parameter=in_parameter) for v in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in COSMETIC_KEYS:
            continue
        if key == "default" and value is None:
            continue
        if key == "required" and value is False:  # required: false es el default
            continue
        if in_parameter and key == "style" and value == "form":
            continue
        if in_parameter and key == "explode" and value is True:
            continue
        out[key] = value

    # 3.0: nullable: true → marcador canónico
    if out.pop("nullable", False):
        out[NULLABLE] = True

    # 3.1: anyOf [X, {type: null}] → X + marcador canónico.
    # Se re-normaliza el resultado: la variante fusionada trae sus propias
    # claves cosméticas/anyOf anidados que el primer pase no vio.
    if "anyOf" in out:
        variants = [v for v in out["anyOf"] if v != {"type": "null"}]
        if len(variants) < len(out["anyOf"]) and len(variants) == 1:
            merged = {**variants[0], **{k: v for k, v in out.items() if k != "anyOf"}}
            merged[NULLABLE] = True
            return normalize(merged, in_parameter=in_parameter)

    # JSON tiene un solo tipo numérico; format double/float es anotación sin
    # efecto observable (pydantic no lo emite para float).
    if out.get("type") == "number" and out.get("format") in {"double", "float"}:
        del out["format"]

    out = {k: normalize(v, in_parameter=in_parameter) for k, v in out.items()}

    if "parameters" in out and isinstance(out["parameters"], list):
        params = [normalize(p, in_parameter=True) for p in node["parameters"]]
        out["parameters"] = sorted(params, key=lambda p: (p.get("in", ""), p.get("name", "")))

    # En query params la nulabilidad no es observable (el param simplemente se omite)
    if in_parameter and "schema" in out and isinstance(out["schema"], dict):
        out["schema"].pop(NULLABLE, None)

    if "required" in out and isinstance(out["required"], list):
        out["required"] = sorted(out["required"])

    return out


def diff(a: Any, b: Any, path: str, problems: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(a.keys() | b.keys()):
            if key not in a:
                problems.append(f"{path}/{key}: solo en runtime → {json.dumps(b[key])[:120]}")
            elif key not in b:
                problems.append(f"{path}/{key}: solo en contrato → {json.dumps(a[key])[:120]}")
            else:
                diff(a[key], b[key], f"{path}/{key}", problems)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            problems.append(f"{path}: largo distinto (contrato {len(a)}, runtime {len(b)})")
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            diff(x, y, f"{path}[{i}]", problems)
    elif a != b:
        problems.append(f"{path}: contrato={json.dumps(a)} runtime={json.dumps(b)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("runtime")
    parser.add_argument(
        "--match-path",
        default=".*",
        help="Regex de paths a comparar (la superficie ya implementada por el servicio)",
    )
    args = parser.parse_args()

    contract_doc = load(args.contract)
    runtime_doc = load(args.runtime)
    matcher = re.compile(args.match_path)

    def surface(doc: dict) -> dict:
        paths = {p: v for p, v in doc.get("paths", {}).items() if matcher.search(p)}
        return {
            "paths": normalize(deref(paths, doc)),
            "security": doc.get("security"),
        }

    problems: list[str] = []
    diff(surface(contract_doc), surface(runtime_doc), "", problems)

    if problems:
        print(f"DRIFT DETECTADO ({len(problems)} diferencias) entre contrato y runtime:\n")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(f"Sin drift: contrato y runtime coinciden en los paths que matchean "
          f"{args.match_path!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
