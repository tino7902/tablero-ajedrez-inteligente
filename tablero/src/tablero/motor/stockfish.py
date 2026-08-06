"""Integración con el motor Stockfish para el modo vs-máquina.

Envuelve `chess.engine.SimpleEngine` (API síncrona de python-chess, sin
asyncio — coherente con un loop de polling de GPIO en el resto del proyecto)
hablando el protocolo UCI con el binario `stockfish` del sistema.

Fuerza fija en esta etapa: no se setean opciones UCI de Skill Level ni modo
de análisis/hint, Stockfish juega a máxima fuerza limitado solo por el tiempo
por jugada (`tiempo_por_jugada` / `config.STOCKFISH_MOVETIME`).
"""

from __future__ import annotations

import chess
import chess.engine

from tablero import config


class MotorStockfish:
    """Wrapper de `chess.engine.SimpleEngine` para pedir la mejor jugada.

    Recibe un `chess.Board` en `mejor_movimiento` (no un `EstadoTablero`) para
    que este módulo no dependa del wrapper de `logica/` — el llamador pasa
    `estado.board`.

    Levanta un proceso del binario de Stockfish al construirse; hay que
    llamar a `cerrar()` (o usar como context manager) para no dejar el
    proceso huérfano.
    """

    def __init__(
        self,
        ruta_binario: str | None = None,
        tiempo_por_jugada: float | None = None,
    ) -> None:
        """Abre el proceso de Stockfish.

        `ruta_binario` y `tiempo_por_jugada` (segundos) usan por default
        `config.STOCKFISH_PATH` y `config.STOCKFISH_MOVETIME` si no se pasan.
        """
        self._tiempo_por_jugada = tiempo_por_jugada or config.STOCKFISH_MOVETIME
        self._engine = chess.engine.SimpleEngine.popen_uci(
            ruta_binario or config.STOCKFISH_PATH
        )

    def mejor_movimiento(self, tablero: chess.Board) -> chess.Move:
        """Mejor jugada de Stockfish para `tablero`, según el tiempo configurado."""
        resultado = self._engine.play(
            tablero, chess.engine.Limit(time=self._tiempo_por_jugada)
        )
        assert resultado.move is not None
        return resultado.move

    def cerrar(self) -> None:
        """Cierra el proceso de Stockfish."""
        self._engine.quit()

    def __enter__(self) -> MotorStockfish:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cerrar()
