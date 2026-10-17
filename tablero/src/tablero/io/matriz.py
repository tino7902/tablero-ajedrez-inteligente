"""Barrido de la matriz de casillas: 74HC138 (elige la fila) + 74HC165 (lee las 8 columnas).

Común a las dos versiones de sensor, porque los chips y su cableado son los mismos:
- Hall (la actual): io/sensores.py. El 138 además alimenta los Hall de la fila elegida.
- Reed (la anterior): io/sensores_reed.py.

Cada versión pone su propia espera por fila, su antirrebote y su mapeo celda → casilla;
acá solo está el manejo de los chips, sus pruebas por separado (`probar_selector`,
`probar_lector`) y la vista en vivo que usan las dos. Funcionamiento de los chips en
hardware-docs/funcionamiento_deteccion_de_casillas.md, conexiones pata por pata en
hardware-docs/conexiones-matriz.md y detalle en software-docs/sensores.md.
"""

import logging
import time
from collections.abc import Callable

import chess
import RPi.GPIO as GPIO

from tablero import config
from tablero.logica.matriz import MatrizCruda

logger = logging.getLogger(__name__)

_PINES_SELECTOR = (
    config.PIN_MATRIZ_SELECTOR_A,
    config.PIN_MATRIZ_SELECTOR_B,
    config.PIN_MATRIZ_SELECTOR_C,
)
_PINES_MATRIZ = (*_PINES_SELECTOR, config.PIN_MATRIZ_CARGA, config.PIN_MATRIZ_RELOJ, config.PIN_MATRIZ_DATOS)

# Pata física del 74HC138 de cada salida Y0..Y7 y del 74HC165 de cada entrada D0..D7,
# para saber dónde medir con el multímetro.
PATA_DE_SALIDA_138 = (15, 14, 13, 12, 11, 10, 9, 7)
PATA_DE_ENTRADA_165 = (11, 12, 13, 14, 3, 4, 5, 6)

# Por debajo de esto `time.sleep` no tiene resolución (en la Pi duerme bastante más de
# lo pedido): se espera activamente. Solo pasa con las esperas cortas de la calibración.
_ESPERA_ACTIVA_HASTA = 0.0005


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


def elegir_fila(salida: int) -> None:
    """Escribe `salida` en A/B/C: el 74HC138 pone en LOW esa salida Y y deja las demás en HIGH."""
    for bit, pin in enumerate(_PINES_SELECTOR):
        GPIO.output(pin, GPIO.HIGH if salida >> bit & 1 else GPIO.LOW)


def leer_columnas() -> tuple[bool, ...]:
    """Lee las 8 entradas del 74HC165 de la fila ya seleccionada, indexadas D0..D7.

    Tras el pulso de carga, Q7 ya muestra D7; cada flanco de subida de CLK
    desplaza la siguiente (D6, D5, ... D0). Una columna en LOW es un sensor activo
    contra la fila elegida (Hall con imán, o reed cerrado), o sea pieza presente.
    """
    GPIO.output(config.PIN_MATRIZ_CARGA, GPIO.LOW)
    GPIO.output(config.PIN_MATRIZ_CARGA, GPIO.HIGH)
    leidas = []
    for _ in range(8):
        leidas.append(GPIO.input(config.PIN_MATRIZ_DATOS) == GPIO.LOW)
        GPIO.output(config.PIN_MATRIZ_RELOJ, GPIO.HIGH)
        GPIO.output(config.PIN_MATRIZ_RELOJ, GPIO.LOW)
    return tuple(reversed(leidas))  # se leyó D7 primero


def esperar(segundos: float) -> None:
    if segundos >= _ESPERA_ACTIVA_HASTA:
        time.sleep(segundos)
        return
    fin = time.perf_counter() + segundos
    while time.perf_counter() < fin:
        pass


def leer_matriz(espera: float) -> MatrizCruda:
    """Barre las 8 filas y devuelve la matriz cruda, sin antirrebote ni mapeo a casillas.

    `espera` son los segundos que se esperan en cada fila después de elegirla y antes de
    cargar las columnas: lo que tardan en estabilizarse la fila (cables largos) y, con los
    Hall, lo que tardan en encender.
    """
    filas = []
    for salida in range(8):
        elegir_fila(salida)
        esperar(espera)
        filas.append(leer_columnas())
    return tuple(filas)


class LectorMatriz:
    """Lectura con antirrebote: solo reporta una matriz que se repitió N veces seguidas.

    Cada versión de sensor tiene su subclase con su espera y su N por defecto
    (`sensores.LectorMatriz`, `sensores_reed.LectorMatriz`).
    """

    def __init__(self, espera: float, lecturas_estables: int) -> None:
        self.espera = espera
        self._lecturas_estables = lecturas_estables
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida lo leído: la próxima matriz estable se devuelve aunque no haya cambiado."""
        self._candidata: MatrizCruda | None = None
        self._repeticiones = 0
        self.estable: MatrizCruda | None = None

    def leer(self) -> MatrizCruda | None:
        """Hace una lectura; devuelve la nueva matriz estable si cambió, si no `None`."""
        lectura = leer_matriz(self.espera)
        if lectura == self._candidata:
            self._repeticiones += 1
        else:
            self._candidata, self._repeticiones = lectura, 1
        if self._repeticiones >= self._lecturas_estables and lectura != self.estable:
            self.estable = lectura
            return lectura
        return None

    def esperar_estable(self) -> MatrizCruda:
        """Olvida lo leído y espera la próxima matriz estable, aunque sea igual a la anterior."""
        self.reiniciar()
        while (matriz := self.leer()) is None:
            time.sleep(0.01)
        return matriz


def formatear_matriz(matriz: MatrizCruda) -> str:
    lineas = ["      " + " ".join(f"D{d}" for d in range(8))]
    for salida, fila in enumerate(matriz):
        lineas.append(f"  Y{salida}   " + "  ".join("#" if ocupada else "." for ocupada in fila))
    return "\n".join(lineas)


def formatear_tablero(casillas: frozenset[chess.Square]) -> str:
    lineas = []
    for fila in range(7, -1, -1):
        celdas = "  ".join("#" if chess.square(col, fila) in casillas else "." for col in range(8))
        lineas.append(f"  {fila + 1}   {celdas}")
    lineas.append("      " + "  ".join("abcdefgh"))
    return "\n".join(lineas)


def mostrar_en_vivo(
    lector: LectorMatriz,
    a_casillas: Callable[[MatrizCruda], frozenset[chess.Square]],
    leyenda: str,
) -> None:
    """Muestra en vivo la matriz cruda y el tablero mapeado; loguea cada cambio. Ctrl+C sale.

    `a_casillas` es el mapeo de la versión de sensor (`ocupacion()` de cada módulo) y
    `leyenda`, qué significa un `#` en la matriz cruda.
    """
    configurar_matriz()
    anteriores: frozenset[chess.Square] = frozenset()
    logger.info("Leyendo la matriz (Ctrl+C para salir)...")
    try:
        while True:
            matriz = lector.leer()
            if matriz is not None:
                actuales = a_casillas(matriz)
                print("\033[2J\033[H", end="")  # limpia la terminal
                print(f"Matriz cruda (# = {leyenda}):")
                print(formatear_matriz(matriz))
                print(f"\nTablero mapeado ({len(actuales)} piezas):")
                print(formatear_tablero(actuales))
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


def probar_selector() -> None:
    """Activa Y0..Y7 del 74HC138 de a una, esperando Enter, para medirlas con el multímetro.

    Prueba el 138 solo, sin depender del 74HC165. La salida activa tiene que dar ~0 V y
    las demás ~3,3 V; diagnóstico en software-docs/sensores.md, "Pruebas por chip".
    """
    GPIO.setmode(GPIO.BOARD)
    for pin in _PINES_SELECTOR:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    try:
        for salida in range(8):
            elegir_fila(salida)
            input(
                f"Y{salida} activa: pata {PATA_DE_SALIDA_138[salida]} del 138 en ~0 V, "
                "las otras Y en ~3,3 V. Enter para seguir... "
            )
        print("Listo, se recorrieron las 8 salidas.")
    except KeyboardInterrupt:
        print("\nPrueba cancelada.")
    finally:
        GPIO.cleanup(list(_PINES_SELECTOR))


def probar_lector() -> None:
    """Prueba el 74HC165 sin el 138: que maneje el pin de datos y que desplace los bits.

    1. Con SH/LD en LOW la salida del 165 copia en vivo la entrada D7: se lee el pin con
       pull-up y con pull-down. Si la lectura sigue al pull, nadie maneja el pin.
    2. Se cargan las columnas y se dan 8 pulsos de reloj: la salida tiene que pasar de D7
       (1 con el tablero vacío) a lo que entra por SER, que está a GND (0). Si sigue en 1,
       el chip carga pero no desplaza, y `matriz` solo ve la columna de D7.

    Correr con el tablero vacío; diagnóstico en software-docs/sensores.md, "Pruebas por chip".
    """
    GPIO.setwarnings(False)  # el pin de datos se configura dos veces, con pulls distintos
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(config.PIN_MATRIZ_CARGA, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(config.PIN_MATRIZ_RELOJ, GPIO.OUT, initial=GPIO.LOW)
    lecturas = {}
    try:
        for pull, nombre in ((GPIO.PUD_UP, "pull-up"), (GPIO.PUD_DOWN, "pull-down")):
            GPIO.setup(config.PIN_MATRIZ_DATOS, GPIO.IN, pull_up_down=pull)
            time.sleep(0.05)
            lecturas[nombre] = [GPIO.input(config.PIN_MATRIZ_DATOS) for _ in range(16)]
            print(nombre, lecturas[nombre])

        GPIO.output(config.PIN_MATRIZ_CARGA, GPIO.LOW)
        GPIO.output(config.PIN_MATRIZ_CARGA, GPIO.HIGH)
        recien_cargado = GPIO.input(config.PIN_MATRIZ_DATOS)
        for _ in range(8):
            GPIO.output(config.PIN_MATRIZ_RELOJ, GPIO.HIGH)
            GPIO.output(config.PIN_MATRIZ_RELOJ, GPIO.LOW)
        tras_reloj = GPIO.input(config.PIN_MATRIZ_DATOS)
        print(f"desplazamiento: recién cargado {recien_cargado}, después de 8 pulsos de reloj {tras_reloj}")
    finally:
        GPIO.cleanup([config.PIN_MATRIZ_CARGA, config.PIN_MATRIZ_RELOJ, config.PIN_MATRIZ_DATOS])

    arriba, abajo = set(lecturas["pull-up"]), set(lecturas["pull-down"])
    if arriba == {1} and abajo == {0}:
        print("FALLA: nadie maneja el pin (cable de la pata 9, o el 165 sin Vcc/GND, al revés o dañado).")
    elif arriba == abajo == {0}:
        print("FALLA: el 165 maneja el pin pero D7 está en LOW (¿tablero vacío? ¿pull-up de esa columna?).")
    elif arriba != {1} or abajo != {1}:
        print("FALLA: lecturas mezcladas, probable falso contacto.")
    elif (recien_cargado, tras_reloj) == (1, 1):
        print(
            "FALLA: el 165 carga pero no desplaza (CLK pata 2 → pin 31, INH pata 15 a GND, "
            "SH/LD y CLK cruzados) o SER (pata 10) no está a GND."
        )
    elif (recien_cargado, tras_reloj) != (1, 0):
        print("FALLA: el desplazamiento dio un resultado inesperado, probable falso contacto.")
    else:
        print("OK: el 165 maneja el pin, D7 está en HIGH y desplaza los bits.")
