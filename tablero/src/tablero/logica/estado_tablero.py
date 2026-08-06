from __future__ import annotations

import chess


class MovimientoIlegalError(ValueError):
    """Se intentó aplicar un movimiento que no es legal en la posición actual."""


class EstadoTablero:
    def __init__(self, fen: str | None = None) -> None:
        self._board = chess.Board(fen) if fen else chess.Board()

    @property
    def board(self) -> chess.Board:
        return self._board

    @property
    def turno(self) -> chess.Color:
        return self._board.turn

    def fen(self) -> str:
        return self._board.fen()

    def movimientos_legales(self) -> list[chess.Move]:
        return list(self._board.legal_moves)

    def es_legal(self, movimiento: chess.Move) -> bool:
        return self._board.is_legal(movimiento)

    def aplicar_movimiento(self, movimiento: chess.Move) -> None:
        if not self.es_legal(movimiento):
            raise MovimientoIlegalError(
                f"{movimiento.uci()} no es un movimiento legal en {self.fen()}"
            )
        self._board.push(movimiento)

    def deshacer(self) -> chess.Move:
        return self._board.pop()

    def reiniciar(self) -> None:
        self._board = chess.Board()

    def esta_en_jaque(self) -> bool:
        return self._board.is_check()

    def es_jaque_mate(self) -> bool:
        return self._board.is_checkmate()

    def es_tablas(self) -> bool:
        return (
            self._board.is_stalemate()
            or self._board.is_insufficient_material()
            or self._board.can_claim_draw()
        )

    def terminada(self) -> bool:
        return self._board.is_game_over()

    def resultado(self) -> str | None:
        outcome = self._board.outcome(claim_draw=True)
        return outcome.result() if outcome else None
