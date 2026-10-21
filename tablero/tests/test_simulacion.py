"""Tests del modo vs Magnus de la simulación (tablero/src/tablero/simulacion.py).

No requieren Stockfish: el motor es un falso que devuelve jugadas fijas, y lo que se
tipea se reemplaza con `monkeypatch` sobre `input`.
"""

import chess

from tablero.logica.notacion import Idioma
from tablero.logica.partida import Partida
from tablero.simulacion import jugar_magnus


class _MotorFalso:
    """Contesta las jugadas que se le dan, en orden, y anota las posiciones que recibió."""

    def __init__(self, *jugadas: str) -> None:
        self._jugadas = [chess.Move.from_uci(uci) for uci in jugadas]
        self.posiciones: list[str] = []

    def mejor_movimiento(self, board: chess.Board) -> chess.Move:
        self.posiciones.append(board.fen())
        return self._jugadas.pop(0)


def _tipear(monkeypatch, *lineas: str) -> None:
    entradas = iter(lineas)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(entradas))


def _partida(tiempo, fen=None) -> Partida:
    return Partida(segundos_por_jugador=None, idioma=Idioma.ESPANOL, fen=fen, fuente_tiempo=tiempo)


def test_magnus_contesta_despues_de_tu_boton_y_te_podes_rendir(monkeypatch, capsys, tiempo):
    partida = _partida(tiempo)
    motor = _MotorFalso("e7e5")
    _tipear(monkeypatch, "e4", "", "rendirse")

    jugar_magnus(partida, motor, chess.WHITE)

    salida = capsys.readouterr().out
    assert "Magnus: peón e7→e5" in salida
    assert [m.uci() for m in partida.estado.board.move_stack] == ["e2e4", "e7e5"]
    assert partida.motivo_fin == "rendición"
    assert partida.resultado() == "0-1"
    assert "Aguantaste 00:00 contra Magnus" in salida


def test_con_negras_magnus_juega_primero(monkeypatch, capsys, tiempo):
    partida = _partida(tiempo)
    motor = _MotorFalso("e2e4")
    _tipear(monkeypatch, "salir")

    jugar_magnus(partida, motor, chess.BLACK)

    assert motor.posiciones == [chess.STARTING_FEN]
    assert partida.turno == chess.BLACK, "la jugada de Magnus se confirma sola"
    assert "Partida abandonada" in capsys.readouterr().out


def test_mate_tuyo_termina_con_el_mensaje_final(monkeypatch, capsys, tiempo):
    partida = _partida(tiempo, fen="6k1/5ppp/8/8/8/8/8/R6K w - - 0 1")
    _tipear(monkeypatch, "Ta8")

    jugar_magnus(partida, _MotorFalso(), chess.WHITE)

    assert partida.motivo_fin == "jaque mate"
    assert "¡Derrotaste a Magnus en 00:00!" in capsys.readouterr().out
