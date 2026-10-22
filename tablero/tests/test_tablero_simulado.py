"""Tests de TableroSimulado (tablero/src/tablero/logica/tablero_simulado.py)."""

import chess

from tablero.logica.estado_tablero import EstadoTablero
from tablero.logica.eventos import RastreadorMovimientos, TipoLectura, casillas_ocupadas
from tablero.logica.tablero_simulado import TableroSimulado

INICIAL = casillas_ocupadas(chess.Board())


def _lecturas(tablero: TableroSimulado) -> list:
    lecturas = []
    while (ocupacion := tablero.leer()) is not None:
        lecturas.append(ocupacion)
    return lecturas


def test_arranca_en_la_posicion_inicial_y_despues_no_cambia():
    tablero = TableroSimulado()

    assert tablero.leer() == INICIAL
    assert tablero.leer() is None


def test_jugada_normal_en_dos_pasos():
    tablero = TableroSimulado()
    tablero.leer()

    assert tablero.enviar("e2e4") is None

    assert _lecturas(tablero) == [INICIAL - {chess.E2}, INICIAL - {chess.E2} | {chess.E4}]


def test_captura_vacia_la_casilla_y_el_rastreador_la_detecta():
    estado = EstadoTablero("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
    rastreador = RastreadorMovimientos(estado)
    tablero = TableroSimulado()
    tablero.enviar("inicial")  # se reemplaza abajo por la posición del FEN
    _lecturas(tablero)
    tablero._ocupacion = casillas_ocupadas(estado.board)

    tablero.enviar("E4D5")
    lecturas = _lecturas(tablero)

    assert len(lecturas) == 3
    for ocupacion in lecturas:
        lectura = rastreador.procesar_ocupacion(ocupacion)
    assert lectura.tipo is TipoLectura.JUGADA
    assert lectura.movimiento == chess.Move.from_uci("e4d5")


def test_levantar_apoyar_e_inicial():
    tablero = TableroSimulado()
    tablero.leer()

    tablero.enviar("-e2")
    tablero.enviar("+e4")
    tablero.enviar("inicial")

    assert _lecturas(tablero) == [INICIAL - {chess.E2}, INICIAL - {chess.E2} | {chess.E4}, INICIAL]


def test_comando_que_no_se_entiende():
    tablero = TableroSimulado()

    assert "no entiendo" in tablero.enviar("caballo a f3")


def test_reiniciar_vuelve_a_entregar_la_ocupacion_actual():
    tablero = TableroSimulado()
    tablero.leer()

    tablero.reiniciar()

    assert tablero.leer() == INICIAL
    assert tablero.leer() is None
