"""Entradas digitales del tablero: botones del reloj y matriz de casillas.

- Botones del reloj: dos interruptores fin de carrera, detectados por flanco
  (ver hardware-docs/componentes.md, sección "Asignación de Pines GPIO").
- Matriz de ocupación: 64 reed switches barridos con un 74HC138 (elige la fila)
  y un 74HC165 (lee las 8 columnas), ver
  hardware-docs/funcionamiento_deteccion_de_casillas.md.

Pruebas manuales en la Raspberry (ver software-docs/sensores.md):

    uv run python -m tablero.io.sensores botones
    uv run python -m tablero.io.sensores matriz
    uv run python -m tablero.io.sensores calibrar
"""

import argparse
import logging
import time
from collections.abc import Callable

import chess
import RPi.GPIO as GPIO

from tablero import config

logger = logging.getLogger(__name__)

_NOMBRES_BOTONES = {
    config.PIN_BOTON_RELOJ_JUGADOR_1: "boton_1",
    config.PIN_BOTON_RELOJ_JUGADOR_2: "boton_2",
}

_PINES_SELECTOR = (
    config.PIN_MATRIZ_SELECTOR_A,
    config.PIN_MATRIZ_SELECTOR_B,
    config.PIN_MATRIZ_SELECTOR_C,
)
_PINES_MATRIZ = (*_PINES_SELECTOR, config.PIN_MATRIZ_CARGA, config.PIN_MATRIZ_RELOJ, config.PIN_MATRIZ_DATOS)

# Tiempo para que la fila recién elegida en el 74HC138 se estabilice antes de
# cargar las columnas en el 74HC165. Sobra por mucho (el chip tarda nanosegundos),
# pero cubre la capacidad de los cables largos de la matriz.
_ESPERA_SELECCION_FILA = 0.0001

# matriz[salida Y del 74HC138][entrada D del 74HC165] → True si hay pieza.
MatrizCruda = tuple[tuple[bool, ...], ...]


# -- Botones del reloj -------------------------------------------------------------


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
    """Libera solo los pines de los botones, para no desarmar la matriz si está en uso."""
    for pin in _NOMBRES_BOTONES:
        GPIO.remove_event_detect(pin)
    GPIO.cleanup(list(_NOMBRES_BOTONES))


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


# -- Matriz de casillas ------------------------------------------------------------


def configurar_matriz() -> None:
    """Configura los pines del 74HC138 y el 74HC165. Llamar a `liberar_matriz()` al terminar."""
    GPIO.setmode(GPIO.BOARD)
    for pin in _PINES_SELECTOR:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    # SH/LD en HIGH = modo desplazamiento; un pulso LOW carga las 8 columnas.
    GPIO.setup(config.PIN_MATRIZ_CARGA, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.setup(config.PIN_MATRIZ_RELOJ, GPIO.OUT, initial=GPIO.LOW)
    # Q7 lo maneja el 74HC165 (salida push-pull), no hace falta pull.
    GPIO.setup(config.PIN_MATRIZ_DATOS, GPIO.IN)


def liberar_matriz() -> None:
    GPIO.cleanup(list(_PINES_MATRIZ))


def _leer_columnas() -> tuple[bool, ...]:
    """Lee las 8 entradas del 74HC165 de la fila ya seleccionada, indexadas D0..D7.

    Tras el pulso de carga, Q7 ya muestra D7; cada flanco de subida de CLK
    desplaza la siguiente (D6, D5, ... D0). Una columna en LOW es un reed cerrado
    contra la fila activa, o sea pieza presente.
    """
    GPIO.output(config.PIN_MATRIZ_CARGA, GPIO.LOW)
    GPIO.output(config.PIN_MATRIZ_CARGA, GPIO.HIGH)
    leidas = []
    for _ in range(8):
        leidas.append(GPIO.input(config.PIN_MATRIZ_DATOS) == GPIO.LOW)
        GPIO.output(config.PIN_MATRIZ_RELOJ, GPIO.HIGH)
        GPIO.output(config.PIN_MATRIZ_RELOJ, GPIO.LOW)
    return tuple(reversed(leidas))  # se leyó D7 primero


def leer_matriz() -> MatrizCruda:
    """Barre las 8 filas y devuelve la matriz cruda, sin antirrebote ni mapeo a casillas."""
    filas = []
    for salida in range(8):
        for bit, pin in enumerate(_PINES_SELECTOR):
            GPIO.output(pin, GPIO.HIGH if salida >> bit & 1 else GPIO.LOW)
        time.sleep(_ESPERA_SELECCION_FILA)
        filas.append(_leer_columnas())
    return tuple(filas)


class LectorMatriz:
    """Lectura con antirrebote: solo reporta una matriz que se repitió N veces seguidas."""

    def __init__(self, lecturas_estables: int = config.MATRIZ_LECTURAS_ESTABLES) -> None:
        self._lecturas_estables = lecturas_estables
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida lo leído: la próxima matriz estable se devuelve aunque no haya cambiado."""
        self._candidata: MatrizCruda | None = None
        self._repeticiones = 0
        self.estable: MatrizCruda | None = None

    def leer(self) -> MatrizCruda | None:
        """Hace una lectura; devuelve la nueva matriz estable si cambió, si no `None`."""
        lectura = leer_matriz()
        if lectura == self._candidata:
            self._repeticiones += 1
        else:
            self._candidata, self._repeticiones = lectura, 1
        if self._repeticiones >= self._lecturas_estables and lectura != self.estable:
            self.estable = lectura
            return lectura
        return None


def casilla_de(salida: int, entrada: int) -> chess.Square:
    """Casilla de ajedrez de la celda cruda (salida Y del 138, entrada D del 165)."""
    return chess.square(config.COLUMNA_DE_ENTRADA_165[entrada], config.FILA_DE_SALIDA_138[salida])


def ocupacion(matriz: MatrizCruda) -> frozenset[chess.Square]:
    """Convierte la matriz cruda a la `Ocupacion` que espera `logica/eventos.py`."""
    return frozenset(
        casilla_de(salida, entrada)
        for salida, fila in enumerate(matriz)
        for entrada, ocupada in enumerate(fila)
        if ocupada
    )


def _celdas_activas(matriz: MatrizCruda) -> list[tuple[int, int]]:
    return [(s, d) for s, fila in enumerate(matriz) for d, ocupada in enumerate(fila) if ocupada]


def _formatear_matriz(matriz: MatrizCruda) -> str:
    lineas = ["      " + " ".join(f"D{d}" for d in range(8))]
    for salida, fila in enumerate(matriz):
        lineas.append(f"  Y{salida}   " + "  ".join("#" if ocupada else "." for ocupada in fila))
    return "\n".join(lineas)


def _formatear_tablero(casillas: frozenset[chess.Square]) -> str:
    lineas = []
    for fila in range(7, -1, -1):
        celdas = "  ".join("#" if chess.square(col, fila) in casillas else "." for col in range(8))
        lineas.append(f"  {fila + 1}   {celdas}")
    lineas.append("      " + "  ".join("abcdefgh"))
    return "\n".join(lineas)


def probar_matriz() -> None:
    """Muestra en vivo la matriz cruda y el tablero mapeado; loguea cada cambio. Ctrl+C sale."""
    configurar_matriz()
    lector = LectorMatriz()
    anteriores: frozenset[chess.Square] = frozenset()
    logger.info("Leyendo la matriz (Ctrl+C para salir)...")
    try:
        while True:
            matriz = lector.leer()
            if matriz is not None:
                actuales = ocupacion(matriz)
                print("\033[2J\033[H", end="")  # limpia la terminal
                print("Matriz cruda (# = reed cerrado):")
                print(_formatear_matriz(matriz))
                print(f"\nTablero mapeado ({len(actuales)} piezas):")
                print(_formatear_tablero(actuales))
                print()
                for sq in sorted(actuales - anteriores):
                    logger.info("aparece pieza en %s", chess.square_name(sq))
                for sq in sorted(anteriores - actuales):
                    logger.info("se levanta pieza de %s", chess.square_name(sq))
                anteriores = actuales
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        liberar_matriz()
        logger.info("GPIO liberado, saliendo.")


def _esperar_celda_unica(lector: LectorMatriz, casilla: str) -> tuple[int, int] | None:
    input(f"Dejá UNA sola pieza, en {casilla}, y apretá Enter... ")
    lector.reiniciar()
    while (matriz := lector.leer()) is None:
        time.sleep(0.01)
    activas = _celdas_activas(matriz)
    if len(activas) != 1:
        print(f"  Se detectaron {len(activas)} celdas activas ({activas}), tiene que ser 1. Se repite.")
        return None
    salida, entrada = activas[0]
    print(f"  {casilla} → Y{salida}, D{entrada}")
    return salida, entrada


def calibrar_matriz() -> None:
    """Guía para generar FILA_DE_SALIDA_138 y COLUMNA_DE_ENTRADA_165 de config.py.

    Pide una pieza sola en a1..h1 (da el orden de las columnas) y en a2..a8 (da el
    orden de las filas), 15 lecturas en total, y verifica que el cableado sea de
    verdad una grilla (todas las casillas de una fila en la misma salida del 138, etc.).
    """
    configurar_matriz()
    lector = LectorMatriz()
    columnas: list[int | None] = [None] * 8
    filas: list[int | None] = [None] * 8
    try:
        print("Calibración de la matriz: sacá todas las piezas del tablero.\n")
        for col in range(8):
            nombre = chess.square_name(chess.square(col, 0))
            while (celda := _esperar_celda_unica(lector, nombre)) is None:
                pass
            salida, entrada = celda
            columnas[entrada] = col
            if col == 0:
                filas[salida] = 0
            elif filas[salida] != 0:
                print(f"  AVISO: {nombre} no está en la misma salida del 138 que a1 (cableado inesperado)")
        for fila in range(1, 8):
            nombre = chess.square_name(chess.square(0, fila))
            while (celda := _esperar_celda_unica(lector, nombre)) is None:
                pass
            salida, entrada = celda
            filas[salida] = fila
            if columnas[entrada] != 0:
                print(f"  AVISO: {nombre} no está en la misma entrada del 165 que a1 (cableado inesperado)")
    except KeyboardInterrupt:
        print("\nCalibración cancelada.")
        return
    finally:
        liberar_matriz()

    if None in columnas or None in filas or len(set(columnas)) != 8 or len(set(filas)) != 8:
        print("\nEl mapeo quedó incompleto o con repetidos:")
        print(f"  filas={filas}\n  columnas={columnas}")
        print("Revisar el cableado (dos casillas leídas en la misma celda) y repetir.")
        return
    print("\nCopiar en tablero/src/tablero/config.py:\n")
    print(f"FILA_DE_SALIDA_138: tuple[int, ...] = {tuple(filas)}")
    print(f"COLUMNA_DE_ENTRADA_165: tuple[int, ...] = {tuple(columnas)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pruebas manuales de los sensores del tablero.")
    parser.add_argument(
        "prueba",
        nargs="?",
        default="botones",
        choices=["botones", "matriz", "calibrar"],
        help="botones: reloj (por defecto); matriz: ver la grilla en vivo; calibrar: generar el mapeo",
    )
    prueba = parser.parse_args().prueba
    {"botones": probar_botones_reloj, "matriz": probar_matriz, "calibrar": calibrar_matriz}[prueba]()
