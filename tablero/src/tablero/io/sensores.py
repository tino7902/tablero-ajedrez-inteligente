"""Entradas digitales del tablero: botones del reloj de ajedrez.

Por ahora solo cubre los dos botones del reloj (interruptores fin de carrera,
ver hardware-docs/componentes.md, sección "Asignación de Pines GPIO"). La
matriz de ocupación de casillas (74HC165 + 74HC138) todavía no está
implementada acá.
"""

import logging
import time
from collections.abc import Callable

import RPi.GPIO as GPIO

from tablero import config

logger = logging.getLogger(__name__)

_NOMBRES_BOTONES = {
    config.PIN_BOTON_RELOJ_JUGADOR_1: "boton_1",
    config.PIN_BOTON_RELOJ_JUGADOR_2: "boton_2",
}


def configurar_botones_reloj(callback: Callable[[str], None]) -> None:
    """Configura GPIO para llamar a `callback('boton_1' | 'boton_2')` en cada presión.

    Los botones conectan el pin a GND al presionarse (activo en bajo), así
    que se habilita el pull-up interno del SoC (`GPIO.PUD_UP`) sin importar
    cómo estén armadas las resistencias externas (ver software-docs/sensores.md)
    y se detecta la presión por flanco descendente (`GPIO.FALLING`).

    El callback corre en el thread interno de `rpi-lgpio` (no en el thread que
    llama a esta función) — quien lo use debe tenerlo en cuenta si no es
    thread-safe. Llamar a `liberar_botones_reloj()` al terminar.
    """
    def _en_flanco(pin: int) -> None:
        callback(_NOMBRES_BOTONES[pin])

    GPIO.setmode(GPIO.BOARD)
    for pin in _NOMBRES_BOTONES:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(pin, GPIO.FALLING, callback=_en_flanco, bouncetime=200)


def liberar_botones_reloj() -> None:
    GPIO.cleanup()


def probar_botones_reloj() -> None:
    """Loguea cada vez que se presiona alguno de los dos botones del reloj.

    Test manual de hardware standalone, construido sobre `configurar_botones_reloj()`.
    Todavía no hay lógica de reloj acá (eso vive en `io/menus.py`/`io/menus_gpio.py`) —
    solo confirma que la detección de flanco funciona en cada pin por separado. Corre
    indefinidamente hasta Ctrl+C.
    """
    configurar_botones_reloj(lambda nombre: logger.info("%s presionado", nombre))
    logger.info(
        "Esperando presiones en boton_1 (pin %d) o boton_2 (pin %d) (Ctrl+C para salir)...",
        config.PIN_BOTON_RELOJ_JUGADOR_1,
        config.PIN_BOTON_RELOJ_JUGADOR_2,
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        liberar_botones_reloj()
        logger.info("GPIO liberado, saliendo.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    probar_botones_reloj()
