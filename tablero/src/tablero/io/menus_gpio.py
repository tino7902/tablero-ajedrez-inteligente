"""Punto de entrada para correr la interfaz completa en la Raspberry con los botones
físicos del reloj (GPIO) conectados.

Reusa el mismo diseño gráfico y loop de navegación de `io/menus.py` sin modificarlo: solo
agrega de dónde vienen los eventos de "se presionó boton_1/boton_2" (GPIO en vez de
teclado). Este archivo y `io/menus.py` son independientes a propósito — cambiar cómo se
simulan los botones por teclado en `io/menus.py` no puede romper la detección real por
GPIO acá, y viceversa; lo único que comparten es `menus.ejecutar_menus()` y la constante
`menus.EVENTO_BOTON_RELOJ`.

    cd tablero
    uv run python -m tablero.io.menus_gpio
"""

import logging

import pygame

from tablero.io import menus, sensores

logger = logging.getLogger(__name__)


def _publicar_evento_boton(nombre: str) -> None:
    pygame.event.post(pygame.event.Event(menus.EVENTO_BOTON_RELOJ, boton=nombre))


def ejecutar_menus_gpio() -> None:
    sensores.configurar_botones_reloj(_publicar_evento_boton)
    try:
        menus.ejecutar_menus()
    finally:
        sensores.liberar_botones_reloj()
        logger.info("GPIO liberado.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ejecutar_menus_gpio()
