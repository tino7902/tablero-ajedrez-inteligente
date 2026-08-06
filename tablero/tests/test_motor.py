"""Tests de MotorStockfish (tablero/src/tablero/motor/stockfish.py).

Requieren el binario `stockfish` instalado en el sistema; el módulo entero
se saltea (`pytestmark`) si no está en PATH, para no romper en máquinas o CI
sin el binario. Los tiempos por jugada se mantienen bajos (0.1-0.2s) porque
las posiciones usadas no necesitan más para resolverse.
"""

import shutil

import chess
import pytest

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
