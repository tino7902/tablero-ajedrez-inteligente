"""La interfaz de la pantalla táctil en la Raspberry, con el tablero real.

Arma el `Hardware` de `io/menus.py` con lo físico y llama a `menus.ejecutar_menus`:

- la ocupación de las casillas sale de la matriz Hall del Nano (`io/sensores.py`);
- los LEDs se pintan con la tira WS2812B (`io/leds.py`), con los mismos colores que
  `io/juego.py`;
- los botones del reloj (GPIO) publican `menus.EVENTO_BOTON_RELOJ`, como antes;
- contra Magnus se abre Stockfish (`motor/stockfish.py`).

`io/menus.py` no importa nada de esto a propósito: así la versión de la notebook (tablero
simulado, teclado) y la de la Pi no se pueden romper entre sí. Usa los LEDs, así que
necesita root: si no se corre como root se relanza solo con `sudo`, como `io/juego.py`.

    cd tablero
    uv run python -m tablero.io.menus_gpio
"""

import logging
import os
import sys
from pathlib import Path

import chess
import pygame

from tablero import config
from tablero.io import leds, matriz, menus, sensores
from tablero.logica.eventos import Marca, Ocupacion
from tablero.logica.sesion import ErrorTablero

logger = logging.getLogger(__name__)

_COLOR_DE_MARCA = {
    Marca.ORIGEN: leds.AZUL,
    Marca.DESTINO: leds.BLANCO_TENUE,
    Marca.JUGADA: leds.VERDE,
    Marca.FALTA: leds.ROJO,
    Marca.SOBRA: leds.AMARILLO,
    Marca.MAGNUS_ORIGEN: leds.VIOLETA,
    Marca.MAGNUS_DESTINO: leds.CIAN,
}


def _publicar_evento_boton(nombre: str) -> None:
    # Corre en el hilo de rpi-lgpio; pygame.event.post se puede llamar desde otro hilo.
    pygame.event.post(pygame.event.Event(menus.EVENTO_BOTON_RELOJ, boton=nombre))


class _FuenteNano:
    """La matriz del Nano como fuente de ocupación de `logica/sesion.py`."""

    def __init__(self) -> None:
        # Un lector nuevo por partida: la primera lectura estable se entrega aunque las
        # piezas no se hayan movido desde la partida anterior.
        self._lector = sensores.LectorMatriz()

    def leer(self) -> Ocupacion | None:
        try:
            lectura = self._lector.leer()
        except matriz.ErrorNano as error:
            # Se cierra el puerto para que la próxima partida lo vuelva a abrir.
            sensores.liberar_matriz()
            raise ErrorTablero(f"Error con el Nano: {error}") from error
        return None if lectura is None else sensores.ocupacion(lectura)


def _crear_fuente() -> _FuenteNano:
    try:
        sensores.configurar_matriz()  # no hace nada si ya está abierto
    except matriz.ErrorNano as error:
        raise ErrorTablero(f"Error con el Nano: {error}") from error
    return _FuenteNano()


def _devolver_registros_al_usuario() -> None:
    """Con `sudo`, los registros quedan de root: se los devuelve a quien lo corrió."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    raiz = Path(config.DIRECTORIO_REGISTROS)
    if os.geteuid() != 0 or uid is None or gid is None or not raiz.exists():
        return
    for ruta in [raiz, *raiz.rglob("*")]:
        try:
            os.chown(ruta, int(uid), int(gid))
        except OSError as error:
            logger.warning("No se pudo devolver %s a su dueño: %s", ruta, error)


def ejecutar_menus_gpio(brillo: int = config.LED_BRILLO) -> None:
    tira = leds.TiraLeds(brillo)

    def pintar(marcas: dict[chess.Square, Marca]) -> None:
        tira.limpiar()
        for casilla, marca in marcas.items():
            tira.encender(casilla, _COLOR_DE_MARCA[marca])
        tira.mostrar()

    hardware = menus.Hardware(crear_fuente=_crear_fuente, pintar=pintar, crear_motor=menus.crear_motor_stockfish)
    try:
        sensores.configurar_matriz()  # ahora y no en la primera partida: abrirlo tarda ~2 s
    except matriz.ErrorNano as error:
        logger.warning("El Nano no está listo todavía (%s); se reintenta al empezar una partida.", error)
    sensores.configurar_botones_reloj(_publicar_evento_boton)
    try:
        menus.ejecutar_menus(hardware)
    finally:
        tira.apagar()
        sensores.liberar_botones_reloj()
        sensores.liberar_matriz()
        _devolver_registros_al_usuario()
        logger.info("LEDs apagados, GPIO y puerto del Nano liberados.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        # rpi-ws281x necesita root (/dev/mem), ver io/leds.py: mismo relanzamiento.
        os.execvp("sudo", ["sudo", sys.executable, "-m", "tablero.io.menus_gpio", *sys.argv[1:]])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ejecutar_menus_gpio()
