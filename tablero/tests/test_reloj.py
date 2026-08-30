"""Tests de RelojAjedrez (tablero/src/tablero/logica/reloj.py).

No requieren hardware: el paso del tiempo se controla con la fixture `tiempo`
(`RelojFalso`, en `conftest.py`) en vez de dormir, así los tests son deterministas y corren en milisegundos.
"""

import chess
import pytest

from tablero.logica.reloj import RelojAjedrez, formatear_tiempo


def test_arranca_con_el_turno_en_blancas_y_los_dos_tiempos_completos(tiempo):
    reloj = RelojAjedrez(300, tiempo)

    assert reloj.turno == chess.WHITE
    assert reloj.restante(chess.WHITE) == 300
    assert reloj.restante(chess.BLACK) == 300
    assert not reloj.tiempo_agotado


def test_solo_descuenta_del_jugador_que_tiene_el_turno(tiempo):
    reloj = RelojAjedrez(300, tiempo)

    tiempo.avanzar(10)
    reloj.actualizar()

    assert reloj.restante(chess.WHITE) == 290
    assert reloj.restante(chess.BLACK) == 300


def test_el_turno_pasa_al_pulsar_y_el_tiempo_cambia_de_lado(tiempo):
    reloj = RelojAjedrez(300, tiempo)

    tiempo.avanzar(10)
    reloj.actualizar()
    assert reloj.pulsar(chess.WHITE)
    tiempo.avanzar(4)
    reloj.actualizar()

    assert reloj.turno == chess.BLACK
    assert reloj.restante(chess.WHITE) == 290
    assert reloj.restante(chess.BLACK) == 296


def test_pulsar_el_boton_del_jugador_que_no_tiene_el_turno_no_hace_nada(tiempo):
    reloj = RelojAjedrez(300, tiempo)

    assert not reloj.pulsar(chess.BLACK)
    assert reloj.turno == chess.WHITE


def test_avanzar_descuenta_tiempo_simulado_sin_cobrar_dos_veces(tiempo):
    reloj = RelojAjedrez(300, tiempo)

    tiempo.avanzar(5)  # tiempo real que pasó antes del avance manual
    reloj.avanzar(100)
    reloj.actualizar()

    assert reloj.restante(chess.WHITE) == 200


def test_al_agotarse_el_tiempo_queda_congelado_en_el_perdedor(tiempo):
    reloj = RelojAjedrez(30, tiempo)

    assert reloj.avanzar(31)
    assert reloj.tiempo_agotado
    assert reloj.perdedor == chess.WHITE
    assert reloj.restante(chess.WHITE) == 0
    # Ya agotado: no se sigue descontando ni se puede cambiar de turno.
    assert not reloj.avanzar(10)
    assert not reloj.pulsar(chess.WHITE)
    assert reloj.turno == chess.WHITE
    assert reloj.restante(chess.BLACK) == 30


def test_solo_avisa_una_vez_que_se_agoto_el_tiempo(tiempo):
    reloj = RelojAjedrez(10, tiempo)

    assert reloj.avanzar(20) is True
    assert reloj.avanzar(1) is False


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [(300, "05:00"), (299.999, "05:00"), (60, "01:00"), (59.2, "01:00"), (0.4, "00:01"), (0, "00:00"), (-5, "00:00")],
)
def test_formatear_tiempo_redondea_hacia_arriba_y_no_baja_de_cero(segundos, esperado):
    assert formatear_tiempo(segundos) == esperado
