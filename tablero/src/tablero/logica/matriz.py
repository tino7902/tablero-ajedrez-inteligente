"""Procesamiento de las lecturas crudas de la matriz de casillas, sin hardware.

`io/matriz.py` barre el 74HC138 + 74HC165 y devuelve una `MatrizCruda`; acá vive todo lo
que se hace con esas lecturas y no necesita GPIO: el mapeo celda → casilla de la versión
Hall (tabla de 64 en `config.CASILLA_DE_CELDA_HALL`), y las cuentas de la calibración de
`io/sensores.py` (tiempo de encendido de los Hall y antirrebote). Vive en `logica/` para
testearse off-device (`tests/test_matriz.py`), respetando el boundary de `CLAUDE.md`.
Detalle en software-docs/sensores.md.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

import chess

# matriz[salida Y del 74HC138][entrada D del 74HC165] → True si hay pieza.
MatrizCruda = tuple[tuple[bool, ...], ...]
# (salida Y del 138, entrada D del 165): la posición de un sensor en la matriz.
Celda = tuple[int, int]

# Espera mínima que se recomienda aunque los Hall respondan al instante: la misma que
# usaba la versión reed, que cubre la capacidad de los cables largos de la matriz.
_ESPERA_MINIMA_RECOMENDADA = 0.0001
_LECTURAS_ESTABLES_MINIMAS = 3


def celdas_activas(matriz: MatrizCruda) -> list[Celda]:
    return [(s, d) for s, fila in enumerate(matriz) for d, ocupada in enumerate(fila) if ocupada]


# -- Tabla celda → casilla -----------------------------------------------------------


def tabla_desde_config(nombres: Sequence[Sequence[str]]) -> dict[Celda, chess.Square]:
    """Valida `CASILLA_DE_CELDA_HALL` (8 salidas Y × 8 entradas D) y la pasa a un dict.

    Tira `ValueError` con la celda culpable: una forma distinta de 8×8, un nombre que
    no es casilla, o una casilla repetida (dos sensores no pueden ser la misma casilla).
    """
    if len(nombres) != 8:
        raise ValueError(f"CASILLA_DE_CELDA_HALL tiene que tener 8 filas (Y0..Y7), tiene {len(nombres)}")
    tabla: dict[Celda, chess.Square] = {}
    celda_de: dict[chess.Square, Celda] = {}
    for salida, fila in enumerate(nombres):
        if len(fila) != 8:
            raise ValueError(f"Y{salida} tiene {len(fila)} casillas, tiene que tener 8 (D0..D7)")
        for entrada, nombre in enumerate(fila):
            try:
                casilla = chess.parse_square(nombre.strip().lower())
            except ValueError:
                raise ValueError(f"Y{salida} D{entrada}: {nombre!r} no es una casilla (a1..h8)") from None
            if casilla in celda_de:
                s, d = celda_de[casilla]
                raise ValueError(
                    f"{chess.square_name(casilla)} aparece dos veces: Y{s} D{d} y Y{salida} D{entrada}"
                )
            tabla[(salida, entrada)] = casilla
            celda_de[casilla] = (salida, entrada)
    return tabla


def ocupacion(matriz: MatrizCruda, tabla: dict[Celda, chess.Square]) -> frozenset[chess.Square]:
    """Convierte la matriz cruda a la `Ocupacion` que espera `logica/eventos.py`."""
    return frozenset(tabla[celda] for celda in celdas_activas(matriz))


def formatear_tabla_config(asignacion: dict[chess.Square, Celda]) -> str:
    """Bloque `CASILLA_DE_CELDA_HALL` listo para pegar en config.py, una salida Y por línea."""
    if len(asignacion) != 64 or len(set(asignacion.values())) != 64:
        raise ValueError("La asignación tiene que cubrir las 64 casillas, cada una en una celda distinta")
    nombre_en: dict[Celda, str] = {celda: chess.square_name(casilla) for casilla, celda in asignacion.items()}
    lineas = ["CASILLA_DE_CELDA_HALL: tuple[tuple[str, ...], ...] = ("]
    for salida in range(8):
        nombres = ", ".join(f'"{nombre_en[(salida, entrada)]}"' for entrada in range(8))
        lineas.append(f"    ({nombres}),  # Y{salida}: D0..D7")
    lineas.append(")")
    return "\n".join(lineas)


def es_grilla(asignacion: dict[chess.Square, Celda]) -> bool:
    """True si cada salida Y es una sola fila de ajedrez y cada entrada D una sola columna.

    Solo informativo: la tabla de 64 funciona igual aunque el cableado no sea una grilla.
    """
    filas_de_salida: dict[int, set[int]] = {}
    columnas_de_entrada: dict[int, set[int]] = {}
    for casilla, (salida, entrada) in asignacion.items():
        filas_de_salida.setdefault(salida, set()).add(chess.square_rank(casilla))
        columnas_de_entrada.setdefault(entrada, set()).add(chess.square_file(casilla))
    return all(len(f) == 1 for f in filas_de_salida.values()) and all(
        len(c) == 1 for c in columnas_de_entrada.values()
    )


# -- Calibración: tiempo de encendido ---------------------------------------------------


def lectura_mas_comun(lecturas: Sequence[MatrizCruda]) -> MatrizCruda:
    if not lecturas:
        raise ValueError("No hay lecturas")
    return Counter(lecturas).most_common(1)[0][0]


def espera_minima(aciertos: dict[float, bool]) -> float | None:
    """La espera más corta tal que ella y todas las más largas leyeron bien.

    Un acierto por debajo de una espera que falló no cuenta: anduvo de casualidad.
    `None` si ni la espera más larga anduvo (o no hay datos).
    """
    minima = None
    for espera in sorted(aciertos, reverse=True):
        if not aciertos[espera]:
            break
        minima = espera
    return minima


def recomendar_espera(minima: float) -> float:
    """El doble de la mínima medida, de margen, sin bajar de 0,1 ms."""
    return round(max(2 * minima, _ESPERA_MINIMA_RECOMENDADA), 6)


# -- Calibración: estabilidad -----------------------------------------------------------


def racha_maxima_distinta(lecturas: Sequence[MatrizCruda], referencia: MatrizCruda) -> int:
    """Racha más larga de lecturas seguidas iguales entre sí y distintas de `referencia`.

    Es lo que mide si el antirrebote alcanza: `LectorMatriz` solo reporta una matriz que se
    repitió N veces seguidas, así que una racha de N lecturas falsas iguales pasaría.
    """
    maxima = racha = 0
    anterior = None
    for lectura in lecturas:
        racha = racha + 1 if lectura == anterior else 1
        anterior = lectura
        if lectura != referencia:
            maxima = max(maxima, racha)
    return maxima


def cambios_por_celda(lecturas: Sequence[MatrizCruda]) -> dict[Celda, int]:
    """Cuántas veces cambió cada celda entre lecturas consecutivas (solo las que cambiaron)."""
    cambios: Counter[Celda] = Counter()
    for anterior, actual in pairwise(lecturas):
        for salida in range(len(actual)):
            for entrada in range(len(actual[salida])):
                if anterior[salida][entrada] != actual[salida][entrada]:
                    cambios[(salida, entrada)] += 1
    return dict(cambios)


def recomendar_lecturas_estables(racha: int) -> int:
    """Lecturas iguales que tiene que pedir el antirrebote: la racha falsa más larga + 2."""
    return max(_LECTURAS_ESTABLES_MINIMAS, racha + 2)
