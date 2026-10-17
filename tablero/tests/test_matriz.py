"""Tests de tablero/src/tablero/logica/matriz.py (procesamiento de lecturas de la matriz).

No requieren hardware: las lecturas crudas del 74HC138/74HC165 se arman a mano como
`MatrizCruda`, igual que las devolvería `io/matriz.py::leer_matriz()`.
"""

import ast

import chess
import pytest

from tablero import config
from tablero.logica.matriz import (
    cambios_por_celda,
    celdas_activas,
    es_grilla,
    espera_minima,
    formatear_tabla_config,
    lectura_mas_comun,
    ocupacion,
    racha_maxima_distinta,
    recomendar_espera,
    recomendar_lecturas_estables,
    tabla_desde_config,
)

_IDENTIDAD = tuple(
    tuple(chess.square_name(chess.square(entrada, salida)) for entrada in range(8)) for salida in range(8)
)


def _matriz(*celdas: tuple[int, int]) -> tuple[tuple[bool, ...], ...]:
    return tuple(tuple((salida, entrada) in celdas for entrada in range(8)) for salida in range(8))


def _con_fila(nombres, salida, fila):
    return tuple(fila if s == salida else original for s, original in enumerate(nombres))


# -- Tabla celda → casilla -----------------------------------------------------------


def test_tabla_identidad():
    tabla = tabla_desde_config(_IDENTIDAD)
    assert len(tabla) == 64
    assert tabla[(0, 0)] == chess.A1
    assert tabla[(0, 7)] == chess.H1
    assert tabla[(7, 0)] == chess.A8
    assert tabla[(3, 4)] == chess.E4


def test_tabla_de_config_es_valida():
    # Atrapa en la notebook un CASILLA_DE_CELDA_HALL mal pegado después de `mapear`.
    assert len(tabla_desde_config(config.CASILLA_DE_CELDA_HALL)) == 64


def test_tabla_rechaza_cantidad_de_filas_incorrecta():
    with pytest.raises(ValueError, match="8 filas"):
        tabla_desde_config(_IDENTIDAD[:7])


def test_tabla_rechaza_fila_corta():
    nombres = _con_fila(_IDENTIDAD, 2, _IDENTIDAD[2][:7])
    with pytest.raises(ValueError, match="Y2"):
        tabla_desde_config(nombres)


def test_tabla_rechaza_nombre_invalido():
    nombres = _con_fila(_IDENTIDAD, 5, ("z9", *_IDENTIDAD[5][1:]))
    with pytest.raises(ValueError, match="z9"):
        tabla_desde_config(nombres)


def test_tabla_rechaza_casilla_repetida():
    nombres = _con_fila(_IDENTIDAD, 1, ("a1", *_IDENTIDAD[1][1:]))
    with pytest.raises(ValueError, match="a1"):
        tabla_desde_config(nombres)


def test_tabla_acepta_mayusculas_y_espacios():
    nombres = _con_fila(_IDENTIDAD, 0, (" A1", *_IDENTIDAD[0][1:]))
    assert tabla_desde_config(nombres)[(0, 0)] == chess.A1


# -- Ocupación -----------------------------------------------------------------------


def test_celdas_activas():
    assert celdas_activas(_matriz()) == []
    assert celdas_activas(_matriz((0, 3), (6, 1))) == [(0, 3), (6, 1)]


def test_ocupacion_con_tabla_no_identidad():
    # Y0 lee la fila 8 al revés (D0 = h8 ... D7 = a8); el resto es la identidad.
    nombres = _con_fila(_IDENTIDAD, 7, _IDENTIDAD[0])
    nombres = _con_fila(nombres, 0, tuple(reversed(_IDENTIDAD[7])))
    tabla = tabla_desde_config(nombres)

    assert ocupacion(_matriz((0, 0), (0, 7), (3, 4)), tabla) == frozenset({chess.H8, chess.A8, chess.E4})
    assert ocupacion(_matriz(), tabla) == frozenset()


# -- Salida de `mapear` ---------------------------------------------------------------


def _asignacion_desde(nombres) -> dict[chess.Square, tuple[int, int]]:
    return {casilla: celda for celda, casilla in tabla_desde_config(nombres).items()}


def test_formatear_tabla_ida_y_vuelta():
    nombres = _con_fila(_IDENTIDAD, 4, tuple(reversed(_IDENTIDAD[4])))
    asignacion = _asignacion_desde(nombres)

    texto = formatear_tabla_config(asignacion)
    nombre, valor = texto.split(" = ", 1)

    assert nombre.startswith("CASILLA_DE_CELDA_HALL")
    releida = ast.literal_eval(valor)
    assert releida == nombres
    assert tabla_desde_config(releida) == tabla_desde_config(nombres)


def test_formatear_tabla_comenta_cada_salida():
    texto = formatear_tabla_config(_asignacion_desde(_IDENTIDAD))
    assert "# Y0: D0..D7" in texto
    assert "# Y7: D0..D7" in texto


def test_formatear_tabla_rechaza_asignacion_incompleta():
    asignacion = _asignacion_desde(_IDENTIDAD)
    del asignacion[chess.E4]
    with pytest.raises(ValueError):
        formatear_tabla_config(asignacion)


def test_es_grilla():
    assert es_grilla(_asignacion_desde(_IDENTIDAD))
    # Filas y columnas permutadas siguen siendo una grilla.
    permutada = tuple(tuple(reversed(fila)) for fila in reversed(_IDENTIDAD))
    assert es_grilla(_asignacion_desde(permutada))
    # Dos casillas intercambiadas entre filas distintas ya no lo son.
    intercambiada = _con_fila(_IDENTIDAD, 0, ("a2", *_IDENTIDAD[0][1:]))
    intercambiada = _con_fila(intercambiada, 1, ("a1", *_IDENTIDAD[1][1:]))
    assert not es_grilla(_asignacion_desde(intercambiada))


# -- Calibración: tiempo de encendido -----------------------------------------------------


def test_lectura_mas_comun():
    a, b = _matriz((0, 0)), _matriz((1, 1))
    assert lectura_mas_comun([a, b, a, a, b]) == a


def test_lectura_mas_comun_vacia():
    with pytest.raises(ValueError):
        lectura_mas_comun([])


def test_espera_minima_monotona():
    aciertos = {0.005: True, 0.002: True, 0.001: True, 0.0005: False, 0.0: False}
    assert espera_minima(aciertos) == 0.001


def test_espera_minima_ignora_aciertos_por_debajo_de_una_falla():
    # 0,2 ms anduvo de casualidad, pero 0,5 ms falló: no es confiable bajar de 1 ms.
    aciertos = {0.005: True, 0.001: True, 0.0005: False, 0.0002: True, 0.0: False}
    assert espera_minima(aciertos) == 0.001


def test_espera_minima_todas_bien():
    assert espera_minima({0.005: True, 0.001: True, 0.0: True}) == 0.0


def test_espera_minima_sin_ninguna_que_ande():
    assert espera_minima({0.005: False, 0.001: True, 0.0: True}) is None
    assert espera_minima({}) is None


def test_recomendar_espera():
    assert recomendar_espera(0.0) == 0.0001
    assert recomendar_espera(0.00002) == 0.0001
    assert recomendar_espera(0.0002) == 0.0004
    assert recomendar_espera(0.001) == 0.002


# -- Calibración: estabilidad ---------------------------------------------------------


def test_racha_maxima_distinta():
    ref, x, y = _matriz((0, 0)), _matriz((0, 0), (2, 2)), _matriz()
    assert racha_maxima_distinta([], ref) == 0
    assert racha_maxima_distinta([ref, ref, ref], ref) == 0
    assert racha_maxima_distinta([ref, x, x, ref, y, ref], ref) == 2
    # Lecturas distintas entre sí no forman racha: el antirrebote no las dejaría pasar.
    assert racha_maxima_distinta([x, y, x, y], ref) == 1
    assert racha_maxima_distinta([ref, y, y, y], ref) == 3


def test_cambios_por_celda():
    a = _matriz((0, 0))
    b = _matriz((0, 0), (5, 3))
    c = _matriz()
    assert cambios_por_celda([a, a, a]) == {}
    assert cambios_por_celda([a, b, a, b]) == {(5, 3): 3}
    assert cambios_por_celda([a, c]) == {(0, 0): 1}
    assert cambios_por_celda([]) == {}


def test_recomendar_lecturas_estables():
    assert recomendar_lecturas_estables(0) == 3
    assert recomendar_lecturas_estables(1) == 3
    assert recomendar_lecturas_estables(2) == 4
    assert recomendar_lecturas_estables(5) == 7
