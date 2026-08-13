"""Entradas digitales del tablero: botones del reloj de ajedrez.

Por ahora solo cubre los dos botones del reloj (interruptores fin de carrera,
ver hardware-docs/componentes.md, sección "Asignación de Pines GPIO"). La
matriz de ocupación de casillas (74HC165 + 74HC138) todavía no está
implementada acá.
"""

import logging
import time

import RPi.GPIO as GPIO

from tablero import config

logger = logging.getLogger(__name__)

_NOMBRES_BOTONES = {
    config.PIN_BOTON_RELOJ_JUGADOR_1: "boton_1",
    config.PIN_BOTON_RELOJ_JUGADOR_2: "boton_2",
}


def _log_boton_presionado(pin: int) -> None:
    logger.info("%s presionado (pin físico %d)", _NOMBRES_BOTONES[pin], pin)


def probar_botones_reloj() -> None:
    """Loguea cada vez que se presiona alguno de los dos botones del reloj.

    Test manual de hardware: todavía no hay lógica de reloj (tiempo, turnos,
    de quién es el turno) — solo confirma que la detección de flanco funciona
    en cada pin por separado. Corre indefinidamente hasta Ctrl+C.

    Los botones conectan el pin a GND al presionarse (activo en bajo), así
    que se habilita el pull-up interno del SoC (`GPIO.PUD_UP`) sin importar
    cómo estén armadas las resistencias externas (ver software-docs/sensores.md)
    y se detecta la presión por flanco descendente (`GPIO.FALLING`).
    """
    GPIO.setmode(GPIO.BOARD)
    pines = (config.PIN_BOTON_RELOJ_JUGADOR_1, config.PIN_BOTON_RELOJ_JUGADOR_2)

    try:
        for pin in pines:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(pin, GPIO.FALLING, callback=_log_boton_presionado, bouncetime=200)

        logger.info(
            "Esperando presiones en boton_1 (pin %d) o boton_2 (pin %d) (Ctrl+C para salir)...",
            config.PIN_BOTON_RELOJ_JUGADOR_1,
            config.PIN_BOTON_RELOJ_JUGADOR_2,
        )
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        logger.info("GPIO liberado, saliendo.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    probar_botones_reloj()
