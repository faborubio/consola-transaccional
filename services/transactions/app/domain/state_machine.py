"""Máquina de estados como DATOS, no como if/else.

Todas las transiciones válidas viven en un solo mapa: testeable
exhaustivamente con un loop sobre estado × acción (incluidas las
prohibidas), y el estado solo puede cambiar de forma declarada aquí.
Una cadena de if/elif crece sin control y deja combinaciones sin probar.
"""

from app.domain.models import TransactionStatus as S
from app.domain.models import TransitionAction as A

TRANSITIONS: dict[S, dict[A, S]] = {
    S.PENDIENTE: {
        A.APROBAR: S.APROBADA,
        A.RECHAZAR: S.RECHAZADA,
        A.ENVIAR_A_REVISION: S.EN_REVISION,
    },
    S.EN_REVISION: {
        A.APROBAR: S.APROBADA,
        A.RECHAZAR: S.RECHAZADA,
    },
    S.APROBADA: {
        A.REVERTIR: S.REVERTIDA,
    },
    # Estados terminales: ninguna acción válida.
    S.RECHAZADA: {},
    S.REVERTIDA: {},
}

# Acciones que exigen motivo (control de negocio, no de esquema).
REQUIRES_REASON: frozenset[A] = frozenset({A.RECHAZAR, A.REVERTIR})


def next_status(current: S, action: A) -> S | None:
    """Estado siguiente, o None si la transición es inválida."""
    return TRANSITIONS[current].get(action)
