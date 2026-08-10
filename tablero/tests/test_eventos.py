"""Tests de RastreadorMovimientos (tablero/src/tablero/logica/eventos.py).

No requieren hardware ni binarios externos, corren en cualquier máquina. Las
lecturas de sensores se simulan a mano como `frozenset[chess.Square]`, tal como
las produciría `io/sensores.py` el día que exista.
"""

import logging

import chess
import pytest

from tablero.logica.estado_tablero import EstadoTablero
from tablero.logica.eventos import (
    RastreadorMovimientos,
    TipoEvento,
    casillas_ocupadas,
)


def _sin(ocupacion: frozenset[chess.Square], *casillas: chess.Square) -> frozenset[chess.Square]:
    return ocupacion - set(casillas)


def _con(ocupacion: frozenset[chess.Square], *casillas: chess.Square) -> frozenset[chess.Square]:
    return ocupacion | set(casillas)


def test_movimiento_legal_directo_se_aplica_y_pasa_el_turno(caplog):
    estado = EstadoTablero()
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    with caplog.at_level(logging.INFO):
        evento_levantar = rastreador.procesar_ocupacion(_sin(inicial, chess.E2))
        evento_mover = rastreador.procesar_ocupacion(_con(_sin(inicial, chess.E2), chess.E4))

    assert evento_levantar is not None
    assert evento_mover is not None
    assert evento_levantar.tipo is TipoEvento.PIEZA_LEVANTADA
    assert evento_levantar.origen == chess.E2
    assert evento_levantar.turno == chess.WHITE
    assert evento_levantar.numero_jugada == 1

    assert evento_mover.tipo is TipoEvento.MOVIMIENTO_APLICADO
    assert evento_mover.origen == chess.E2
    assert evento_mover.destino == chess.E4
    assert evento_mover.turno == chess.WHITE
    assert evento_mover.numero_jugada == 1

    assert estado.turno == chess.BLACK
    assert estado.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert "Jugada 1 (blancas)" in caplog.text
    assert "Turno pasa a negras" in caplog.text


def test_ejemplo_del_usuario_movimiento_ilegal_corregido():
    """e2 levantado -> colocado en d4 (ilegal) -> retomado -> colocado en e4 (legal)."""
    estado = EstadoTablero()
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    # t1.1: se levanta la pieza de e2.
    ev1 = rastreador.procesar_ocupacion(_sin(inicial, chess.E2))
    assert ev1 is not None
    assert ev1.tipo is TipoEvento.PIEZA_LEVANTADA
    assert ev1.origen == chess.E2

    # t1.2: se detecta la pieza en d4 -> movimiento e2-d4 ilegal.
    ev2 = rastreador.procesar_ocupacion(_con(_sin(inicial, chess.E2), chess.D4))
    assert ev2 is not None
    assert ev2.tipo is TipoEvento.MOVIMIENTO_ILEGAL_RECHAZADO
    assert ev2.origen == chess.E2
    assert ev2.destino == chess.D4
    assert estado.turno == chess.WHITE  # el turno no avanzó
    assert estado.board.piece_at(chess.E2) == chess.Piece(chess.PAWN, chess.WHITE)  # sin tocar

    # t1.3: se levanta la pieza de d4 (se retoma la corrección).
    ev3 = rastreador.procesar_ocupacion(_sin(inicial, chess.E2))
    assert ev3 is not None
    assert ev3.tipo is TipoEvento.PIEZA_LEVANTADA
    assert ev3.origen == chess.E2  # el origen lógico sigue siendo e2, no d4

    # t1.4: se detecta la pieza en e4 -> movimiento e2-e4 legal.
    ev4 = rastreador.procesar_ocupacion(_con(_sin(inicial, chess.E2), chess.E4))
    assert ev4 is not None
    assert ev4.tipo is TipoEvento.MOVIMIENTO_APLICADO
    assert ev4.origen == chess.E2
    assert ev4.destino == chess.E4
    assert estado.turno == chess.BLACK
    assert estado.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)


def test_pieza_repuesta_cancela_el_movimiento():
    estado = EstadoTablero()
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    ev1 = rastreador.procesar_ocupacion(_sin(inicial, chess.E2))
    assert ev1 is not None
    assert ev1.tipo is TipoEvento.PIEZA_LEVANTADA

    ev2 = rastreador.procesar_ocupacion(inicial)  # se repone en e2
    assert ev2 is not None
    assert ev2.tipo is TipoEvento.PIEZA_REPUESTA
    assert ev2.origen == chess.E2
    assert estado.turno == chess.WHITE
    assert estado.fen() == chess.Board().fen()

    # el rastreador quedó en reposo: un movimiento normal después funciona bien
    ev3 = rastreador.procesar_ocupacion(_sin(inicial, chess.E2))
    assert ev3 is not None
    assert ev3.tipo is TipoEvento.PIEZA_LEVANTADA


def test_enroque_se_rechaza_como_no_soportado():
    estado = EstadoTablero(fen="r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    ev1 = rastreador.procesar_ocupacion(_sin(inicial, chess.E1))
    assert ev1 is not None
    assert ev1.tipo is TipoEvento.PIEZA_LEVANTADA

    ev2 = rastreador.procesar_ocupacion(_con(_sin(inicial, chess.E1), chess.G1))
    assert ev2 is not None
    assert ev2.tipo is TipoEvento.MOVIMIENTO_NO_SOPORTADO
    assert ev2.origen == chess.E1
    assert ev2.destino == chess.G1

    # el estado lógico no se tocó: ni el rey ni la torre se movieron
    assert estado.turno == chess.WHITE
    assert estado.board.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
    assert estado.board.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE)


def test_captura_fisica_completa_se_rechaza_sin_quedar_en_silencio(caplog):
    """Secuencia física real de una captura: se levanta la atacante, se retira la
    pieza capturada, se coloca la atacante en la casilla de la capturada. El paso
    final coincide por casualidad con la ocupación "de reposo" del tablero lógico
    (nada se aplicó todavía) — sin el seguimiento de la casilla extra vaciada, este
    paso no generaría ningún log ni evento, dejando el rastreador colgado en curso
    para siempre. Este test verifica que en cambio se rechaza explícitamente.
    """
    estado = EstadoTablero(fen="8/8/8/3p4/4P3/8/8/K6k w - - 0 1")
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    ev1 = rastreador.procesar_ocupacion(_sin(inicial, chess.E4))  # se levanta el peón atacante
    assert ev1 is not None
    assert ev1.tipo is TipoEvento.PIEZA_LEVANTADA

    with caplog.at_level(logging.WARNING):
        ev2 = rastreador.procesar_ocupacion(_sin(inicial, chess.E4, chess.D5))  # se retira la capturada
    assert ev2 is None
    assert "captura en curso" in caplog.text

    ev3 = rastreador.procesar_ocupacion(_sin(inicial, chess.E4))  # se coloca la atacante en d5
    assert ev3 is not None
    assert ev3.tipo is TipoEvento.MOVIMIENTO_NO_SOPORTADO
    assert ev3.origen == chess.E4
    assert ev3.destino == chess.D5

    # el estado lógico no se tocó: la captura nunca se aplicó
    assert estado.turno == chess.WHITE
    assert estado.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert estado.board.piece_at(chess.D5) == chess.Piece(chess.PAWN, chess.BLACK)


def test_promocion_ambigua_se_resuelve_a_dama():
    estado = EstadoTablero(fen="8/4P3/8/8/8/8/8/k6K w - - 0 1")
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    rastreador.procesar_ocupacion(_sin(inicial, chess.E7))
    evento = rastreador.procesar_ocupacion(_con(_sin(inicial, chess.E7), chess.E8))

    assert evento is not None
    assert evento.tipo is TipoEvento.MOVIMIENTO_APLICADO
    assert estado.board.piece_at(chess.E8) == chess.Piece(chess.QUEEN, chess.WHITE)


def test_diff_de_mas_de_una_casilla_se_ignora_como_anomalia(caplog):
    estado = EstadoTablero()
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    with caplog.at_level(logging.WARNING):
        evento = rastreador.procesar_ocupacion(_sin(inicial, chess.E2, chess.D2))

    assert evento is None
    assert "diff de ocupación inesperado" in caplog.text
    assert estado.turno == chess.WHITE  # no se tocó el estado


def test_lectura_identica_no_genera_evento_ni_log(caplog):
    estado = EstadoTablero()
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    with caplog.at_level(logging.DEBUG):
        evento = rastreador.procesar_ocupacion(inicial)

    assert evento is None
    assert caplog.text == ""


def test_levantar_pieza_del_color_equivocado_se_ignora(caplog):
    estado = EstadoTablero()
    rastreador = RastreadorMovimientos(estado)
    inicial = casillas_ocupadas(estado.board)

    with caplog.at_level(logging.WARNING):
        evento = rastreador.procesar_ocupacion(_sin(inicial, chess.E7))  # peón negro, mueven blancas

    assert evento is None
    assert "no corresponde a quien tiene el turno" in caplog.text
    assert estado.turno == chess.WHITE
