"""Tests de RegistroPartida (tablero/src/tablero/logica/registro.py).

No requieren hardware: todo se escribe en el `tmp_path` de pytest, nunca en el
directorio de registros real del proyecto.
"""

import io

import chess
import chess.pgn

from tablero.logica.notacion import Idioma
from tablero.logica.partida import Partida
from tablero.logica.registro import SUBDIR_DETALLE, SUBDIR_PARTIDAS, RegistroPartida


def _registro(directorio, **kwargs) -> RegistroPartida:
    kwargs.setdefault("segundos_por_jugador", 300)
    return RegistroPartida(directorio, **kwargs)


def _partida_con_registro(directorio, tiempo, **kwargs):
    registro = _registro(directorio, **kwargs)
    partida = Partida(
        segundos_por_jugador=300,
        idioma=Idioma.ESPANOL,
        registro=registro,
        fuente_tiempo=tiempo,
    )
    return partida, registro


def _jugar(partida, texto):
    resultado = partida.intentar_movimiento(texto)
    if resultado.aceptado:
        partida.pulsar_boton(resultado.turno)
    return resultado


def _leer_pgn(ruta) -> chess.pgn.Game:
    return chess.pgn.read_game(io.StringIO(ruta.read_text(encoding="utf-8")))


def test_crea_los_dos_archivos_de_la_partida(tmp_path):
    registro = _registro(tmp_path)

    assert registro.ruta_pgn.parent == tmp_path / SUBDIR_PARTIDAS
    assert registro.ruta_log.parent == tmp_path / SUBDIR_DETALLE
    assert registro.ruta_pgn.exists()
    assert "partida iniciada" in registro.ruta_log.read_text(encoding="utf-8")


def test_el_pgn_guarda_los_movimientos_legales_y_el_resultado(tmp_path, tiempo):
    partida, registro = _partida_con_registro(tmp_path, tiempo)
    for texto in ("e4", "e5", "Ac4", "Cc6", "Dh5", "Cf6"):
        _jugar(partida, texto)
    partida.intentar_movimiento("Dxf7")  # mate del pastor
    partida.finalizar()

    juego = _leer_pgn(registro.ruta_pgn)

    assert [m.uci() for m in juego.mainline_moves()] == [
        "e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7",
    ]
    assert juego.headers["Result"] == "1-0"
    assert juego.headers["Termination"] == "jaque mate"
    assert juego.headers["TimeControl"] == "300"


def test_el_pgn_se_escribe_de_a_poco_sin_esperar_al_final(tmp_path, tiempo):
    partida, registro = _partida_con_registro(tmp_path, tiempo)

    _jugar(partida, "e4")

    juego = _leer_pgn(registro.ruta_pgn)
    assert [m.uci() for m in juego.mainline_moves()] == ["e2e4"]
    assert juego.headers["Result"] == "*", "la partida sigue en curso"


def test_partida_abandonada_queda_registrada_como_sin_terminar(tmp_path, tiempo):
    partida, registro = _partida_con_registro(tmp_path, tiempo)
    _jugar(partida, "e4")

    partida.finalizar()

    juego = _leer_pgn(registro.ruta_pgn)
    assert juego.headers["Result"] == "*"
    assert juego.headers["Termination"] == "abandonada"


def test_el_log_detalla_intentos_botones_y_estado_del_reloj(tmp_path, tiempo):
    partida, registro = _partida_con_registro(tmp_path, tiempo)

    partida.intentar_movimiento("e4")
    partida.intentar_movimiento("Cf6")  # bloqueado: falta el reloj
    partida.pulsar_boton(chess.BLACK)  # botón equivocado
    tiempo.avanzar(65)
    partida.pulsar_boton(chess.WHITE)
    partida.finalizar()

    lineas = registro.ruta_log.read_text(encoding="utf-8").splitlines()

    assert "modo=simulacion" in lineas[0]
    assert "ACEPTADO e4 (peón e2→e4)" in lineas[1]
    assert "BLOQUEADO (BLOQUEADO_FALTA_RELOJ)" in lineas[2]
    assert "IGNORADO (IGNORADO_COLOR)" in lineas[3]
    assert "TURNO PASADO a negras" in lineas[4]
    assert "⏱ B 03:55 · N 05:00" in lineas[4], "el reloj queda anotado en cada cambio de turno"
    assert "partida finalizada — * (abandonada)" in lineas[5]


def test_el_log_anota_el_tiempo_agotado(tmp_path, tiempo):
    partida, registro = _partida_con_registro(tmp_path, tiempo)

    partida.avanzar_tiempo(400)
    partida.finalizar()

    contenido = registro.ruta_log.read_text(encoding="utf-8")
    assert "tiempo agotado: blancas" in contenido
    assert "partida finalizada — 0-1 (tiempo)" in contenido


def test_se_conservan_solo_las_ultimas_partidas_y_los_ultimos_detalles(tmp_path):
    for _ in range(20):
        _registro(tmp_path, max_partidas=15, max_detalles=5)

    assert len(list((tmp_path / SUBDIR_PARTIDAS).glob("*.pgn"))) == 15
    assert len(list((tmp_path / SUBDIR_DETALLE).glob("*.log"))) == 5


def test_la_rotacion_borra_las_mas_viejas_y_deja_las_nuevas(tmp_path):
    registros = [_registro(tmp_path, max_partidas=3, max_detalles=3) for _ in range(4)]

    assert not registros[0].ruta_pgn.exists(), "la más vieja se borró"
    assert all(r.ruta_pgn.exists() for r in registros[1:])


def test_partidas_del_mismo_segundo_no_se_pisan(tmp_path):
    primero = _registro(tmp_path, id_partida="20260830-201455")
    segundo = _registro(tmp_path, id_partida="20260830-201455")

    assert primero.ruta_pgn != segundo.ruta_pgn
    assert primero.ruta_log.exists() and segundo.ruta_log.exists()


def test_cerrar_dos_veces_no_duplica_nada(tmp_path, tiempo):
    partida, registro = _partida_con_registro(tmp_path, tiempo)
    _jugar(partida, "e4")

    partida.finalizar()
    partida.finalizar()

    contenido = registro.ruta_log.read_text(encoding="utf-8")
    assert contenido.count("partida finalizada") == 1
