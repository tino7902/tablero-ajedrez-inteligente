"""Tests de parsear_movimiento (tablero/src/tablero/logica/notacion.py).

No requieren hardware. Cubren los dos idiomas de notación, UCI, y la distinción entre
"no se entiende lo que escribiste" y "se entiende pero es ilegal".
"""

import chess
import pytest

from tablero.logica.notacion import (
    Idioma,
    MovimientoIlegalError,
    NotacionInvalidaError,
    parsear_movimiento,
)


@pytest.mark.parametrize(
    ("texto", "uci"),
    [
        ("e4", "e2e4"),
        ("Cf3", "g1f3"),
        ("e2e4", "e2e4"),
        ("E2E4", "e2e4"),
        (" e4 ", "e2e4"),
    ],
)
def test_notacion_espanola_y_uci(texto, uci):
    assert parsear_movimiento(texto, chess.Board(), Idioma.ESPANOL) == chess.Move.from_uci(uci)


@pytest.mark.parametrize(("texto", "uci"), [("e4", "e2e4"), ("Nf3", "g1f3"), ("e2e4", "e2e4")])
def test_notacion_inglesa(texto, uci):
    assert parsear_movimiento(texto, chess.Board(), Idioma.INGLES) == chess.Move.from_uci(uci)


def test_la_r_es_rey_en_espanol_y_torre_en_ingles():
    # Rey en e1 con f1/g1 libres para enrocar, torre blanca en a3 con a4 libre.
    board = chess.Board("4k3/8/8/8/8/R7/8/4K3 w - - 0 1")

    assert parsear_movimiento("Re2", board, Idioma.ESPANOL) == chess.Move.from_uci("e1e2")
    assert parsear_movimiento("Ra4", board, Idioma.INGLES) == chess.Move.from_uci("a3a4")
    # Y la lectura del otro idioma no se cuela: en español 'Ra4' sería un rey a a4.
    with pytest.raises(MovimientoIlegalError):
        parsear_movimiento("Ra4", board, Idioma.ESPANOL)


@pytest.mark.parametrize("texto", ["O-O", "0-0", "o-o"])
def test_enroque_corto_en_cualquier_escritura(texto):
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert parsear_movimiento(texto, board, Idioma.ESPANOL) == chess.Move.from_uci("e1g1")


def test_promocion_en_san_y_en_uci_con_letras_espanolas():
    board = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")

    assert parsear_movimiento("e8=D", board, Idioma.ESPANOL).promotion == chess.QUEEN
    assert parsear_movimiento("e7e8d", board, Idioma.ESPANOL).promotion == chess.QUEEN
    assert parsear_movimiento("e7e8c", board, Idioma.ESPANOL).promotion == chess.KNIGHT
    assert parsear_movimiento("e7e8n", board, Idioma.INGLES).promotion == chess.KNIGHT


def test_letra_de_promocion_del_otro_idioma_no_se_acepta():
    board = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    with pytest.raises(NotacionInvalidaError):
        parsear_movimiento("e7e8q", board, Idioma.ESPANOL)


def test_notacion_del_otro_idioma_es_invalida_no_ilegal():
    with pytest.raises(NotacionInvalidaError):
        parsear_movimiento("Cf3", chess.Board(), Idioma.INGLES)


@pytest.mark.parametrize("texto", ["", "xyz", "e9", "hola", "e2e9"])
def test_texto_que_no_es_un_movimiento(texto):
    with pytest.raises(NotacionInvalidaError):
        parsear_movimiento(texto, chess.Board(), Idioma.ESPANOL)


@pytest.mark.parametrize("texto", ["Dh5", "e2e5", "a3a4"])
def test_movimiento_entendido_pero_ilegal(texto):
    with pytest.raises(MovimientoIlegalError):
        parsear_movimiento(texto, chess.Board(), Idioma.ESPANOL)


def test_movimiento_ambiguo_pide_desambiguar():
    # Los caballos de b1 y f1 pueden ir los dos a d2.
    board = chess.Board("4k3/8/8/8/8/8/8/1N3N1K w - - 0 1")
    with pytest.raises(NotacionInvalidaError, match="ambiguo"):
        parsear_movimiento("Cd2", board, Idioma.ESPANOL)
    assert parsear_movimiento("Cbd2", board, Idioma.ESPANOL) == chess.Move.from_uci("b1d2")
