"""Tests de Partida (tablero/src/tablero/logica/partida.py).

No requieren hardware. El foco está en la regla de las dos condiciones: el turno pasa
solo si el jugador correcto hizo un movimiento legal Y después presionó su botón.
El reloj usa la fixture `tiempo` (`RelojFalso`, en `conftest.py`) para que los tests
no dependan de cuánto tardan en correr.
"""

import chess

from tablero.logica.notacion import Idioma
from tablero.logica.partida import Partida, TipoBoton, TipoJugada


def _partida(tiempo, *, segundos: int | None = 300, fen=None, idioma=Idioma.ESPANOL) -> Partida:
    return Partida(
        segundos_por_jugador=segundos, idioma=idioma, fen=fen, fuente_tiempo=tiempo
    )


def _jugar(partida: Partida, texto: str):
    """Movimiento + botón, el ciclo completo de una jugada bien hecha."""
    resultado = partida.intentar_movimiento(texto)
    partida.pulsar_boton(resultado.turno)
    return resultado


# -- Condición 1: movimiento legal del jugador correcto ---------------------------


def test_movimiento_legal_se_acepta_pero_todavia_no_pasa_el_turno(tiempo):
    partida = _partida(tiempo)

    resultado = partida.intentar_movimiento("e4")

    assert resultado.tipo is TipoJugada.ACEPTADO
    assert resultado.san == "e4"
    assert partida.turno == chess.WHITE, "el turno no pasa hasta que se presione el botón"
    assert partida.esperando_boton == chess.WHITE


def test_movimiento_del_color_equivocado_se_bloquea(tiempo):
    partida = _partida(tiempo)

    resultado = partida.intentar_movimiento("Cf6")

    assert resultado.tipo is TipoJugada.BLOQUEADO_TURNO
    assert "negras" in resultado.motivo
    assert partida.estado.board.piece_at(chess.G8) is not None, "no se movió nada"


def test_pieza_que_no_esta_en_el_origen_se_bloquea(tiempo):
    partida = _partida(tiempo)

    resultado = partida.intentar_movimiento("a3a4")

    assert resultado.tipo is TipoJugada.BLOQUEADO_ILEGAL
    assert "no hay ninguna pieza en a3" in resultado.motivo


def test_pieza_que_no_puede_hacer_ese_movimiento_se_bloquea(tiempo):
    partida = _partida(tiempo)

    resultado = partida.intentar_movimiento("Dh5")

    assert resultado.tipo is TipoJugada.BLOQUEADO_ILEGAL
    assert "la dama de d1 no puede ir a h5" in resultado.motivo


def test_notacion_que_no_se_entiende_se_bloquea_aparte(tiempo):
    partida = _partida(tiempo)

    assert partida.intentar_movimiento("cualquier cosa").tipo is TipoJugada.BLOQUEADO_NOTACION


# -- Condición 2: el botón del reloj después de mover -----------------------------


def test_sin_presionar_el_boton_el_rival_no_puede_mover(tiempo):
    partida = _partida(tiempo)
    partida.intentar_movimiento("e4")

    resultado = partida.intentar_movimiento("Cf6")

    assert resultado.tipo is TipoJugada.BLOQUEADO_FALTA_RELOJ
    assert "blancas" in resultado.motivo


def test_sin_presionar_el_boton_tampoco_se_puede_mover_de_nuevo(tiempo):
    partida = _partida(tiempo)
    partida.intentar_movimiento("e4")

    assert partida.intentar_movimiento("Cf3").tipo is TipoJugada.BLOQUEADO_FALTA_RELOJ


def test_presionar_el_boton_sin_haber_movido_no_pasa_el_turno(tiempo):
    partida = _partida(tiempo)

    resultado = partida.pulsar_boton(chess.WHITE)

    assert resultado.tipo is TipoBoton.IGNORADO_SIN_MOVIMIENTO
    assert partida.turno == chess.WHITE


def test_presionar_el_boton_del_otro_jugador_no_hace_nada(tiempo):
    partida = _partida(tiempo)
    partida.intentar_movimiento("e4")

    resultado = partida.pulsar_boton(chess.BLACK)

    assert resultado.tipo is TipoBoton.IGNORADO_COLOR
    assert partida.turno == chess.WHITE
    assert partida.esperando_boton == chess.WHITE


def test_las_dos_condiciones_juntas_pasan_el_turno(tiempo):
    partida = _partida(tiempo)
    partida.intentar_movimiento("e4")

    resultado = partida.pulsar_boton(chess.WHITE)

    assert resultado.tipo is TipoBoton.TURNO_PASADO
    assert resultado.turno_nuevo == chess.BLACK
    assert partida.turno == chess.BLACK
    assert partida.esperando_boton is None


def test_secuencia_completa_de_varias_jugadas(tiempo):
    partida = _partida(tiempo)

    for texto in ("e4", "e5", "Cf3", "Cc6"):
        assert _jugar(partida, texto).tipo is TipoJugada.ACEPTADO

    assert partida.turno == chess.WHITE
    assert partida.estado.board.fullmove_number == 3


# -- Reloj ------------------------------------------------------------------------


def test_el_tiempo_le_corre_a_quien_movio_hasta_que_presiona_el_boton(tiempo):
    partida = _partida(tiempo)
    partida.intentar_movimiento("e4")

    tiempo.avanzar(20)  # se olvidó de apretar el reloj
    partida.actualizar_tiempo()

    assert partida.reloj.restante(chess.WHITE) == 280
    assert partida.reloj.restante(chess.BLACK) == 300


def test_quedarse_sin_tiempo_termina_la_partida_y_bloquea_todo(tiempo):
    partida = _partida(tiempo, segundos=30)

    assert partida.avanzar_tiempo(31)
    assert partida.terminada
    assert partida.motivo_fin == "tiempo"
    assert partida.resultado() == "0-1"
    assert partida.intentar_movimiento("e4").tipo is TipoJugada.BLOQUEADO_TIEMPO
    assert partida.pulsar_boton(chess.WHITE).tipo is TipoBoton.IGNORADO_TIEMPO


# -- Jugadas ya resueltas (las de los sensores) -----------------------------------


def test_intentar_jugada_aplica_un_move_con_las_mismas_reglas(tiempo):
    partida = _partida(tiempo)

    resultado = partida.intentar_jugada(chess.Move.from_uci("g1f3"))

    assert resultado.tipo is TipoJugada.ACEPTADO
    assert resultado.texto == "g1f3"
    assert resultado.san == "Nf3"
    assert resultado.descripcion == "caballo g1→f3"
    assert partida.esperando_boton == chess.WHITE


def test_intentar_jugada_ilegal_se_bloquea_con_el_motivo(tiempo):
    partida = _partida(tiempo)

    resultado = partida.intentar_jugada(chess.Move.from_uci("e2e5"))

    assert resultado.tipo is TipoJugada.BLOQUEADO_ILEGAL
    assert "el peón de e2 no puede ir a e5" in resultado.motivo
    assert partida.estado.board.piece_at(chess.E2) is not None


def test_intentar_jugada_tambien_espera_el_boton(tiempo):
    partida = _partida(tiempo)
    partida.intentar_jugada(chess.Move.from_uci("e2e4"))

    resultado = partida.intentar_jugada(chess.Move.from_uci("e7e5"))

    assert resultado.tipo is TipoJugada.BLOQUEADO_FALTA_RELOJ


# -- Fin de partida ---------------------------------------------------------------


def test_jaque_mate_termina_la_partida_sin_esperar_el_boton(tiempo):
    partida = _partida(tiempo)
    for texto in ("e4", "e5", "Ac4", "Cc6", "Dh5", "Cf6"):
        _jugar(partida, texto)

    resultado = partida.intentar_movimiento("Dxf7")  # mate del pastor

    assert resultado.tipo is TipoJugada.ACEPTADO
    assert partida.terminada
    assert partida.esperando_boton is None, "no hace falta apretar el reloj si ya es mate"
    assert partida.motivo_fin == "jaque mate"
    assert partida.resultado() == "1-0"


def test_partida_sin_terminar_da_resultado_abierto(tiempo):
    partida = _partida(tiempo)
    _jugar(partida, "e4")

    assert not partida.terminada
    assert partida.resultado() == "*"


def test_arrancar_desde_un_fen_pone_el_reloj_en_el_color_que_mueve(tiempo):
    partida = _partida(tiempo, fen="4k3/8/8/8/8/8/4P3/4K3 b - - 0 1")

    assert partida.turno == chess.BLACK
    assert partida.intentar_movimiento("Rd8").tipo is TipoJugada.ACEPTADO


# -- Sin límite y rendición (modo vs Magnus) --------------------------------------


def test_partida_sin_limite_nunca_termina_por_tiempo(tiempo):
    partida = _partida(tiempo, segundos=None)

    tiempo.avanzar(10_000)

    assert not partida.actualizar_tiempo()
    assert not partida.terminada
    assert partida.reloj.usado(chess.WHITE) == 10_000
    assert _jugar(partida, "e4").tipo is TipoJugada.ACEPTADO


def test_el_reloj_se_congela_cuando_termina_la_partida(tiempo):
    partida = _partida(tiempo, segundos=None)
    for texto in ("e4", "e5", "Ac4", "Cc6", "Dh5", "Cf6"):
        tiempo.avanzar(1)
        _jugar(partida, texto)
    tiempo.avanzar(1)
    partida.intentar_movimiento("Dxf7")  # mate del pastor

    tiempo.avanzar(60)
    partida.actualizar_tiempo()

    assert partida.reloj.duracion == 7


def test_rendirse_da_la_partida_al_otro_color(tiempo):
    partida = _partida(tiempo)
    _jugar(partida, "e4")

    partida.rendirse(chess.BLACK)

    assert partida.terminada
    assert partida.motivo_fin == "rendición"
    assert partida.resultado() == "1-0"
    assert partida.intentar_movimiento("e5").tipo is TipoJugada.BLOQUEADO_TERMINADA


def test_rendirse_con_la_partida_terminada_no_cambia_el_resultado(tiempo):
    partida = _partida(tiempo, segundos=30)
    partida.avanzar_tiempo(31)

    partida.rendirse(chess.BLACK)

    assert partida.motivo_fin == "tiempo"
    assert partida.resultado() == "0-1"
