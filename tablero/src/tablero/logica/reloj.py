"""Reloj de ajedrez: dos temporizadores independientes con cambio de turno.

Único reloj del proyecto — lo usan tanto la simulación por terminal
(`tablero/simulacion.py`, vía `logica/partida.py`) como la pantalla PvP
(`io/menus.py`), que antes descontaba el tiempo a mano en su propio loop de pygame.
No depende de hardware ni de pygame: vive en `logica/` y se testea off-device
(`tests/test_reloj.py`), respetando el boundary documentado en `CLAUDE.md`.

Solo mide tiempo y cambia de turno cuando se lo piden: la regla de "el turno pasa
únicamente si además hubo un movimiento legal" es responsabilidad de
`logica/partida.py`, que es quien decide si llamar a `pulsar`. Así el mismo reloj
sirve a `io/menus.py`, que todavía no tiene sensores y pasa el turno con el botón solo.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

import chess


def formatear_tiempo(segundos: float) -> str:
    """Formatea `segundos` como `MM:SS`, redondeando hacia arriba y sin bajar de cero.

    Hacia arriba y no hacia abajo para que una partida de 5 minutos muestre `05:00` al
    arrancar (y no `04:59` por unos milisegundos), y para que `00:00` aparezca recién
    cuando el tiempo se agotó de verdad — igual que un reloj de ajedrez comercial.
    """
    total = max(0, math.ceil(segundos - 1e-9))
    minutos, segs = divmod(total, 60)
    return f"{minutos:02d}:{segs:02d}"


class RelojAjedrez:
    """Dos temporizadores de cuenta regresiva, uno por color, con turno activo.

    El tiempo se descuenta del jugador cuyo `turno` está activo, y solo cuando se
    llama a `actualizar()` (tiempo real transcurrido) o `avanzar()` (tiempo simulado).
    """

    def __init__(
        self,
        segundos_por_jugador: float,
        fuente_tiempo: Callable[[], float] = time.monotonic,
    ) -> None:
        """Arranca el reloj con `segundos_por_jugador` para cada lado y el turno en blancas.

        `fuente_tiempo` se puede reemplazar por una función controlada en los tests para
        que el descuento sea determinista (ver `tests/test_reloj.py`).
        """
        self._restante = {
            chess.WHITE: float(segundos_por_jugador),
            chess.BLACK: float(segundos_por_jugador),
        }
        self._turno: chess.Color = chess.WHITE
        self._tiempo_agotado = False
        self._fuente_tiempo = fuente_tiempo
        self._ultimo_tick = fuente_tiempo()

    @property
    def turno(self) -> chess.Color:
        """Color cuyo reloj está corriendo.

        Cuando el tiempo se agota queda congelado en el lado que perdió, así identifica
        a la vez "de quién es el turno" y "quién perdió por tiempo" (misma convención
        que usaba `EstadoPartida` en `io/menus.py`).
        """
        return self._turno

    @property
    def tiempo_agotado(self) -> bool:
        """Indica si algún jugador se quedó sin tiempo."""
        return self._tiempo_agotado

    @property
    def perdedor(self) -> chess.Color | None:
        """Color que se quedó sin tiempo, o `None` si todavía no pasó."""
        return self._turno if self._tiempo_agotado else None

    def restante(self, color: chess.Color) -> float:
        """Segundos que le quedan a `color`."""
        return self._restante[color]

    def actualizar(self) -> bool:
        """Descuenta el tiempo real transcurrido desde la última llamada.

        Devuelve `True` solo en la llamada en la que el tiempo se agota (después
        siempre `False`), para que el llamador loguee o dibuje el fin una sola vez.
        """
        ahora = self._fuente_tiempo()
        transcurrido = ahora - self._ultimo_tick
        self._ultimo_tick = ahora
        return self._descontar(transcurrido)

    def avanzar(self, segundos: float) -> bool:
        """Descuenta `segundos` de forma manual (tiempo simulado).

        Sincroniza el instante del último tick para que un `actualizar()` posterior no
        vuelva a cobrar el tiempo real que pasó mientras tanto. Mismo valor de retorno
        que `actualizar()`.
        """
        self._ultimo_tick = self._fuente_tiempo()
        return self._descontar(segundos)

    def _descontar(self, segundos: float) -> bool:
        if self._tiempo_agotado or segundos <= 0:
            return False
        self._restante[self._turno] = max(0.0, self._restante[self._turno] - segundos)
        if self._restante[self._turno] > 0:
            return False
        self._tiempo_agotado = True
        return True

    def pulsar(self, color: chess.Color) -> bool:
        """Pasa el turno al otro jugador si `color` es quien tiene el reloj corriendo.

        Devuelve si el turno cambió: pulsar el botón ajeno (o con el tiempo ya agotado)
        no hace nada, igual que un reloj físico.
        """
        if self._tiempo_agotado or color != self._turno:
            return False
        self._turno = not self._turno
        return True
