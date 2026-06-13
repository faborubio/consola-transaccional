"""Cobertura EXHAUSTIVA de la máquina de estados: un loop sobre todas las
combinaciones estado × acción — no 20 tests individuales que dejan huecos."""

import pytest

from app.domain.models import TransactionStatus as S
from app.domain.models import TransitionAction as A
from app.domain.state_machine import TRANSITIONS, next_status

VALID = {
    (S.PENDIENTE, A.APROBAR): S.APROBADA,
    (S.PENDIENTE, A.RECHAZAR): S.RECHAZADA,
    (S.PENDIENTE, A.ENVIAR_A_REVISION): S.EN_REVISION,
    (S.EN_REVISION, A.APROBAR): S.APROBADA,
    (S.EN_REVISION, A.RECHAZAR): S.RECHAZADA,
    (S.APROBADA, A.REVERTIR): S.REVERTIDA,
}


@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize("action", list(A))
def test_todas_las_combinaciones(status: S, action: A):
    """5 estados × 4 acciones = 20 combinaciones: 6 válidas, 14 prohibidas."""
    expected = VALID.get((status, action))
    assert next_status(status, action) == expected


def test_el_mapa_cubre_todos_los_estados():
    """Un estado nuevo sin entrada en el mapa debe romper ESTE test, no producción."""
    assert set(TRANSITIONS.keys()) == set(S)


def test_estados_terminales_sin_salida():
    assert TRANSITIONS[S.RECHAZADA] == {}
    assert TRANSITIONS[S.REVERTIDA] == {}


def test_ninguna_transicion_vuelve_a_pendiente():
    """PENDIENTE es solo estado inicial: nadie puede 'des-procesar'."""
    destinos = {dest for trans in TRANSITIONS.values() for dest in trans.values()}
    assert S.PENDIENTE not in destinos
