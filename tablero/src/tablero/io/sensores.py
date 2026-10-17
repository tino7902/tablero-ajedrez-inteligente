"""Entradas digitales del tablero: botones del reloj y matriz de casillas con sensores Hall.

- Botones del reloj: dos interruptores fin de carrera, detectados por flanco
  (ver hardware-docs/componentes.md, sección "Asignación de Pines GPIO").
- Matriz de ocupación: 64 sensores Hall A3144 / KY-003 barridos con un 74HC138 (elige
  la fila y, como el GND de cada Hall va a su salida Y, también la enciende) y un
  74HC165 (lee las 8 columnas). El barrido de los chips vive en io/matriz.py, común con
  la versión anterior de reed switches (io/sensores_reed.py); conexión de cada Hall en
  hardware-docs/celdas-hall.md.

Pruebas manuales en la Raspberry (ver software-docs/sensores.md y
hardware-docs/checklist-prueba-hall.md):

    uv run python -m tablero.io.sensores botones
    uv run python -m tablero.io.sensores selector
    uv run python -m tablero.io.sensores lector
    uv run python -m tablero.io.sensores medir Y0      (o una casilla: medir e4)
    uv run python -m tablero.io.sensores matriz
    uv run python -m tablero.io.sensores calibrar
    uv run python -m tablero.io.sensores mapear
"""

import argparse
import functools
import logging
import time
from collections.abc import Callable

import chess
import RPi.GPIO as GPIO

from tablero import config
from tablero.io import matriz
from tablero.io.matriz import configurar_matriz, leer_matriz, liberar_matriz
from tablero.logica import matriz as logica_matriz
from tablero.logica.matriz import Celda, MatrizCruda, celdas_activas

logger = logging.getLogger(__name__)

_NOMBRES_BOTONES = {
    config.PIN_BOTON_RELOJ_JUGADOR_1: "boton_1",
    config.PIN_BOTON_RELOJ_JUGADOR_2: "boton_2",
}


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


# -- Matriz de casillas (sensores Hall) ----------------------------------------------

_LEYENDA = "Hall activo"

# Esperas por fila que prueba `calibrar`, de la más larga a la más corta (segundos).
# La más larga es la referencia: con 5 ms cualquier Hall que funcione ya encendió.
_ESPERAS_A_PROBAR = (0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001, 0.00005, 0.00002, 0.0)
_ESPERA_REFERENCIA = _ESPERAS_A_PROBAR[0]
_BARRIDOS_POR_ESPERA = 30
_SEGUNDOS_REPOSO = 3
_SEGUNDOS_ESTABILIDAD = 10

_AVISO_POLARIDAD = "¿Imán al revés? El A3144 solo ve el polo sur."


class LectorMatriz(matriz.LectorMatriz):
    """`io/matriz.py::LectorMatriz` con la espera de encendido y el antirrebote de los Hall."""

    def __init__(
        self,
        espera: float = config.HALL_ESPERA_ENCENDIDO,
        lecturas_estables: int = config.HALL_LECTURAS_ESTABLES,
    ) -> None:
        super().__init__(espera, lecturas_estables)


@functools.cache
def _tabla() -> dict[Celda, chess.Square]:
    # Se valida recién al usar la matriz: un CASILLA_DE_CELDA_HALL mal pegado no tiene que
    # romper los botones del reloj, que también viven en este módulo.
    return logica_matriz.tabla_desde_config(config.CASILLA_DE_CELDA_HALL)


def casilla_de(salida: int, entrada: int) -> chess.Square:
    """Casilla de ajedrez de la celda cruda (salida Y del 138, entrada D del 165)."""
    return _tabla()[(salida, entrada)]


def ocupacion(lectura: MatrizCruda) -> frozenset[chess.Square]:
    """Convierte la matriz cruda a la `Ocupacion` que espera `logica/eventos.py`."""
    return logica_matriz.ocupacion(lectura, _tabla())


def _formatear_celdas(celdas: list[Celda]) -> str:
    return ", ".join(f"Y{s} D{d}" for s, d in celdas)


def _formatear_espera(segundos: float) -> str:
    return f"{segundos * 1000:g} ms"


def probar_matriz() -> None:
    """Muestra en vivo la matriz cruda y el tablero mapeado; loguea cada cambio. Ctrl+C sale."""
    matriz.mostrar_en_vivo(LectorMatriz(), ocupacion, _LEYENDA)


# -- medir ------------------------------------------------------------------------------


def _celda_a_medir(objetivo: str) -> tuple[int, int | None]:
    """'Y3' → (3, None); una casilla → su celda según CASILLA_DE_CELDA_HALL. ValueError si no."""
    objetivo = objetivo.strip().lower()
    if len(objetivo) == 2 and objetivo[0] == "y" and objetivo[1] in "01234567":
        return int(objetivo[1]), None
    casilla = chess.parse_square(objetivo)
    return next(celda for celda, sq in _tabla().items() if sq == casilla)


def medir(objetivo: str) -> None:
    """Deja fija una fila del 138 para medir con el multímetro y muestra lo que lee el 165.

    Barriendo, cada fila está encendida 1/8 del tiempo y el multímetro marca un promedio
    que no sirve; acá la fila queda fija hasta Ctrl+C. Sirve para medir lo que puede fallar
    con los Hall: que el 138 aguante la corriente de la fila, que los Hall tengan tensión y
    que la columna baje lo suficiente (ver hardware-docs/celdas-hall.md).
    """
    try:
        salida, entrada = _celda_a_medir(objetivo)
    except ValueError:
        print(f"No entiendo {objetivo!r}: usá una salida del 138 (Y0..Y7) o una casilla (por ejemplo e4).")
        return
    configurar_matriz()
    matriz.elegir_fila(salida)
    print(f"Y{salida} encendida fija. Multímetro en voltaje continuo, punta negra en GND (pata 8 del 138):")
    print(f"  1. Pata {matriz.PATA_DE_SALIDA_138[salida]} del 138 (Y{salida}): menos de 0,3 V.")
    print("  2. Punta negra en el GND de un Hall de esta fila y roja en su Vcc: 3 V o más.")
    if entrada is None:
        patas = ", ".join(map(str, matriz.PATA_DE_ENTRADA_165))
        print("  3. Poné una pieza en una casilla de esta fila: se marca un # abajo. La pata del 165")
        print(f"     de esa columna tiene que dar menos de 0,8 V (D0..D7 = patas {patas}).")
    else:
        pata = matriz.PATA_DE_ENTRADA_165[entrada]
        print(f"  3. Con la pieza en {objetivo.strip().lower()} (Y{salida} D{entrada}), pata {pata} del 165:")
        print("     menos de 0,8 V; sin la pieza, ~3,3 V.")
    print("Ctrl+C para salir.\n")
    print("        " + " ".join(f"D{d}" for d in range(8)))
    try:
        while True:
            marcas = "  ".join("#" if activa else "." for activa in matriz.leer_columnas())
            print(f"\r  Y{salida}     {marcas}   ", end="", flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()
    finally:
        liberar_matriz()


# -- calibrar ---------------------------------------------------------------------------


def _barrer_durante(segundos: float, espera: float) -> list[MatrizCruda]:
    fin = time.monotonic() + segundos
    lecturas = []
    while time.monotonic() < fin:
        lecturas.append(leer_matriz(espera))
    return lecturas


def _paso_reposo() -> None:
    input("Paso 1/3 · Reposo: sacá todas las piezas del tablero (y los imanes de cerca) y apretá Enter... ")
    lecturas = _barrer_durante(_SEGUNDOS_REPOSO, _ESPERA_REFERENCIA)
    activas = sorted({celda for lectura in lecturas for celda in celdas_activas(lectura)})
    if activas:
        print(f"  AVISO: sin piezas, estos Hall marcan pieza: {_formatear_celdas(activas)}.")
        print("  Hall dañado, mal cableado o un imán cerca. Hay que arreglarlo antes de `mapear`; se sigue igual.")
    else:
        print("  OK: ningún Hall marca pieza sin imán.")


def _paso_encendido() -> tuple[MatrizCruda, float] | None:
    while True:
        input("Paso 2/3 · Tiempo de encendido: armá la posición inicial (32 piezas) y apretá Enter... ")
        lecturas = [leer_matriz(_ESPERA_REFERENCIA) for _ in range(_BARRIDOS_POR_ESPERA)]
        referencia = logica_matriz.lectura_mas_comun(lecturas)
        if celdas_activas(referencia):
            break
        print(f"  No se detectó ninguna pieza. {_AVISO_POLARIDAD} Se repite.")
    print(
        f"  Referencia ({_formatear_espera(_ESPERA_REFERENCIA)} por fila): "
        f"{len(celdas_activas(referencia))} celdas activas."
    )
    print(matriz.formatear_matriz(referencia))
    aciertos = {}
    for espera in _ESPERAS_A_PROBAR:
        iguales = sum(leer_matriz(espera) == referencia for _ in range(_BARRIDOS_POR_ESPERA))
        aciertos[espera] = iguales == _BARRIDOS_POR_ESPERA
        print(f"  {_formatear_espera(espera):>8} por fila: {iguales}/{_BARRIDOS_POR_ESPERA} lecturas iguales a la referencia")
    minima = logica_matriz.espera_minima(aciertos)
    if minima is None:
        print(
            f"  FALLA: ni con {_formatear_espera(_ESPERA_REFERENCIA)} por fila se lee siempre igual. No es un "
            "problema de tiempo: revisar las tensiones con `medir` (ver hardware-docs/celdas-hall.md)."
        )
        return None
    espera = logica_matriz.recomendar_espera(minima)
    print(f"  La espera más corta que anduvo es {_formatear_espera(minima)}; se recomienda {_formatear_espera(espera)}.")
    return referencia, espera


def _paso_estabilidad(referencia: MatrizCruda, espera: float) -> int:
    input(
        f"Paso 3/3 · Estabilidad: dejá las piezas y no toques el tablero durante {_SEGUNDOS_ESTABILIDAD} s. "
        "Enter para empezar... "
    )
    lecturas = _barrer_durante(_SEGUNDOS_ESTABILIDAD, espera)
    estable = logica_matriz.lectura_mas_comun(lecturas)
    if estable != referencia:
        print("  Las piezas no son las mismas que en el paso 2; se toma como referencia lo que se leyó ahora.")
    racha = logica_matriz.racha_maxima_distinta(lecturas, estable)
    cambios = logica_matriz.cambios_por_celda(lecturas)
    print(f"  {len(lecturas)} lecturas en {_SEGUNDOS_ESTABILIDAD} s.")
    if cambios:
        detalle = ", ".join(f"Y{s} D{d} ({n} cambios)" for (s, d), n in sorted(cambios.items()))
        print(f"  Celdas que parpadearon: {detalle}.")
        print(f"  Racha más larga de lecturas falsas iguales: {racha}.")
    else:
        print("  OK: ninguna celda cambió.")
    return logica_matriz.recomendar_lecturas_estables(racha)


def calibrar() -> None:
    """Mide la espera de encendido y el antirrebote de los Hall (HALL_* de config.py).

    Tres pasos: reposo (tablero vacío: ningún Hall tiene que marcar), tiempo de encendido
    (con piezas, prueba esperas por fila cada vez más cortas contra una lectura de
    referencia) y estabilidad (10 s sin tocar, para elegir el antirrebote). Las cuentas
    están en logica/matriz.py; detalle en software-docs/sensores.md.
    """
    configurar_matriz()
    try:
        print("Calibración de los Hall, 3 pasos.\n")
        _paso_reposo()
        print()
        encendido = _paso_encendido()
        if encendido is None:
            return
        referencia, espera = encendido
        print()
        lecturas_estables = _paso_estabilidad(referencia, espera)
    except KeyboardInterrupt:
        print("\nCalibración cancelada.")
        return
    finally:
        liberar_matriz()
    print("\nCopiar en tablero/src/tablero/config.py (reemplazando los valores actuales):\n")
    print(f"HALL_ESPERA_ENCENDIDO: float = {espera}")
    print(f"HALL_LECTURAS_ESTABLES: int = {lecturas_estables}")


# -- mapear -----------------------------------------------------------------------------


def mapear() -> None:
    """Genera CASILLA_DE_CELDA_HALL de config.py: la pieza sola en cada una de las 64 casillas.

    Se usa una sola pieza: en cada paso se la mueve a la casilla que se pide y se aprieta
    Enter ('r' vuelve a la casilla anterior). De paso prueba que cada Hall detecte.
    """
    configurar_matriz()
    lector = LectorMatriz()
    asignacion: dict[chess.Square, Celda] = {}
    try:
        print("Mapeo de los Hall: sacá todas las piezas del tablero y quedate con una sola.\n")
        posicion = 0
        while posicion < len(chess.SQUARES):
            casilla = chess.SQUARES[posicion]
            nombre = chess.square_name(casilla)
            respuesta = input(
                f"[{posicion + 1}/64] Poné la pieza en {nombre} y apretá Enter ('r' repite la anterior)... "
            )
            if respuesta.strip().lower() == "r":
                if posicion == 0:
                    print("  No hay casilla anterior.")
                    continue
                posicion -= 1
                del asignacion[chess.SQUARES[posicion]]
                continue
            activas = celdas_activas(lector.esperar_estable())
            if not activas:
                print(f"  No se detectó la pieza. {_AVISO_POLARIDAD} Se repite.")
                continue
            if len(activas) > 1:
                print(f"  Se detectaron {len(activas)} celdas ({_formatear_celdas(activas)}), tiene que ser 1. Se repite.")
                continue
            celda = activas[0]
            anterior = next((sq for sq, c in asignacion.items() if c == celda), None)
            if anterior is not None:
                print(
                    f"  Y{celda[0]} D{celda[1]} ya quedó como {chess.square_name(anterior)}: ¿la pieza sigue ahí? "
                    "Si te equivocaste antes, 'r'. Se repite."
                )
                continue
            asignacion[casilla] = celda
            print(f"  {nombre} → Y{celda[0]} D{celda[1]}")
            posicion += 1
    except KeyboardInterrupt:
        print("\nMapeo cancelado.")
        return
    finally:
        liberar_matriz()

    print("\nCopiar en tablero/src/tablero/config.py, reemplazando las 10 líneas del CASILLA_DE_CELDA_HALL actual:\n")
    print(logica_matriz.formatear_tabla_config(asignacion))
    if logica_matriz.es_grilla(asignacion):
        print("\nEl cableado es una grilla: cada salida Y es una fila del tablero y cada entrada D una columna.")
    else:
        print(
            "\nOjo: el cableado no es una grilla (hay salidas Y con casillas de varias filas, o entradas D de "
            "varias columnas). La tabla funciona igual; si no era lo esperado, revisar el cableado."
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pruebas manuales de los sensores del tablero (matriz con Hall).")
    parser.add_argument(
        "prueba",
        nargs="?",
        default="botones",
        choices=["botones", "selector", "lector", "medir", "matriz", "calibrar", "mapear"],
        help=(
            "botones: reloj (por defecto); selector: medir las salidas del 74HC138; "
            "lector: ver si el 74HC165 maneja el pin de datos y desplaza; medir: dejar una fila fija "
            "para el multímetro; matriz: ver la grilla en vivo; calibrar: espera de encendido y "
            "antirrebote; mapear: generar la tabla celda → casilla"
        ),
    )
    parser.add_argument("objetivo", nargs="?", help="solo para medir: una salida del 138 (Y0..Y7) o una casilla (e4)")
    argumentos = parser.parse_args()
    if argumentos.prueba == "medir":
        if argumentos.objetivo is None:
            parser.error("medir necesita una salida del 138 o una casilla, por ejemplo: medir Y0")
        medir(argumentos.objetivo)
    elif argumentos.objetivo is not None:
        parser.error(f"{argumentos.prueba} no lleva argumentos")
    else:
        {
            "botones": probar_botones_reloj,
            "selector": matriz.probar_selector,
            "lector": matriz.probar_lector,
            "matriz": probar_matriz,
            "calibrar": calibrar,
            "mapear": mapear,
        }[argumentos.prueba]()
