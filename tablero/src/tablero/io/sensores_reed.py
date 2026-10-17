"""Matriz de casillas, versión reed (la anterior): 64 reed switches con un diodo cada uno.

Se conserva por si se vuelve a los reed switches; la versión actual usa sensores Hall
(io/sensores.py). Los chips son los mismos, así que el barrido del 74HC138 + 74HC165
vive en io/matriz.py y lo comparten las dos versiones; acá solo queda lo propio de los
reed: la espera por fila, el antirrebote y el mapeo con dos permutaciones
(`FILA_DE_SALIDA_138`, `COLUMNA_DE_ENTRADA_165` en config.py).

Pruebas manuales en la Raspberry (ver software-docs/sensores-reed.md):

    uv run python -m tablero.io.sensores_reed selector
    uv run python -m tablero.io.sensores_reed lector
    uv run python -m tablero.io.sensores_reed matriz
    uv run python -m tablero.io.sensores_reed calibrar
"""

import argparse
import logging

import chess

from tablero import config
from tablero.io import matriz
from tablero.io.matriz import configurar_matriz, liberar_matriz
from tablero.logica.matriz import MatrizCruda, celdas_activas

# Tiempo para que la fila recién elegida en el 74HC138 se estabilice antes de
# cargar las columnas en el 74HC165. Sobra por mucho (el chip tarda nanosegundos),
# pero cubre la capacidad de los cables largos de la matriz.
_ESPERA_SELECCION_FILA = 0.0001


class LectorMatriz(matriz.LectorMatriz):
    """`io/matriz.py::LectorMatriz` con la espera y el antirrebote de los reed."""

    def __init__(self, lecturas_estables: int = config.REED_LECTURAS_ESTABLES) -> None:
        super().__init__(_ESPERA_SELECCION_FILA, lecturas_estables)


def casilla_de(salida: int, entrada: int) -> chess.Square:
    """Casilla de ajedrez de la celda cruda (salida Y del 138, entrada D del 165)."""
    return chess.square(config.COLUMNA_DE_ENTRADA_165[entrada], config.FILA_DE_SALIDA_138[salida])


def ocupacion(lectura: MatrizCruda) -> frozenset[chess.Square]:
    """Convierte la matriz cruda a la `Ocupacion` que espera `logica/eventos.py`."""
    return frozenset(casilla_de(salida, entrada) for salida, entrada in celdas_activas(lectura))


def probar_matriz() -> None:
    """Muestra en vivo la matriz cruda y el tablero mapeado; loguea cada cambio. Ctrl+C sale."""
    matriz.mostrar_en_vivo(LectorMatriz(), ocupacion, "reed cerrado")


def _esperar_celda_unica(lector: LectorMatriz, casilla: str) -> tuple[int, int] | None:
    input(f"Dejá UNA sola pieza, en {casilla}, y apretá Enter... ")
    activas = celdas_activas(lector.esperar_estable())
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
    parser = argparse.ArgumentParser(description="Pruebas manuales de la matriz, versión reed (la anterior).")
    parser.add_argument(
        "prueba",
        choices=["selector", "lector", "matriz", "calibrar"],
        help=(
            "selector: medir las salidas del 74HC138; lector: ver si el 74HC165 maneja el pin de "
            "datos y desplaza; matriz: ver la grilla en vivo; calibrar: generar el mapeo"
        ),
    )
    prueba = parser.parse_args().prueba
    {
        "selector": matriz.probar_selector,
        "lector": matriz.probar_lector,
        "matriz": probar_matriz,
        "calibrar": calibrar_matriz,
    }[prueba]()
