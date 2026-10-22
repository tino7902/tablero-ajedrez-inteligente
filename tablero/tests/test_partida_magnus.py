"""Tests de PartidaVsMagnus (tablero/src/tablero/logica/partida_magnus.py).

No requieren hardware ni Stockfish: las jugadas de Magnus las pasa el test con
`recibir_jugada_motor`, las lecturas de la matriz se simulan con una "mano" que levanta y
apoya piezas (como en `test_partida_fisica.py`), y el reloj usa la fixture `tiempo`
(`RelojFalso`, en `conftest.py`).
"""

import chess
import pytest

from tablero.logica.eventos import Marca, casillas_ocupadas
from tablero.logica.partida_magnus import (
    Fase,
    PartidaVsMagnus,
    mensaje_final_magnus,
    nombres_pgn,
    validar_posicion_magnus,
)
from tablero.logica.registro import SUBDIR_DETALLE, RegistroPartida

# 1.e4 d5 2.Cc3: juegan las negras y pueden capturar en e4.
FEN_CAPTURA = "rnbqkbnr/ppp1pppp/8/3p4/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq - 1 2"
FEN_ENROQUES = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R b KQkq - 0 1"
FEN_AL_PASO = "4k3/8/8/8/3pP3/8/8/4K3 b - e3 0 1"
FEN_PROMOCION = "4k3/8/8/8/8/8/p7/1N2K3 b - - 0 1"
# 1.f3 e5 2.g4: las negras dan mate con Dh4.
FEN_MATE_DE_MAGNUS = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq g3 0 2"
FEN_MATE_TUYO = "6k1/5ppp/8/8/8/8/8/R6K w - - 0 1"
FEN_AHOGADO = "7k/8/8/6Q1/8/8/8/K7 w - - 0 1"


class _Mano:
    """Las piezas físicas: cada cambio se lo pasa a la partida como una lectura nueva."""

    def __init__(self, partida: PartidaVsMagnus) -> None:
        self._partida = partida
        self.ocupacion = casillas_ocupadas(partida.board)

    def levantar(self, nombre: str):
        self.ocupacion = self.ocupacion - {chess.parse_square(nombre)}
        return self._partida.procesar_ocupacion(self.ocupacion)

    def apoyar(self, nombre: str):
        self.ocupacion = self.ocupacion | {chess.parse_square(nombre)}
        return self._partida.procesar_ocupacion(self.ocupacion)

    def mover(self, origen: str, destino: str):
        """Levanta la pieza, retira la capturada si hay una, y la apoya en el destino."""
        self.levantar(origen)
        if chess.parse_square(destino) in self.ocupacion:
            self.levantar(destino)
        return self.apoyar(destino)


def _partida(tiempo, color_humano=chess.WHITE, **kwargs) -> tuple[PartidaVsMagnus, _Mano]:
    partida = PartidaVsMagnus(color_humano=color_humano, fuente_tiempo=tiempo, **kwargs)
    return partida, _Mano(partida)


def _recibir(partida: PartidaVsMagnus, uci: str):
    return partida.recibir_jugada_motor(chess.Move.from_uci(uci))


def _marcas(partida: PartidaVsMagnus) -> dict[str, Marca]:
    return {chess.square_name(sq): marca for sq, marca in partida.marcas().items()}


# -- Fases ------------------------------------------------------------------------


def test_humano_con_blancas_confirma_y_pasa_a_magnus_pensando(tiempo):
    partida, mano = _partida(tiempo)
    assert partida.fase is Fase.TURNO_HUMANO
    assert partida.texto_estado() == "Tu turno"

    mano.mover("e2", "e4")
    resultado = partida.pulsar_boton()

    assert resultado.confirmado
    assert resultado.jugada is not None
    assert resultado.jugada.san == "e4"
    assert partida.fase is Fase.MAGNUS_PENSANDO
    assert partida.texto_estado() == "Magnus está pensando…"


def test_mientras_magnus_piensa_el_boton_se_ignora(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "e4")
    partida.pulsar_boton()

    resultado = partida.pulsar_boton()

    assert not resultado.confirmado
    assert resultado.fase is Fase.MAGNUS_PENSANDO
    assert "pensando" in resultado.motivo
    assert partida.fase is Fase.MAGNUS_PENSANDO


def test_humano_con_negras_arranca_con_magnus_pensando(tiempo):
    partida, _ = _partida(tiempo, color_humano=chess.BLACK)

    assert partida.fase is Fase.MAGNUS_PENSANDO
    assert partida.color_magnus == chess.WHITE


def test_boton_sin_mover_en_tu_turno_dice_por_que(tiempo):
    partida, _ = _partida(tiempo)

    resultado = partida.pulsar_boton()

    assert not resultado.confirmado
    assert resultado.motivo == "no se movió ninguna pieza"


def test_board_para_motor_es_una_copia(tiempo):
    partida, _ = _partida(tiempo, color_humano=chess.BLACK)

    copia = partida.board_para_motor()
    copia.push_uci("e2e4")

    assert partida.board.piece_at(chess.E2) is not None


def test_mientras_magnus_piensa_solo_se_marca_lo_que_falta_o_sobra(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "e4")
    partida.pulsar_boton()

    mano.levantar("g8")  # una pieza de Magnus, antes de que conteste

    assert _marcas(partida) == {"g8": Marca.FALTA}


def test_en_tu_turno_las_marcas_son_las_de_pvp(tiempo):
    partida, mano = _partida(tiempo)

    mano.levantar("g1")

    assert _marcas(partida) == {"g1": Marca.ORIGEN, "f3": Marca.DESTINO, "h3": Marca.DESTINO}


# -- La jugada de Magnus ----------------------------------------------------------


def _magnus_contesta_cf6(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "e4")
    partida.pulsar_boton()
    _recibir(partida, "g8f6")
    return partida, mano


def test_la_jugada_de_magnus_espera_que_la_muevas(tiempo):
    partida, _ = _magnus_contesta_cf6(tiempo)

    assert partida.fase is Fase.MOVER_MAGNUS
    assert partida.partida.esperando_boton == chess.BLACK
    assert partida.texto_estado() == "Magnus: caballo g8→f6\nMovelo y apretá un botón"
    assert _marcas(partida) == {"g8": Marca.MAGNUS_ORIGEN, "f6": Marca.MAGNUS_DESTINO}


def test_boton_sin_mover_la_pieza_de_magnus_se_ignora(tiempo):
    # La última lectura era el reposo de antes de la jugada: se reinterpreta al recibirla.
    partida, _ = _magnus_contesta_cf6(tiempo)

    resultado = partida.pulsar_boton()

    assert not resultado.confirmado
    assert resultado.motivo == "la jugada de Magnus no está terminada: falta pieza en f6; sobra pieza en g8"
    assert partida.fase is Fase.MOVER_MAGNUS


def test_jugada_de_magnus_a_medio_mover_y_terminada(tiempo):
    partida, mano = _magnus_contesta_cf6(tiempo)

    mano.levantar("g8")
    assert _marcas(partida) == {"g8": Marca.MAGNUS_ORIGEN, "f6": Marca.MAGNUS_DESTINO}
    assert partida.pulsar_boton().motivo == "la jugada de Magnus no está terminada: falta pieza en f6"

    mano.apoyar("f6")
    assert _marcas(partida) == {"g8": Marca.JUGADA, "f6": Marca.JUGADA}
    resultado = partida.pulsar_boton()

    assert resultado.confirmado
    assert resultado.jugada is not None
    assert resultado.jugada.san == "Nf6"
    assert partida.fase is Fase.TURNO_HUMANO
    assert partida.partida.turno == chess.WHITE


def test_otra_diferencia_mientras_se_mueve_la_de_magnus_se_marca_aparte(tiempo):
    partida, mano = _magnus_contesta_cf6(tiempo)

    mano.levantar("a2")

    assert _marcas(partida) == {
        "g8": Marca.MAGNUS_ORIGEN,
        "f6": Marca.MAGNUS_DESTINO,
        "a2": Marca.FALTA,
    }


def test_tu_jugada_encima_de_la_de_magnus_sin_confirmar_se_ignora(tiempo):
    partida, mano = _magnus_contesta_cf6(tiempo)
    mano.mover("g8", "f6")
    mano.mover("d2", "d4")

    resultado = partida.pulsar_boton()

    assert not resultado.confirmado
    assert "primero hay que confirmar la jugada de Magnus" in resultado.motivo
    assert partida.board.piece_at(chess.D2) is not None

    mano.mover("d4", "d2")
    assert partida.pulsar_boton().confirmado


def test_captura_de_magnus(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_CAPTURA)

    _recibir(partida, "d5e4")

    assert partida.texto_estado().startswith("Magnus: peón d5→e4, captura el peón\n")
    assert _marcas(partida) == {"d5": Marca.MAGNUS_ORIGEN, "e4": Marca.MAGNUS_DESTINO}
    mano.mover("d5", "e4")
    assert partida.pulsar_boton().confirmado
    assert partida.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.BLACK)


def test_captura_de_magnus_con_su_pieza_en_la_mano_no_esta_hecha(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_CAPTURA)
    _recibir(partida, "d5e4")

    # La pieza de Magnus en la mano y tu peón todavía en e4: la ocupación es la de después
    # de la captura, pero falta sacar el peón.
    mano.levantar("d5")
    assert _marcas(partida) == {"d5": Marca.MAGNUS_ORIGEN, "e4": Marca.MAGNUS_DESTINO}
    resultado = partida.pulsar_boton()
    assert not resultado.confirmado
    assert resultado.motivo == (
        "la jugada de Magnus no está terminada: sacá la pieza de e4 y apoyá ahí la de Magnus "
        "(si ya lo hiciste, levantala y volvé a apoyarla)"
    )

    mano.levantar("e4")
    mano.apoyar("e4")
    assert _marcas(partida) == {"d5": Marca.JUGADA, "e4": Marca.JUGADA}
    assert partida.pulsar_boton().confirmado


@pytest.mark.parametrize(
    ("uci", "texto", "origenes", "destinos"),
    [
        ("e8g8", "Magnus enroca corto: rey e8→g8 y torre h8→f8", {"e8", "h8"}, {"g8", "f8"}),
        ("e8c8", "Magnus enroca largo: rey e8→c8 y torre a8→d8", {"e8", "a8"}, {"c8", "d8"}),
    ],
)
def test_enroque_de_magnus(tiempo, uci, texto, origenes, destinos):
    partida, mano = _partida(tiempo, fen=FEN_ENROQUES)

    _recibir(partida, uci)

    assert partida.texto_estado().splitlines()[0] == texto
    marcas = _marcas(partida)
    assert {sq for sq, m in marcas.items() if m is Marca.MAGNUS_ORIGEN} == origenes
    assert {sq for sq, m in marcas.items() if m is Marca.MAGNUS_DESTINO} == destinos
    rey_origen, torre_origen = sorted(origenes, key=lambda sq: sq != "e8")
    rey_destino = uci[2:4]
    torre_destino = (destinos - {rey_destino}).pop()
    mano.mover(rey_origen, rey_destino)
    mano.mover(torre_origen, torre_destino)
    assert partida.pulsar_boton().confirmado


def test_al_paso_de_magnus(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_AL_PASO)

    _recibir(partida, "d4e3")

    assert partida.texto_estado().splitlines()[0] == "Magnus: peón d4→e3, captura al paso el peón de e4"
    assert _marcas(partida) == {
        "d4": Marca.MAGNUS_ORIGEN,
        "e4": Marca.MAGNUS_ORIGEN,
        "e3": Marca.MAGNUS_DESTINO,
    }
    mano.levantar("e4")
    mano.mover("d4", "e3")
    assert partida.pulsar_boton().confirmado


def test_subpromocion_de_magnus_dice_que_pieza_poner(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_PROMOCION)

    _recibir(partida, "a2a1n")

    assert partida.texto_estado().splitlines()[0] == "Magnus: peón a2→a1, poné un caballo"
    mano.mover("a2", "a1")
    assert partida.pulsar_boton().confirmado
    assert partida.board.piece_at(chess.A1) == chess.Piece(chess.KNIGHT, chess.BLACK)


def test_promocion_con_captura_de_magnus(tiempo):
    partida, _ = _partida(tiempo, fen=FEN_PROMOCION)

    _recibir(partida, "a2b1q")

    assert partida.texto_estado().splitlines()[0] == "Magnus: peón a2→b1, captura el caballo y poné una dama"


def test_el_registro_anota_la_jugada_de_magnus_y_su_boton(tiempo, tmp_path):
    registro = RegistroPartida(tmp_path, modo="vs_magnus", segundos_por_jugador=None)
    partida, mano = _partida(tiempo, registro=registro)
    mano.mover("e2", "e4")
    partida.pulsar_boton()
    _recibir(partida, "g8f6")
    mano.mover("g8", "f6")
    partida.pulsar_boton()
    partida.finalizar()

    detalle = next((tmp_path / SUBDIR_DETALLE).iterdir()).read_text(encoding="utf-8")
    assert "negras  intenta 'g8f6' → ACEPTADO Nf6" in detalle
    assert "botón negras → TURNO PASADO a blancas" in detalle


# -- Errores de quien llama -------------------------------------------------------


def test_recibir_jugada_fuera_de_fase_es_un_error(tiempo):
    partida, _ = _partida(tiempo)

    with pytest.raises(ValueError):
        _recibir(partida, "e7e5")


def test_recibir_una_jugada_ilegal_es_un_error(tiempo):
    partida, _ = _partida(tiempo, color_humano=chess.BLACK)

    with pytest.raises(ValueError):
        _recibir(partida, "e2e5")
    assert partida.fase is Fase.MAGNUS_PENSANDO


# -- Fin de partida ---------------------------------------------------------------


def test_mate_de_magnus_termina_sin_boton_y_se_sigue_viendo(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_MATE_DE_MAGNUS)
    tiempo.avanzar(83)

    _recibir(partida, "d8h4")

    assert partida.fase is Fase.TERMINADA
    assert partida.partida.resultado() == "0-1"
    assert partida.mensaje_final() == "Aguantaste 01:23 contra Magnus"
    assert partida.texto_estado() == "Magnus: dama d8→h4\nAguantaste 01:23 contra Magnus"
    assert _marcas(partida) == {"d8": Marca.MAGNUS_ORIGEN, "h4": Marca.MAGNUS_DESTINO}
    mano.mover("d8", "h4")
    assert _marcas(partida) == {"d8": Marca.JUGADA, "h4": Marca.JUGADA}


def test_mate_tuyo_termina_sin_pedirle_jugada_a_magnus(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_MATE_TUYO)
    tiempo.avanzar(75)
    mano.mover("a1", "a8")

    resultado = partida.pulsar_boton()

    assert resultado.confirmado
    assert partida.fase is Fase.TERMINADA
    assert partida.mensaje_final() == "¡Derrotaste a Magnus en 01:15!"
    assert partida.texto_estado() == "¡Derrotaste a Magnus en 01:15!"
    assert partida.marcas() == {}


def test_el_cronometro_se_congela_al_terminar(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_MATE_TUYO)
    tiempo.avanzar(75)
    mano.mover("a1", "a8")
    partida.pulsar_boton()

    tiempo.avanzar(30)
    partida.actualizar_tiempo()

    assert partida.duracion == 75


def test_ahogado_son_tablas(tiempo):
    partida, mano = _partida(tiempo, fen=FEN_AHOGADO)
    mano.mover("g5", "g6")

    partida.pulsar_boton()

    assert partida.fase is Fase.TERMINADA
    assert partida.partida.resultado() == "1/2-1/2"
    assert partida.mensaje_final() == "Tablas con Magnus en 00:00"


def test_rendirse_con_una_jugada_de_magnus_sin_mover(tiempo):
    partida, _ = _magnus_contesta_cf6(tiempo)

    partida.rendirse()

    assert partida.fase is Fase.TERMINADA
    assert partida.partida.motivo_fin == "rendición"
    assert partida.partida.resultado() == "0-1"
    assert partida.mensaje_final() == "Aguantaste 00:00 contra Magnus"
    assert partida.marcas() == {}
    assert not partida.pulsar_boton().confirmado


def test_partida_abandonada_no_tiene_mensaje_final(tiempo):
    partida, _ = _partida(tiempo)

    partida.finalizar()

    assert partida.fase is Fase.TERMINADA
    assert partida.mensaje_final() is None


@pytest.mark.parametrize(
    ("resultado", "color_humano", "esperado"),
    [
        ("1-0", chess.WHITE, "¡Derrotaste a Magnus en 02:05!"),
        ("0-1", chess.BLACK, "¡Derrotaste a Magnus en 02:05!"),
        ("0-1", chess.WHITE, "Aguantaste 02:05 contra Magnus"),
        ("1-0", chess.BLACK, "Aguantaste 02:05 contra Magnus"),
        ("1/2-1/2", chess.WHITE, "Tablas con Magnus en 02:05"),
        ("*", chess.WHITE, None),
    ],
)
def test_mensaje_final_magnus(resultado, color_humano, esperado):
    assert mensaje_final_magnus(resultado, color_humano, 125.7) == esperado


def test_nombres_pgn_segun_tu_color():
    assert nombres_pgn(chess.WHITE, "fácil") == ("Jugador", "Magnus (fácil)")
    assert nombres_pgn(chess.BLACK, "difícil") == ("Magnus (difícil)", "Jugador")


def test_sin_los_dos_reyes_no_se_puede_jugar_contra_magnus(tiempo):
    # Stockfish no acepta posiciones sin rey: mejor fallar al arrancar que a mitad de partida.
    with pytest.raises(ValueError, match="rey"):
        PartidaVsMagnus(color_humano=chess.WHITE, fen="8/4p3/8/8/8/8/4P3/8 w - - 0 1", fuente_tiempo=tiempo)


def test_el_bando_que_no_mueve_en_jaque_no_se_puede_jugar_contra_magnus():
    with pytest.raises(ValueError, match="no es legal"):
        validar_posicion_magnus(chess.Board("4k3/8/8/8/8/8/4R3/4K3 w - - 0 1"))


def test_enroques_imposibles_en_el_fen_no_molestan_a_magnus():
    validar_posicion_magnus(chess.Board("4k3/8/8/8/8/8/8/4K3 w KQkq - 0 1"))
