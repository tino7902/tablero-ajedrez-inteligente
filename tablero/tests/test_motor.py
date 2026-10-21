"""Tests de MotorStockfish (tablero/src/tablero/motor/stockfish.py).

Requieren el binario `stockfish` instalado en el sistema; el módulo entero
se saltea (`pytestmark`) si no está en PATH, para no romper en máquinas o CI
sin el binario. Los tiempos por jugada se mantienen bajos (0.1-0.2s) porque
las posiciones usadas no necesitan más para resolverse.
"""

import os
import shutil

import chess
import pytest

from tablero import config
from tablero.motor.stockfish import MotorStockfish

pytestmark = pytest.mark.skipif(
    shutil.which("stockfish") is None, reason="requiere el binario de stockfish instalado"
)


def test_mejor_movimiento_desde_posicion_inicial_es_legal():
    board = chess.Board()
    with MotorStockfish(tiempo_por_jugada=0.1) as motor:
        movimiento = motor.mejor_movimiento(board)
    assert movimiento in board.legal_moves


def test_encuentra_mate_en_uno():
    board = chess.Board("6k1/5ppp/8/8/8/8/8/R6K w - - 0 1")
    with MotorStockfish(tiempo_por_jugada=0.2) as motor:
        movimiento = motor.mejor_movimiento(board)
    board.push(movimiento)
    assert board.is_checkmate()


def test_cerrar_no_levanta_excepcion():
    motor = MotorStockfish(tiempo_por_jugada=0.1)
    motor.cerrar()


@pytest.mark.parametrize("nivel", list(config.NIVELES_MAGNUS))
def test_cada_nivel_configura_skill_level_y_devuelve_una_jugada_legal(nivel):
    board = chess.Board()
    with MotorStockfish(nivel=nivel) as motor:
        aplicado = motor._engine.protocol.config["Skill Level"]
        movimiento = motor.mejor_movimiento(board)

    assert aplicado == config.NIVELES_MAGNUS[nivel].skill_level
    assert movimiento in board.legal_moves


def test_nivel_desconocido_da_error_antes_de_abrir_el_motor():
    with pytest.raises(ValueError, match="imposible"):
        MotorStockfish(nivel="imposible")


def test_el_motor_corre_en_su_propio_grupo_de_procesos():
    # Así un Ctrl+C en la terminal no mata a Stockfish antes de que Python lo cierre.
    with MotorStockfish(tiempo_por_jugada=0.1) as motor:
        pid = motor._engine.transport.get_pid()
        assert os.getpgid(pid) != os.getpgid(0)
