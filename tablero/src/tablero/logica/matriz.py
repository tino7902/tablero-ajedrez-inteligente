"""Procesamiento de las lecturas crudas de la matriz de casillas, sin hardware.

`io/matriz.py` le pide cada barrido al Arduino Nano por el puerto serie y devuelve una
`MatrizCruda`; acá vive todo lo que se hace con esas lecturas y no necesita el hardware: el
mapeo celda → casilla de la versión Hall (tabla de 64 en `config.CASILLA_DE_CELDA_HALL`), las
cuentas de la calibración de `io/sensores.py` (tiempo de encendido de los Hall y
antirrebote) y el texto del protocolo del Nano (armar los comandos y decodificar las
respuestas). Vive en `logica/` para testearse off-device (`tests/test_matriz.py`),
respetando el boundary de `CLAUDE.md`. Detalle en software-docs/sensores.md y, el
protocolo, en software-docs/firmware-nano.md.
"""

from __future__ import annotations

import string
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

import chess

# matriz[fila Fk][columna Ck] → True si hay pieza. Fk y Ck son los números de cable de
# hardware-docs/matriz-hall-nano.md (en la v2 eran la salida Yk del 74HC138 y la entrada Dk
# del 74HC165; por eso las variables se llaman `salida` y `entrada`).
MatrizCruda = tuple[tuple[bool, ...], ...]
# (fila Fk, columna Ck): la posición de un sensor en la matriz.
Celda = tuple[int, int]

# Espera mínima que se recomienda aunque los Hall respondan al instante: la misma que
# usaba la versión reed, que cubre la capacidad de los cables largos de la matriz.
_ESPERA_MINIMA_RECOMENDADA = 0.0001
_LECTURAS_ESTABLES_MINIMAS = 3


def celdas_activas(matriz: MatrizCruda) -> list[Celda]:
    return [(s, d) for s, fila in enumerate(matriz) for d, ocupada in enumerate(fila) if ocupada]


# -- Tabla celda → casilla -----------------------------------------------------------


def tabla_desde_config(nombres: Sequence[Sequence[str]]) -> dict[Celda, chess.Square]:
    """Valida `CASILLA_DE_CELDA_HALL` (8 filas F × 8 columnas C) y la pasa a un dict.

    Tira `ValueError` con la celda culpable: una forma distinta de 8×8, un nombre que
    no es casilla, o una casilla repetida (dos sensores no pueden ser la misma casilla).
    """
    if len(nombres) != 8:
        raise ValueError(f"CASILLA_DE_CELDA_HALL tiene que tener 8 filas (F0..F7), tiene {len(nombres)}")
    tabla: dict[Celda, chess.Square] = {}
    celda_de: dict[chess.Square, Celda] = {}
    for salida, fila in enumerate(nombres):
        if len(fila) != 8:
            raise ValueError(f"F{salida} tiene {len(fila)} casillas, tiene que tener 8 (C0..C7)")
        for entrada, nombre in enumerate(fila):
            try:
                casilla = chess.parse_square(nombre.strip().lower())
            except ValueError:
                raise ValueError(f"F{salida} C{entrada}: {nombre!r} no es una casilla (a1..h8)") from None
            if casilla in celda_de:
                s, d = celda_de[casilla]
                raise ValueError(
                    f"{chess.square_name(casilla)} aparece dos veces: F{s} C{d} y F{salida} C{entrada}"
                )
            tabla[(salida, entrada)] = casilla
            celda_de[casilla] = (salida, entrada)
    return tabla


def ocupacion(matriz: MatrizCruda, tabla: dict[Celda, chess.Square]) -> frozenset[chess.Square]:
    """Convierte la matriz cruda a la `Ocupacion` que espera `logica/eventos.py`."""
    return frozenset(tabla[celda] for celda in celdas_activas(matriz))


def formatear_tabla_config(asignacion: dict[chess.Square, Celda]) -> str:
    """Bloque `CASILLA_DE_CELDA_HALL` listo para pegar en config.py, una fila F por línea."""
    if len(asignacion) != 64 or len(set(asignacion.values())) != 64:
        raise ValueError("La asignación tiene que cubrir las 64 casillas, cada una en una celda distinta")
    nombre_en: dict[Celda, str] = {celda: chess.square_name(casilla) for casilla, celda in asignacion.items()}
    lineas = ["CASILLA_DE_CELDA_HALL: tuple[tuple[str, ...], ...] = ("]
    for salida in range(8):
        nombres = ", ".join(f'"{nombre_en[(salida, entrada)]}"' for entrada in range(8))
        lineas.append(f"    ({nombres}),  # F{salida}: C0..C7")
    lineas.append(")")
    return "\n".join(lineas)


def es_grilla(asignacion: dict[chess.Square, Celda]) -> bool:
    """True si cada fila F es una sola fila de ajedrez y cada columna C una sola columna.

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


# -- Protocolo del Nano -------------------------------------------------------------------
# El texto que va y viene por el puerto serie (firmware/matriz-nano/, protocolo v1 en
# software-docs/firmware-nano.md). io/matriz.py manda y lee; acá se arman los comandos y se
# validan las respuestas, para que una línea mal formada nunca llegue como matriz.

LISTO_NANO = "LISTO matriz-nano 1"
_PREFIJO_LISTO = "LISTO matriz-nano "
# El firmware acepta `L <µs>` hasta 50000 µs por fila.
ESPERA_MAXIMA_NANO = 0.05
_ANALOGICO_MAXIMO = 1023


def version_listo(linea: str) -> str | None:
    """La versión de protocolo de un `LISTO matriz-nano N`, o `None` si la línea no es un LISTO."""
    linea = linea.strip()
    if not linea.startswith(_PREFIJO_LISTO):
        return None
    return linea.removeprefix(_PREFIJO_LISTO)


def comando_barrido(espera: float) -> str:
    """`L <µs>`: barrido completo, esperando `espera` segundos en cada fila (redondeado al µs)."""
    microsegundos = round(espera * 1_000_000)
    if not 0 <= microsegundos <= round(ESPERA_MAXIMA_NANO * 1_000_000):
        raise ValueError(
            f"La espera por fila tiene que estar entre 0 y {ESPERA_MAXIMA_NANO * 1000:g} ms, "
            f"no {espera * 1000:g} ms"
        )
    return f"L {microsegundos}"


def _campos(linea: str, prefijo: str, cantidad: int) -> list[str]:
    campos = linea.split()
    if len(campos) != cantidad + 1 or campos[0] != prefijo:
        raise ValueError(f"Respuesta inesperada del Nano: {linea!r}")
    return campos[1:]


def _byte(texto: str, linea: str) -> int:
    if len(texto) != 2 or any(c not in string.hexdigits for c in texto):
        raise ValueError(f"Byte inválido {texto!r} en la respuesta del Nano: {linea!r}")
    return int(texto, 16)


def _columnas(valor: int) -> tuple[bool, ...]:
    # Bit c = columna Ck, 1 = imán.
    return tuple(bool(valor >> columna & 1) for columna in range(8))


def decodificar_barrido(linea: str) -> MatrizCruda:
    """`M b0 … b7` (respuesta de `L`) → matriz cruda. `ValueError` si no tiene ese formato."""
    return tuple(_columnas(_byte(campo, linea)) for campo in _campos(linea, "M", 8))


def decodificar_columnas(linea: str) -> tuple[bool, ...]:
    """`C bb` (respuesta de `C`) → las 8 columnas C0..C7 de la fila encendida."""
    (campo,) = _campos(linea, "C", 1)
    return _columnas(_byte(campo, linea))


def decodificar_analogico(linea: str) -> tuple[int | None, ...]:
    """`A v0 … v7` (respuesta de `A`) → lectura del ADC (0–1023) de cada columna C0..C7.

    `None` en las columnas que no son analógicas (C0–C2 en el cableado normal).
    """
    valores: list[int | None] = []
    for campo in _campos(linea, "A", 8):
        if campo == "-":
            valores.append(None)
        elif campo.isascii() and campo.isdigit() and int(campo) <= _ANALOGICO_MAXIMO:
            valores.append(int(campo))
        else:
            raise ValueError(f"Valor analógico inválido {campo!r} en la respuesta del Nano: {linea!r}")
    return tuple(valores)
