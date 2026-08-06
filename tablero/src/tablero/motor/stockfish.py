from __future__ import annotations

import chess
import chess.engine

from tablero import config


class MotorStockfish:
    def __init__(
        self,
        ruta_binario: str | None = None,
        tiempo_por_jugada: float | None = None,
    ) -> None:
        self._tiempo_por_jugada = tiempo_por_jugada or config.STOCKFISH_MOVETIME
        self._engine = chess.engine.SimpleEngine.popen_uci(
            ruta_binario or config.STOCKFISH_PATH
        )

    def mejor_movimiento(self, tablero: chess.Board) -> chess.Move:
        resultado = self._engine.play(
            tablero, chess.engine.Limit(time=self._tiempo_por_jugada)
        )
        assert resultado.move is not None
        return resultado.move

    def cerrar(self) -> None:
        self._engine.quit()

    def __enter__(self) -> MotorStockfish:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cerrar()
