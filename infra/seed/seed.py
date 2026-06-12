# /// script
# requires-python = ">=3.12"
# dependencies = ["pymongo>=4.10", "faker>=30"]
# ///
"""Siembra transacciones a volumen con distribuciones realistas.

- insert_many por lotes (one-by-one tarda horas a 500k).
- Estados sesgados (mayoría APROBADA), montos log-normales, fechas en 12 meses.

Uso: uv run seed.py [--count 500000] [--uri mongodb://localhost:27017/?replicaSet=rs0&directConnection=true]
"""

import argparse
import math
import random
import secrets
import time
from datetime import UTC, datetime, timedelta

from faker import Faker
from pymongo import MongoClient

BATCH_SIZE = 10_000

# Sesgo realista: el grueso aprobado, una minoría operativa pendiente/en revisión.
STATUS_WEIGHTS = {
    "APROBADA": 0.70,
    "RECHAZADA": 0.12,
    "PENDIENTE": 0.10,
    "EN_REVISION": 0.05,
    "REVERTIDA": 0.03,
}
TYPE_WEIGHTS = {"TRANSFERENCIA": 0.45, "PAGO": 0.35, "ABONO": 0.15, "REVERSA": 0.05}
CURRENCY_WEIGHTS = {"CLP": 0.80, "USD": 0.15, "EUR": 0.05}
MAKERS = [f"usr_{i:02d}" for i in range(1, 9)]
CHECKERS = [f"usr_{i:02d}" for i in range(9, 13)]


def make_parties(fake: Faker, n: int = 400) -> list[dict]:
    return [
        {
            "accountId": f"CL-{random.randint(1, 999):03d}-{random.randint(10_000_000, 99_999_999)}",
            "name": fake.company(),
        }
        for _ in range(n)
    ]


def log_normal_amount(currency: str) -> float:
    # mediana ~ e^mu; cola larga de montos grandes, como una cartera real.
    mu, sigma = (13.0, 1.2) if currency == "CLP" else (6.5, 1.1)
    return round(math.exp(random.gauss(mu, sigma)), 2)


def weighted(choices: dict[str, float]) -> str:
    return random.choices(list(choices), weights=list(choices.values()), k=1)[0]


def search_keys(source: dict, destination: dict) -> list[str]:
    """Claves normalizadas para búsqueda por prefijo (índice multikey).

    Una regex sin anclar sobre los nombres no puede usar índices; el prefijo
    anclado sobre este campo en minúsculas sí.
    """
    return sorted(
        {
            source["name"].lower(),
            destination["name"].lower(),
            source["accountId"].lower(),
            destination["accountId"].lower(),
        }
    )


def build_txn(parties: list[dict], now: datetime) -> dict:
    status = weighted(STATUS_WEIGHTS)
    currency = weighted(CURRENCY_WEIGHTS)
    created = now - timedelta(seconds=random.uniform(0, 365 * 24 * 3600))
    source, destination = random.sample(parties, 2)
    txn = {
        "_id": f"txn_{secrets.token_hex(6)}",
        "amount": log_normal_amount(currency),
        "currency": currency,
        "type": weighted(TYPE_WEIGHTS),
        "status": status,
        "version": 1,
        "source": source,
        "destination": destination,
        "searchKeys": search_keys(source, destination),
        "reference": f"Operación {random.randint(1000, 99999)}",
        "createdBy": random.choice(MAKERS),
        "reviewedBy": None,
        "createdAt": created,
        "updatedAt": created,
        "metadata": {"channel": random.choice(["WEB", "API", "BATCH", "SUCURSAL"])},
    }
    if status in ("APROBADA", "RECHAZADA", "REVERTIDA"):
        txn["reviewedBy"] = random.choice(CHECKERS)
        txn["updatedAt"] = created + timedelta(seconds=random.uniform(60, 48 * 3600))
        txn["version"] = 2
    return txn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500_000)
    parser.add_argument(
        "--uri",
        default="mongodb://localhost:27017/?replicaSet=rs0&directConnection=true",
    )
    parser.add_argument("--db", default="transactions_db")
    parser.add_argument("--drop", action="store_true", help="Borra la colección antes de sembrar")
    args = parser.parse_args()

    fake = Faker("es_CL")
    client = MongoClient(args.uri)
    col = client[args.db]["transactions"]

    if args.drop:
        col.drop()
        print("Colección transactions borrada.")

    parties = make_parties(fake)
    now = datetime.now(UTC)
    start = time.monotonic()
    inserted = 0
    while inserted < args.count:
        batch = [build_txn(parties, now) for _ in range(min(BATCH_SIZE, args.count - inserted))]
        col.insert_many(batch, ordered=False)
        inserted += len(batch)
        elapsed = time.monotonic() - start
        print(f"  {inserted:>7,} / {args.count:,}  ({elapsed:.1f}s)", flush=True)

    print(f"Listo: {inserted:,} transacciones en {time.monotonic() - start:.1f}s")
    print("Creando índices ESR…")
    col.create_index([("createdAt", -1), ("_id", -1)])
    col.create_index([("amount", -1), ("_id", -1)])
    col.create_index([("status", 1), ("createdAt", -1), ("_id", -1)])
    col.create_index([("status", 1), ("amount", -1), ("_id", -1)])
    col.create_index([("searchKeys", 1)])
    print("Índices listos.")


if __name__ == "__main__":
    main()
