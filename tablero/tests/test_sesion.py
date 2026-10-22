"""Tests de SesionPvP y SesionMagnus (tablero/src/tablero/logica/sesion.py).

Sin hardware ni Stockfish: la fuente de ocupación es una "mano" que mueve piezas, los LEDs
anotan lo que se pinta, el motor es una función y el reloj es la fixture `tiempo`.
"""

import threading

import chess
import pytest

from tablero.logica.eventos import Marca, casillas_ocupadas
from tablero.logica.partida_magnus import Fase
from tablero.logica.registro import RegistroPartida
from tablero.logica.sesion import ErrorTablero, FaseSesion, SesionMagnus, SesionPvP

INICIAL = casillas_ocupadas(chess.Board())


class _Fuente:
    """Las piezas físicas: `leer()` devuelve la ocupación solo si cambió, como el LectorMatriz."""

    def __init__(self, ocupacion=INICIAL) -> None:
        self.ocupacion = frozenset(ocupacion)
        self._entregada = None
        self.error: Exception | None = None

    def leer(self):
        if self.error is not None:
            raise self.error
        if self.ocupacion == self._entregada:
            return None
        self._entregada = self.ocupacion
        return self.ocupacion

    def mover(self, origen: str, destino: str) -> None:
        o, d = chess.parse_square(origen), chess.parse_square(destino)
        self.ocupacion = (self.ocupacion - {o, d}) | {d}


class _Leds:
    def __init__(self) -> None:
        self.marcas: dict[chess.Square, Marca] = {}

    def __call__(self, marcas) -> None:
        self.marcas = dict(marcas)


def _pvp(tiempo, fuente=None, **kwargs):
    fuente = fuente or _Fuente()
    leds = _Leds()
    sesion = SesionPvP(300, fuente, leds, fuente_tiempo=tiempo, **kwargs)
    return sesion, fuente, leds


def _arrancar_pvp(sesion, tiempo):
    sesion.actualizar()
    sesion.pulsar_boton(chess.BLACK)
    tiempo.avanzar(4)
    sesion.actualizar()
    assert sesion.fase is FaseSesion.JUGANDO


def _jugar(sesion, fuente, color, origen, destino):
    fuente.mover(origen, destino)
    sesion.actualizar()
    sesion.pulsar_boton(color)


# -- Acomodar las piezas -------------------------------------------------------------


def test_acomodar_marca_lo_que_falta_y_sobra(tiempo):
    fuente = _Fuente(INICIAL - {chess.E2} | {chess.E4})
    sesion, _, leds = _pvp(tiempo, fuente)

    assert sesion.actualizar()

    assert sesion.fase is FaseSesion.PREPARANDO
    assert sesion.faltan == {chess.E2}
    assert sesion.sobran == {chess.E4}
    assert leds.marcas == {chess.E2: Marca.FALTA, chess.E4: Marca.SOBRA}
    assert not sesion.posicion_lista
    sesion.pulsar_boton(chess.WHITE)
    assert sesion.fase is FaseSesion.PREPARANDO, "con piezas mal puestas el botón no arranca"


def test_posicion_lista_y_cuenta_regresiva(tiempo):
    sesion, _, leds = _pvp(tiempo)
    sesion.actualizar()
    assert sesion.posicion_lista
    assert set(leds.marcas) == INICIAL

    sesion.pulsar_boton(chess.BLACK)
    assert sesion.fase is FaseSesion.CUENTA_REGRESIVA
    assert sesion.paso_cuenta_regresiva == 0
    tiempo.avanzar(2.5)
    assert sesion.actualizar()
    assert sesion.paso_cuenta_regresiva == 2
    tiempo.avanzar(1.5)
    sesion.actualizar()

    assert sesion.fase is FaseSesion.JUGANDO
    assert sesion.turno == chess.WHITE
    assert sesion.restante(chess.WHITE) == 300
    assert leds.marcas == {}


# -- Partida PvP ---------------------------------------------------------------------


def test_jugada_y_boton_pasan_el_turno(tiempo):
    sesion, fuente, _ = _pvp(tiempo)
    _arrancar_pvp(sesion, tiempo)

    fuente.mover("e2", "e4")
    sesion.actualizar()
    assert "e2→e4" in sesion.linea_estado
    sesion.pulsar_boton(chess.WHITE)

    assert sesion.turno == chess.BLACK
    assert sesion.linea_estado == ""


def test_boton_rechazado_queda_en_la_linea_de_estado(tiempo):
    sesion, fuente, _ = _pvp(tiempo)
    _arrancar_pvp(sesion, tiempo)

    fuente.mover("e2", "d4")
    sesion.actualizar()
    sesion.pulsar_boton(chess.WHITE)

    assert sesion.linea_estado.startswith("Botón de blancas: no es una jugada legal")
    assert sesion.turno == chess.WHITE
    fuente.mover("d4", "e4")
    sesion.actualizar()
    assert not sesion.linea_estado.startswith("Botón"), "al mover piezas se borra el rechazo"


def test_el_reloj_pide_redibujar_una_vez_por_segundo(tiempo):
    sesion, _, _ = _pvp(tiempo)
    _arrancar_pvp(sesion, tiempo)
    sesion.actualizar()

    tiempo.avanzar(0.3)
    assert not sesion.actualizar()
    tiempo.avanzar(0.8)
    assert sesion.actualizar()


def test_sin_tiempo_termina(tiempo):
    sesion, _, leds = _pvp(tiempo)
    _arrancar_pvp(sesion, tiempo)

    tiempo.avanzar(301)
    sesion.actualizar()

    assert sesion.fase is FaseSesion.TERMINADA
    assert sesion.texto_final() == ("¡Blancas se quedaron sin tiempo!", "Ganan negras")
    assert leds.marcas == {}


def test_rendirse(tiempo):
    sesion, _, _ = _pvp(tiempo)
    _arrancar_pvp(sesion, tiempo)

    sesion.rendirse(chess.BLACK)

    assert sesion.fase is FaseSesion.TERMINADA
    assert sesion.texto_final() == ("Negras se rindieron", "Ganan blancas")


def test_tablas_por_acuerdo(tiempo, tmp_path):
    def crear_registro():
        return RegistroPartida(tmp_path, modo="tablero", segundos_por_jugador=300, max_partidas=5, max_detalles=5)

    sesion, _, _ = _pvp(tiempo, crear_registro=crear_registro)
    _arrancar_pvp(sesion, tiempo)

    sesion.ofrecer_tablas(chess.WHITE)
    assert sesion.oferta_tablas == chess.WHITE
    sesion.responder_tablas(acepta=True)

    assert sesion.fase is FaseSesion.TERMINADA
    assert sesion.texto_final() == ("Tablas por acuerdo", "½-½")
    assert len(list(tmp_path.glob("partidas/*.pgn"))) == 1


def test_jaque_mate(tiempo):
    sesion, fuente, _ = _pvp(tiempo)
    _arrancar_pvp(sesion, tiempo)

    for color, origen, destino in [
        (chess.WHITE, "f2", "f3"),
        (chess.BLACK, "e7", "e5"),
        (chess.WHITE, "g2", "g4"),
        (chess.BLACK, "d8", "h4"),
    ]:
        _jugar(sesion, fuente, color, origen, destino)

    assert sesion.fase is FaseSesion.TERMINADA
    assert sesion.texto_final() == ("¡Jaque mate!", "Ganan negras")


def test_cerrar_a_mitad_abandona_y_apaga(tiempo, tmp_path):
    def crear_registro():
        return RegistroPartida(tmp_path, modo="tablero", segundos_por_jugador=300, max_partidas=5, max_detalles=5)

    sesion, fuente, leds = _pvp(tiempo, crear_registro=crear_registro)
    _arrancar_pvp(sesion, tiempo)
    fuente.mover("e2", "e4")
    sesion.actualizar()
    assert leds.marcas

    sesion.cerrar()

    assert leds.marcas == {}
    assert "abandonada" in next(tmp_path.glob("detalle/*.log")).read_text(encoding="utf-8")


def test_la_falla_de_la_fuente_llega_a_la_pantalla(tiempo):
    sesion, fuente, _ = _pvp(tiempo)
    fuente.error = ErrorTablero("se desconectó el Nano")

    with pytest.raises(ErrorTablero, match="Nano"):
        sesion.actualizar()


# -- Contra Magnus -------------------------------------------------------------------


class _Motor:
    """Contesta con jugadas fijas; con `trabado`, no contesta hasta que se lo suelta."""

    def __init__(self, *jugadas: str) -> None:
        self._jugadas = [chess.Move.from_uci(u) for u in jugadas]
        self.soltar = threading.Event()
        self.soltar.set()

    def __call__(self, board: chess.Board) -> chess.Move:
        self.soltar.wait(timeout=5)
        return self._jugadas.pop(0)


def _magnus(tiempo, motor, color=chess.WHITE):
    fuente = _Fuente()
    leds = _Leds()
    sesion = SesionMagnus(color, fuente, leds, motor, fuente_tiempo=tiempo)
    sesion.actualizar()
    sesion.pulsar_boton(chess.WHITE)
    assert sesion.fase is FaseSesion.JUGANDO
    return sesion, fuente, leds


def _esperar_fase(sesion, fase):
    for _ in range(500):
        sesion.actualizar()
        if sesion.fase_partida is fase:
            return
        threading.Event().wait(0.01)
    raise AssertionError(f"no llegó a {fase}")


def test_magnus_contesta_sin_bloquear_y_su_jugada_se_hace_a_mano(tiempo):
    motor = _Motor("e7e5")
    motor.soltar.clear()
    sesion, fuente, leds = _magnus(tiempo, motor)
    try:
        _jugar(sesion, fuente, chess.WHITE, "e2", "e4")
        sesion.actualizar()
        assert sesion.fase_partida is Fase.MAGNUS_PENSANDO
        assert sesion.texto_estado == "Magnus está pensando…"

        motor.soltar.set()
        _esperar_fase(sesion, Fase.MOVER_MAGNUS)
        assert sesion.texto_estado.startswith("Magnus: peón e7→e5")
        assert leds.marcas == {chess.E7: Marca.MAGNUS_ORIGEN, chess.E5: Marca.MAGNUS_DESTINO}

        _jugar(sesion, fuente, chess.BLACK, "e7", "e5")
        assert sesion.fase_partida is Fase.TURNO_HUMANO
    finally:
        sesion.cerrar()


def test_magnus_con_negras_arranca_pensando(tiempo):
    sesion, _, _ = _magnus(tiempo, _Motor("e2e4"), color=chess.BLACK)
    try:
        _esperar_fase(sesion, Fase.MOVER_MAGNUS)
    finally:
        sesion.cerrar()


def test_rendirse_contra_magnus(tiempo):
    sesion, _, _ = _magnus(tiempo, _Motor())
    tiempo.avanzar(65)

    sesion.rendirse()
    sesion.cerrar()

    assert sesion.fase is FaseSesion.TERMINADA
    assert sesion.texto_estado == "Aguantaste 01:05 contra Magnus"


def test_si_el_motor_falla_la_partida_termina_con_el_error(tiempo):
    def motor(board):
        raise TimeoutError("sin respuesta")

    sesion, fuente, _ = _magnus(tiempo, motor)
    _jugar(sesion, fuente, chess.WHITE, "e2", "e4")
    for _ in range(500):
        sesion.actualizar()
        if sesion.fase is FaseSesion.TERMINADA:
            break
        threading.Event().wait(0.01)
    sesion.cerrar()

    assert sesion.texto_estado == "Magnus dejó de responder: sin respuesta"
