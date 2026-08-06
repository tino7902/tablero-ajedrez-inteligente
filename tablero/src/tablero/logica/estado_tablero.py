"""Estado de la partida y validación de movimientos.

Envuelve `chess.Board` (paquete `chess`, instalado como `python-chess`) con una
API en español para el resto del proyecto. Toda la lógica de reglas (jaque,
enroque, al paso, promoción, tablas) la resuelve python-chess — este módulo no
reimplementa reglas de ajedrez, solo expone un wrapper.

No maneja la traducción de eventos de sensores a `chess.Move` (eso es
responsabilidad de `logica/eventos.py`, todavía no implementado) ni la
resolución de a qué pieza promociona un peón: quien llama a
`aplicar_movimiento` debe pasar un `chess.Move` ya completo, incluyendo la
pieza de promoción si corresponde (ej. `chess.Move.from_uci("e7e8q")`).
"""

from __future__ import annotations

import chess


class MovimientoIlegalError(ValueError):
    """Se intentó aplicar un movimiento que no es legal en la posición actual."""


class EstadoTablero:
    """Wrapper de `chess.Board` con la API que usa el resto del proyecto.

    Expone la propiedad `board` (el `chess.Board` interno) para interoperar
    con `motor/stockfish.py`, que recibe un `chess.Board` en vez de depender
    de esta clase. `board` es de solo lectura por convención: no se debe
    mutar directamente, solo a través de `aplicar_movimiento`.
    """

    def __init__(self, fen: str | None = None) -> None:
        """Crea la partida en la posición inicial, o en `fen` si se pasa."""
        self._board = chess.Board(fen) if fen else chess.Board()

    @property
    def board(self) -> chess.Board:
        """`chess.Board` interno, de solo lectura por convención."""
        return self._board

    @property
    def turno(self) -> chess.Color:
        """A quién le toca mover (`chess.WHITE` o `chess.BLACK`)."""
        return self._board.turn

    def fen(self) -> str:
        """Posición actual en notación FEN."""
        return self._board.fen()

    def movimientos_legales(self) -> list[chess.Move]:
        """Todos los movimientos legales en la posición actual."""
        return list(self._board.legal_moves)

    def es_legal(self, movimiento: chess.Move) -> bool:
        """Indica si `movimiento` es legal en la posición actual."""
        return self._board.is_legal(movimiento)

    def aplicar_movimiento(self, movimiento: chess.Move) -> None:
        """Aplica `movimiento` sobre el tablero.

        Levanta `MovimientoIlegalError` si el movimiento no es legal en la
        posición actual — el llamador nunca debe asumir que se aplicó.
        """
        if not self.es_legal(movimiento):
            raise MovimientoIlegalError(
                f"{movimiento.uci()} no es un movimiento legal en {self.fen()}"
            )
        self._board.push(movimiento)

    def deshacer(self) -> chess.Move:
        """Deshace el último movimiento aplicado y lo devuelve."""
        return self._board.pop()

    def reiniciar(self) -> None:
        """Vuelve a la posición inicial de una partida nueva."""
        self._board = chess.Board()

    def esta_en_jaque(self) -> bool:
        """Indica si el jugador que tiene el turno está en jaque."""
        return self._board.is_check()

    def es_jaque_mate(self) -> bool:
        """Indica si la posición actual es jaque mate."""
        return self._board.is_checkmate()

    def es_tablas(self) -> bool:
        """Indica si la partida es tablas: ahogado, material insuficiente,
        regla de 50 movimientos o triple repetición (estas dos últimas solo
        si un jugador puede reclamarlas, vía `Board.can_claim_draw`).
        """
        return (
            self._board.is_stalemate()
            or self._board.is_insufficient_material()
            or self._board.can_claim_draw()
        )

    def terminada(self) -> bool:
        """Indica si la partida terminó (mate, tablas, o cualquier otro fin)."""
        return self._board.is_game_over()

    def resultado(self) -> str | None:
        """Resultado de la partida ("1-0", "0-1", "1/2-1/2") o `None` si sigue en curso."""
        outcome = self._board.outcome(claim_draw=True)
        return outcome.result() if outcome else None
