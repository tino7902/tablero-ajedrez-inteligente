"""LEDs WS2812B del tablero: uno por casilla más el LED de sacrificio.

Usa `rpi-ws281x` sobre GPIO 12 (pin físico 32, PWM0). Necesita root para acceder a
`/dev/mem` y el audio analógico desactivado (`dtparam=audio=off` en config.txt),
porque comparte el periférico PWM — ver software-docs/leds.md.

Pruebas manuales en la Raspberry (desde tablero/):

    sudo .venv/bin/python -m tablero.io.leds todos
    sudo .venv/bin/python -m tablero.io.leds recorrer
    sudo .venv/bin/python -m tablero.io.leds esquinas
"""

import argparse
import logging
import time

import chess
from rpi_ws281x import Color, PixelStrip

from tablero import config

logger = logging.getLogger(__name__)

APAGADO = Color(0, 0, 0)
BLANCO = Color(255, 255, 255)
ROJO = Color(255, 0, 0)
VERDE = Color(0, 255, 0)
AZUL = Color(0, 0, 255)
AMARILLO = Color(255, 255, 0)


def indice_de(casilla: chess.Square) -> int:
    """Índice en la tira del LED de `casilla`, según LED_ZIGZAG (ver config.py)."""
    fila, columna = chess.square_rank(casilla), chess.square_file(casilla)
    if config.LED_ZIGZAG and fila % 2 == 1:
        columna = 7 - columna
    return config.LED_INDICE_SACRIFICIO + 1 + fila * 8 + columna


class TiraLeds:
    """Envoltorio de `PixelStrip` que habla en casillas y mantiene apagado el LED de sacrificio."""

    def __init__(self, brillo: int = config.LED_BRILLO) -> None:
        self._tira = PixelStrip(
            config.LED_CANTIDAD,
            config.LED_GPIO_BCM,
            brightness=brillo,
            channel=config.LED_CANAL_PWM,
        )
        self._tira.begin()

    def encender(self, casilla: chess.Square, color: int) -> None:
        self._tira.setPixelColor(indice_de(casilla), color)

    def encender_indice(self, indice: int, color: int) -> None:
        self._tira.setPixelColor(indice, color)

    def limpiar(self) -> None:
        for indice in range(config.LED_CANTIDAD):
            self._tira.setPixelColor(indice, APAGADO)

    def mostrar(self) -> None:
        """Envía los colores a la tira (nada cambia hasta llamar a esto)."""
        self._tira.setPixelColor(config.LED_INDICE_SACRIFICIO, APAGADO)
        self._tira.show()

    def apagar(self) -> None:
        self.limpiar()
        self.mostrar()


def _probar_todos(tira: TiraLeds) -> None:
    """Enciende las 64 casillas en rojo, verde, azul y blanco (brillo bajo)."""
    for nombre, color in (("rojo", ROJO), ("verde", VERDE), ("azul", AZUL), ("blanco", BLANCO)):
        logger.info("Todas las casillas en %s", nombre)
        for casilla in chess.SQUARES:
            tira.encender(casilla, color)
        tira.mostrar()
        time.sleep(2)


def _probar_recorrer(tira: TiraLeds) -> None:
    """Enciende de a un LED por índice de la tira, para anotar en qué casilla cae cada uno."""
    for indice in range(config.LED_CANTIDAD):
        if indice == config.LED_INDICE_SACRIFICIO:
            continue
        tira.limpiar()
        tira.encender_indice(indice, BLANCO)
        tira.mostrar()
        input(f"LED {indice} encendido (Enter para el siguiente)... ")


def _probar_esquinas(tira: TiraLeds) -> None:
    """Enciende a1, h1, a8 y h8 con colores distintos a través del mapeo casilla → LED."""
    esquinas = ((chess.A1, ROJO, "rojo"), (chess.H1, VERDE, "verde"), (chess.A8, AZUL, "azul"), (chess.H8, AMARILLO, "amarillo"))
    tira.limpiar()
    for casilla, color, nombre in esquinas:
        tira.encender(casilla, color)
        logger.info("%s → LED %d (%s)", chess.square_name(casilla), indice_de(casilla), nombre)
    tira.mostrar()
    input("Verificar que cada color esté en su esquina (Enter para terminar)... ")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pruebas manuales de los LEDs del tablero.")
    parser.add_argument(
        "prueba",
        choices=["todos", "recorrer", "esquinas"],
        help="todos: colores en todo el tablero; recorrer: LED por LED; esquinas: verificar el mapeo",
    )
    parser.add_argument("--brillo", type=int, default=config.LED_BRILLO, help="0-255")
    argumentos = parser.parse_args()
    tira = TiraLeds(argumentos.brillo)
    pruebas = {"todos": _probar_todos, "recorrer": _probar_recorrer, "esquinas": _probar_esquinas}
    try:
        pruebas[argumentos.prueba](tira)
    except KeyboardInterrupt:
        pass
    finally:
        tira.apagar()
        logger.info("LEDs apagados, saliendo.")
