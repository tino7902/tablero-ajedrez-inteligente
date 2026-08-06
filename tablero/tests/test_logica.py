import chess
import pytest

from tablero.logica.estado_tablero import EstadoTablero, MovimientoIlegalError


def test_posicion_inicial_tiene_veinte_movimientos_legales():
    estado = EstadoTablero()
    assert len(estado.movimientos_legales()) == 20


def test_aplicar_movimiento_legal_cambia_el_turno():
    estado = EstadoTablero()
    estado.aplicar_movimiento(chess.Move.from_uci("e2e4"))
    assert estado.turno == chess.BLACK


def test_aplicar_movimiento_ilegal_levanta_error():
    estado = EstadoTablero()
    with pytest.raises(MovimientoIlegalError):
        estado.aplicar_movimiento(chess.Move.from_uci("e2e5"))


def test_mate_del_pastor_termina_la_partida():
    estado = EstadoTablero()
    for uci in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"):
        estado.aplicar_movimiento(chess.Move.from_uci(uci))

    assert estado.es_jaque_mate()
    assert estado.terminada()
    assert estado.resultado() == "1-0"


def test_ahogado_conocido_es_tablas():
    # Rey negro ahogado en h8, sin jaque y sin movimientos legales.
    estado = EstadoTablero(fen="7k/8/6Q1/8/8/8/8/K7 b - - 0 1")
    assert estado.es_tablas()
    assert estado.terminada()
    assert not estado.esta_en_jaque()


def test_captura_al_paso_elimina_el_peon_capturado():
    estado = EstadoTablero(fen="8/8/8/8/pP6/8/8/k6K b - b3 0 1")
    estado.aplicar_movimiento(chess.Move.from_uci("a4b3"))
    assert estado.board.piece_at(chess.B4) is None
    assert estado.board.piece_at(chess.B3) == chess.Piece(chess.PAWN, chess.BLACK)


def test_enroque_corto_mueve_rey_y_torre():
    estado = EstadoTablero(fen="r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    estado.aplicar_movimiento(chess.Move.from_uci("e1g1"))
    assert estado.board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
    assert estado.board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
    assert estado.board.piece_at(chess.E1) is None
    assert estado.board.piece_at(chess.H1) is None


def test_promocion_a_dama():
    estado = EstadoTablero(fen="8/4P3/8/8/8/8/8/k6K w - - 0 1")
    estado.aplicar_movimiento(chess.Move.from_uci("e7e8q"))
    assert estado.board.piece_at(chess.E8) == chess.Piece(chess.QUEEN, chess.WHITE)


def test_deshacer_vuelve_al_fen_anterior():
    estado = EstadoTablero()
    fen_inicial = estado.fen()
    estado.aplicar_movimiento(chess.Move.from_uci("e2e4"))
    estado.deshacer()
    assert estado.fen() == fen_inicial


def test_reiniciar_vuelve_a_la_posicion_inicial():
    estado = EstadoTablero()
    estado.aplicar_movimiento(chess.Move.from_uci("e2e4"))
    estado.reiniciar()
    assert estado.fen() == chess.Board().fen()
