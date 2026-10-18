"""Tests de RastreadorMovimientos y marcas (tablero/src/tablero/logica/eventos.py).

No requieren hardware ni binarios externos, corren en cualquier máquina. Las lecturas de
sensores se simulan a mano como `frozenset[chess.Square]`, tal como las produce
`io/sensores.ocupacion()`. El rastreador nunca aplica la jugada: solo dice qué jugada
representa la posición física (la aplica `Partida` al apretar el reloj).
"""

import logging

import chess

from tablero.logica.estado_tablero import EstadoTablero
from tablero.logica.eventos import (
    Marca,
    RastreadorMovimientos,
    TipoLectura,
    casillas_ocupadas,
    marcas,
)

_FEN_CAPTURA = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2"  # 1.e4 d5
_FEN_CABALLO_DOS_CAPTURAS = "4k3/8/8/4p1p1/8/5N2/8/4K3 w - - 0 1"  # Cxe5 o Cxg5
_FEN_ENROQUE_CORTO = "4k3/8/8/8/8/8/8/4K2R w K - 0 1"
_FEN_ENROQUE_LARGO = "4k3/8/8/8/8/8/8/R3K3 w Q - 0 1"
_FEN_AL_PASO = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"  # el peón negro acaba de jugar d7-d5
_FEN_PROMOCION = "1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1"


def _rastreador(fen: str | None = None) -> tuple[RastreadorMovimientos, EstadoTablero]:
    estado = EstadoTablero(fen)
    return RastreadorMovimientos(estado), estado


class _Mano:
    """La mano del jugador: levanta y apoya piezas, y le pasa cada lectura al rastreador."""

    def __init__(self, rastreador: RastreadorMovimientos, estado: EstadoTablero) -> None:
        self._rastreador = rastreador
        self.ocupacion = casillas_ocupadas(estado.board)

    def levantar(self, casilla: chess.Square):
        assert casilla in self.ocupacion, f"no hay pieza en {chess.square_name(casilla)}"
        self.ocupacion = self.ocupacion - {casilla}
        return self._rastreador.procesar_ocupacion(self.ocupacion)

    def apoyar(self, casilla: chess.Square):
        assert casilla not in self.ocupacion, f"{chess.square_name(casilla)} ya está ocupada"
        self.ocupacion = self.ocupacion | {casilla}
        return self._rastreador.procesar_ocupacion(self.ocupacion)


def _mano(fen: str | None = None) -> tuple[_Mano, RastreadorMovimientos, EstadoTablero]:
    rastreador, estado = _rastreador(fen)
    return _Mano(rastreador, estado), rastreador, estado


# -- Movimientos simples --------------------------------------------------------------


def test_posicion_sin_cambios_es_reposo():
    rastreador, estado = _rastreador()

    lectura = rastreador.procesar_ocupacion(casillas_ocupadas(estado.board))

    assert lectura.tipo is TipoLectura.REPOSO
    assert marcas(lectura, estado.board) == {}


def test_movimiento_normal_se_detecta_sin_aplicarse():
    mano, _, estado = _mano()

    levantada = mano.levantar(chess.E2)
    apoyada = mano.apoyar(chess.E4)

    assert levantada.tipo is TipoLectura.INCOMPLETA
    assert levantada.faltan == {chess.E2}
    assert apoyada.tipo is TipoLectura.JUGADA
    assert apoyada.movimiento == chess.Move.from_uci("e2e4")
    assert estado.turno == chess.WHITE, "el rastreador no aplica nada"
    assert estado.board.piece_at(chess.E2) is not None


def test_pieza_repuesta_en_su_casilla_vuelve_a_reposo():
    mano, _, _ = _mano()

    mano.levantar(chess.G1)
    lectura = mano.apoyar(chess.G1)

    assert lectura.tipo is TipoLectura.REPOSO


def test_pieza_en_casilla_ilegal_es_incompleta_y_se_puede_corregir():
    mano, _, estado = _mano()

    mano.levantar(chess.E2)
    ilegal = mano.apoyar(chess.D4)

    assert ilegal.tipo is TipoLectura.INCOMPLETA
    assert ilegal.faltan == {chess.E2}
    assert ilegal.sobran == {chess.D4}
    assert marcas(ilegal, estado.board) == {
        chess.E2: Marca.ORIGEN,
        chess.E3: Marca.DESTINO,
        chess.E4: Marca.DESTINO,
        chess.D4: Marca.SOBRA,
    }

    mano.levantar(chess.D4)
    corregida = mano.apoyar(chess.E3)
    assert corregida.tipo is TipoLectura.JUGADA
    assert corregida.movimiento == chess.Move.from_uci("e2e3")


def test_cambiar_de_idea_antes_del_boton_detecta_la_ultima_posicion():
    mano, _, _ = _mano()

    mano.levantar(chess.E2)
    assert mano.apoyar(chess.E4).movimiento == chess.Move.from_uci("e2e4")
    mano.levantar(chess.E4)
    assert mano.apoyar(chess.E3).movimiento == chess.Move.from_uci("e2e3")


def test_pieza_del_rival_levantada_es_falta():
    mano, _, estado = _mano()

    lectura = mano.levantar(chess.E7)

    assert lectura.tipo is TipoLectura.INCOMPLETA
    assert marcas(lectura, estado.board) == {chess.E7: Marca.FALTA}


def test_pieza_levantada_muestra_sus_destinos():
    mano, _, estado = _mano()

    lectura = mano.levantar(chess.G1)

    assert marcas(lectura, estado.board) == {
        chess.G1: Marca.ORIGEN,
        chess.F3: Marca.DESTINO,
        chess.H3: Marca.DESTINO,
    }


def test_se_loguea_cada_pieza_levantada_y_apoyada(caplog):
    mano, _, _ = _mano()

    with caplog.at_level(logging.INFO):
        mano.levantar(chess.E2)
        mano.apoyar(chess.E4)

    assert "Jugada 1 (blancas): se levanta peón de e2" in caplog.text
    assert "aparece pieza en e4" in caplog.text
    assert "posición de e4" in caplog.text


# -- Capturas -------------------------------------------------------------------------


def test_captura_levantando_primero_la_atacante():
    mano, _, _ = _mano(_FEN_CAPTURA)

    mano.levantar(chess.E4)
    mano.levantar(chess.D5)
    lectura = mano.apoyar(chess.D5)

    assert lectura.tipo is TipoLectura.JUGADA
    assert lectura.movimiento == chess.Move.from_uci("e4d5")


def test_captura_sacando_primero_la_capturada():
    mano, _, estado = _mano(_FEN_CAPTURA)

    sacada = mano.levantar(chess.D5)
    assert marcas(sacada, estado.board) == {chess.E4: Marca.ORIGEN, chess.D5: Marca.DESTINO}
    mano.levantar(chess.E4)
    lectura = mano.apoyar(chess.D5)

    assert lectura.movimiento == chess.Move.from_uci("e4d5")


def test_captura_se_resuelve_por_la_casilla_que_se_vacio():
    mano, _, _ = _mano(_FEN_CABALLO_DOS_CAPTURAS)

    mano.levantar(chess.F3)
    mano.levantar(chess.G5)
    lectura = mano.apoyar(chess.G5)

    assert lectura.tipo is TipoLectura.JUGADA
    assert lectura.movimiento == chess.Move.from_uci("f3g5")
    assert len(lectura.candidatos) == 2


def test_pieza_rival_tocada_y_repuesta_no_confunde_la_captura():
    mano, _, _ = _mano(_FEN_CABALLO_DOS_CAPTURAS)

    mano.levantar(chess.E5)
    assert mano.apoyar(chess.E5).tipo is TipoLectura.REPOSO  # el historial se borra
    mano.levantar(chess.G5)
    mano.levantar(chess.F3)
    lectura = mano.apoyar(chess.G5)

    assert lectura.movimiento == chess.Move.from_uci("f3g5")


def test_captura_corregida_gana_la_casilla_ocupada_mas_reciente():
    mano, _, _ = _mano(_FEN_CABALLO_DOS_CAPTURAS)

    mano.levantar(chess.F3)
    mano.levantar(chess.E5)
    assert mano.apoyar(chess.E5).movimiento == chess.Move.from_uci("f3e5")
    # Se arrepiente: devuelve el peón a e5 (con el caballo en la mano) y captura en g5.
    mano.levantar(chess.E5)
    mano.apoyar(chess.E5)
    mano.levantar(chess.G5)
    lectura = mano.apoyar(chess.G5)

    assert lectura.movimiento == chess.Move.from_uci("f3g5")


def test_captura_sin_ver_vaciarse_la_casilla_es_ambigua_hasta_retocarla():
    rastreador, estado = _rastreador(_FEN_CABALLO_DOS_CAPTURAS)
    reposo = casillas_ocupadas(estado.board)

    # El antirrebote no llegó a ver vacía la casilla capturada: de una lectura a la
    # siguiente solo desapareció el caballo.
    ambigua = rastreador.procesar_ocupacion(reposo - {chess.F3})
    assert ambigua.tipo is TipoLectura.AMBIGUA
    assert marcas(ambigua, estado.board) == {
        chess.F3: Marca.JUGADA,
        chess.E5: Marca.DESTINO,
        chess.G5: Marca.DESTINO,
    }

    # Levantar y volver a apoyar la pieza que capturó lo resuelve.
    rastreador.procesar_ocupacion(reposo - {chess.F3, chess.G5})
    lectura = rastreador.procesar_ocupacion(reposo - {chess.F3})
    assert lectura.movimiento == chess.Move.from_uci("f3g5")


# -- Enroque, al paso y promoción -----------------------------------------------------


def test_enroque_corto_empezando_por_el_rey():
    mano, _, estado = _mano(_FEN_ENROQUE_CORTO)

    mano.levantar(chess.E1)
    assert mano.apoyar(chess.G1).tipo is TipoLectura.INCOMPLETA
    a_medias = mano.levantar(chess.H1)
    assert marcas(a_medias, estado.board) == {
        chess.E1: Marca.ORIGEN,
        chess.H1: Marca.ORIGEN,
        chess.G1: Marca.DESTINO,
        chess.F1: Marca.DESTINO,
    }
    lectura = mano.apoyar(chess.F1)

    assert lectura.tipo is TipoLectura.JUGADA
    assert lectura.movimiento == chess.Move.from_uci("e1g1")
    assert estado.board.is_castling(lectura.movimiento)
    assert marcas(lectura, estado.board) == dict.fromkeys(
        [chess.E1, chess.F1, chess.G1, chess.H1], Marca.JUGADA
    )


def test_enroque_empezando_por_la_torre_pasa_por_una_jugada_de_torre():
    mano, _, _ = _mano(_FEN_ENROQUE_CORTO)

    mano.levantar(chess.H1)
    torre = mano.apoyar(chess.F1)
    assert torre.movimiento == chess.Move.from_uci("h1f1"), "a esta altura es una jugada de torre"
    mano.levantar(chess.E1)
    lectura = mano.apoyar(chess.G1)

    assert lectura.movimiento == chess.Move.from_uci("e1g1")


def test_enroque_largo():
    mano, _, _ = _mano(_FEN_ENROQUE_LARGO)

    mano.levantar(chess.E1)
    mano.apoyar(chess.C1)
    mano.levantar(chess.A1)
    lectura = mano.apoyar(chess.D1)

    assert lectura.movimiento == chess.Move.from_uci("e1c1")


def test_al_paso_moviendo_primero_el_peon_propio():
    mano, _, estado = _mano(_FEN_AL_PASO)

    mano.levantar(chess.E5)
    assert mano.apoyar(chess.D6).tipo is TipoLectura.INCOMPLETA, "falta sacar el peón de d5"
    lectura = mano.levantar(chess.D5)

    assert lectura.movimiento == chess.Move.from_uci("e5d6")
    assert estado.board.is_en_passant(lectura.movimiento)
    assert marcas(lectura, estado.board) == dict.fromkeys(
        [chess.E5, chess.D6, chess.D5], Marca.JUGADA
    )


def test_al_paso_sacando_primero_el_peon_capturado():
    mano, _, _ = _mano(_FEN_AL_PASO)

    mano.levantar(chess.D5)
    mano.levantar(chess.E5)
    lectura = mano.apoyar(chess.D6)

    assert lectura.movimiento == chess.Move.from_uci("e5d6")


def test_promocion_se_resuelve_a_dama():
    mano, _, _ = _mano(_FEN_PROMOCION)

    mano.levantar(chess.A7)
    lectura = mano.apoyar(chess.A8)

    assert lectura.tipo is TipoLectura.JUGADA
    assert lectura.movimiento == chess.Move.from_uci("a7a8q")


def test_promocion_con_captura_se_resuelve_a_dama():
    mano, _, _ = _mano(_FEN_PROMOCION)

    mano.levantar(chess.A7)
    mano.levantar(chess.B8)
    lectura = mano.apoyar(chess.B8)

    assert lectura.movimiento == chess.Move.from_uci("a7b8q")


# -- Cambio del tablero lógico --------------------------------------------------------


def test_al_aplicarse_la_jugada_la_posicion_fisica_pasa_a_ser_reposo():
    mano, rastreador, estado = _mano(_FEN_CABALLO_DOS_CAPTURAS)
    mano.levantar(chess.F3)
    mano.levantar(chess.E5)
    jugada = mano.apoyar(chess.E5)

    estado.aplicar_movimiento(jugada.movimiento)

    assert rastreador.procesar_ocupacion(mano.ocupacion).tipo is TipoLectura.REPOSO
    lectura = mano.levantar(chess.E8)
    assert lectura.faltan == {chess.E8}, "se compara contra el tablero nuevo"
