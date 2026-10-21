"""Integración con el motor Stockfish para el modo vs-máquina.

Envuelve `chess.engine.SimpleEngine` (API síncrona de python-chess, sin
asyncio — coherente con un loop de polling de GPIO en el resto del proyecto)
hablando el protocolo UCI con el binario `stockfish` del sistema.

Con `nivel` (una clave de `config.NIVELES_MAGNUS`) se configura `Skill Level`
al abrir el motor y cada jugada usa el tiempo de ese nivel. Sin `nivel`,
Stockfish juega a máxima fuerza limitado solo por el tiempo por jugada
(`tiempo_por_jugada` / `config.STOCKFISH_MOVETIME`).

`mejor_movimiento` bloquea mientras el motor piensa: `io/juego.py` lo llama
desde otro hilo para que los LEDs y la matriz no se congelen.
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
        nivel: str | None = None,
    ) -> None:
        """Abre el proceso de Stockfish.

        `ruta_binario` usa por default `config.STOCKFISH_PATH`. `nivel` es una
        clave de `config.NIVELES_MAGNUS` (`ValueError` si no existe, antes de
        abrir nada). `tiempo_por_jugada` (segundos), si se pasa, gana sobre el
        del nivel; sin ninguno de los dos se usa `config.STOCKFISH_MOVETIME`.
        """
        datos_nivel = None
        if nivel is not None:
            if nivel not in config.NIVELES_MAGNUS:
                opciones = ", ".join(config.NIVELES_MAGNUS)
                raise ValueError(f"nivel de Magnus desconocido: {nivel!r} (hay {opciones})")
            datos_nivel = config.NIVELES_MAGNUS[nivel]

        self._tiempo_por_jugada = tiempo_por_jugada or (
            datos_nivel.segundos_por_jugada if datos_nivel else config.STOCKFISH_MOVETIME
        )
        # En su propio grupo de procesos: un Ctrl+C en la terminal le llega solo a
        # Python, que termina la jugada en curso y cierra el motor ordenadamente.
        self._engine = chess.engine.SimpleEngine.popen_uci(
            ruta_binario or config.STOCKFISH_PATH, setpgrp=True
        )
        if datos_nivel is not None:
            self._engine.configure({"Skill Level": datos_nivel.skill_level})

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
