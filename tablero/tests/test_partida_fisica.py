"""Tests de PartidaFisica (tablero/src/tablero/logica/partida_fisica.py).

No requieren hardware: las lecturas de la matriz se simulan con una "mano" que levanta y
apoya piezas, y el reloj usa la fixture `tiempo` (`RelojFalso`, en `conftest.py`). El foco
está en que la jugada recién cuenta al apretar el botón del reloj.
"""

import chess

from tablero.logica.eventos import TipoLectura, casillas_ocupadas
from tablero.logica.partida import TipoBoton
from tablero.logica.partida_fisica import PartidaFisica
from tablero.logica.registro import SUBDIR_DETALLE, SUBDIR_PARTIDAS, RegistroPartida


class _Mano:
    """Las piezas físicas: cada cambio se lo pasa a la partida como una lectura nueva."""

    def __init__(self, partida: PartidaFisica) -> None:
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


def _partida(tiempo, **kwargs) -> tuple[PartidaFisica, _Mano]:
    kwargs.setdefault("segundos_por_jugador", 300)
    partida = PartidaFisica(fuente_tiempo=tiempo, **kwargs)
    return partida, _Mano(partida)


def _jugar(partida: PartidaFisica, mano: _Mano, origen: str, destino: str):
    mano.mover(origen, destino)
    return partida.pulsar_boton(partida.partida.turno)


def test_jugada_mas_boton_pasa_el_turno(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "e4")

    resultado = partida.pulsar_boton(chess.WHITE)

    assert resultado.paso_turno
    assert resultado.jugada is not None
    assert resultado.jugada.san == "e4"
    assert partida.partida.turno == chess.BLACK
    assert partida.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert partida.lectura.tipo is TipoLectura.REPOSO, "la posición física es el nuevo reposo"


def test_la_jugada_no_se_aplica_hasta_el_boton(tiempo):
    partida, mano = _partida(tiempo)

    lectura = mano.mover("e2", "e4")

    assert lectura.tipo is TipoLectura.JUGADA
    assert partida.board.piece_at(chess.E2) is not None
    assert partida.partida.esperando_boton is None
    assert "peón e2→e4 (e4), falta apretar el reloj" == partida.describir()


def test_boton_sin_mover_no_hace_nada(tiempo):
    partida, _ = _partida(tiempo)

    resultado = partida.pulsar_boton(chess.WHITE)

    assert resultado.boton.tipo is TipoBoton.IGNORADO_SIN_MOVIMIENTO
    assert resultado.jugada is None
    assert resultado.motivo == "no se movió ninguna pieza"
    assert partida.partida.turno == chess.WHITE


def test_boton_con_la_pieza_en_una_casilla_ilegal_dice_que_corregir(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "d4")

    resultado = partida.pulsar_boton(chess.WHITE)

    assert not resultado.paso_turno
    assert resultado.motivo == "no es una jugada legal: falta pieza en e2; sobra pieza en d4"
    assert partida.board.piece_at(chess.E2) is not None

    mano.mover("d4", "e3")
    assert partida.pulsar_boton(chess.WHITE).paso_turno


def test_boton_con_la_pieza_que_puede_capturar_en_la_mano_no_captura(tiempo):
    # 1.e4 d5: con el peón de e4 levantado, d5 sigue ocupada como después de exd5.
    partida, mano = _partida(tiempo, fen="rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
    mano.levantar("e4")

    resultado = partida.pulsar_boton(chess.WHITE)

    assert not resultado.paso_turno
    assert resultado.motivo == (
        "falta pieza en e4 (si ya capturaste en d5, levantá y volvé a apoyar la pieza que capturó)"
    )
    mano.levantar("d5")
    mano.apoyar("d5")
    assert partida.pulsar_boton(chess.WHITE).jugada.san == "exd5"


def test_boton_del_rival_no_confirma_la_jugada(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "e4")

    resultado = partida.pulsar_boton(chess.BLACK)

    assert resultado.boton.tipo is TipoBoton.IGNORADO_COLOR
    assert resultado.jugada is None
    assert partida.board.piece_at(chess.E2) is not None
    assert partida.pulsar_boton(chess.WHITE).paso_turno


def test_si_el_rival_toca_una_pieza_antes_del_boton_hay_que_reponerla(tiempo):
    partida, mano = _partida(tiempo)
    mano.mover("e2", "e4")
    mano.levantar("e7")  # las negras se apuran

    rechazado = partida.pulsar_boton(chess.WHITE)
    assert not rechazado.paso_turno
    assert "falta pieza en e2, e7" in rechazado.motivo

    mano.apoyar("e7")
    assert partida.pulsar_boton(chess.WHITE).paso_turno


def test_el_tiempo_corre_mientras_se_acomodan_las_piezas(tiempo):
    partida, mano = _partida(tiempo, segundos_por_jugador=60)
    mano.mover("e2", "e4")
    tiempo.avanzar(10)

    partida.pulsar_boton(chess.WHITE)

    assert partida.partida.reloj.restante(chess.WHITE) == 50


def test_jaque_mate_termina_la_partida(tiempo):
    partida, mano = _partida(tiempo)
    for origen, destino in [
        ("e2", "e4"), ("e7", "e5"), ("f1", "c4"), ("b8", "c6"), ("d1", "h5"), ("g8", "f6")
    ]:
        assert _jugar(partida, mano, origen, destino).paso_turno

    mano.mover("h5", "f7")
    resultado = partida.pulsar_boton(chess.WHITE)

    assert resultado.jugada is not None
    assert resultado.jugada.aceptado
    assert resultado.boton.tipo is TipoBoton.IGNORADO_TERMINADA
    assert partida.terminada
    assert partida.partida.motivo_fin == "jaque mate"
    assert partida.partida.resultado() == "1-0"


def test_partida_corta_con_captura_y_enroque_queda_registrada(tiempo, tmp_path):
    registro = RegistroPartida(tmp_path, modo="tablero", segundos_por_jugador=300)
    partida, mano = _partida(tiempo, registro=registro)

    for origen, destino in [("e2", "e4"), ("e7", "e5"), ("g1", "f3"), ("g8", "f6"), ("f1", "c4")]:
        assert _jugar(partida, mano, origen, destino).paso_turno
    captura = _jugar(partida, mano, "f6", "e4")
    assert captura.jugada is not None
    assert captura.jugada.san == "Nxe4"

    mano.mover("e1", "g1")
    mano.mover("h1", "f1")
    enroque = partida.pulsar_boton(chess.WHITE)
    assert enroque.paso_turno
    assert enroque.jugada is not None
    assert enroque.jugada.san == "O-O"
    partida.finalizar()

    assert partida.board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
    assert partida.board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
    pgn = next((tmp_path / SUBDIR_PARTIDAS).iterdir()).read_text(encoding="utf-8")
    assert "4. O-O" in pgn
    detalle = next((tmp_path / SUBDIR_DETALLE).iterdir()).read_text(encoding="utf-8")
    assert "intenta 'e1g1' → ACEPTADO O-O" in detalle


# -- Tablas ---------------------------------------------------------------------------


def test_tablas_aceptadas_terminan_la_partida(tiempo, tmp_path):
    registro = RegistroPartida(tmp_path, modo="tablero", segundos_por_jugador=300, max_partidas=5, max_detalles=5)
    partida, _ = _partida(tiempo, registro=registro)

    assert partida.ofrecer_tablas(chess.WHITE)
    assert partida.oferta_tablas == chess.WHITE
    assert not partida.ofrecer_tablas(chess.BLACK), "una sola oferta a la vez"
    partida.responder_tablas(acepta=True)

    assert partida.terminada
    assert partida.oferta_tablas is None
    assert partida.partida.resultado() == "1/2-1/2"
    assert partida.partida.motivo_fin == "tablas por acuerdo"
    log = registro.ruta_log.read_text(encoding="utf-8")
    assert "blancas ofrece tablas" in log
    assert "negras acepta las tablas" in log
    assert '[Result "1/2-1/2"]' in registro.ruta_pgn.read_text(encoding="utf-8")


def test_tablas_rechazadas_siguen_la_partida(tiempo):
    partida, mano = _partida(tiempo)
    partida.ofrecer_tablas(chess.BLACK)

    partida.responder_tablas(acepta=False)

    assert not partida.terminada
    assert partida.oferta_tablas is None
    assert _jugar(partida, mano, "e2", "e4").paso_turno


def test_jugar_sin_contestar_rechaza_las_tablas(tiempo):
    partida, mano = _partida(tiempo)
    _jugar(partida, mano, "e2", "e4")
    # Las blancas ofrecen después de jugar; la oferta sigue mientras piensan las negras.
    partida.ofrecer_tablas(chess.WHITE)
    assert partida.oferta_tablas == chess.WHITE

    _jugar(partida, mano, "e7", "e5")

    assert partida.oferta_tablas is None
    assert not partida.terminada


def test_la_oferta_sobrevive_a_la_jugada_de_quien_ofrecio(tiempo):
    partida, mano = _partida(tiempo)
    partida.ofrecer_tablas(chess.WHITE)

    _jugar(partida, mano, "e2", "e4")

    assert partida.oferta_tablas == chess.WHITE


def test_no_se_ofrecen_tablas_con_la_partida_terminada(tiempo):
    partida, _ = _partida(tiempo)
    partida.partida.rendirse(chess.WHITE)

    assert not partida.ofrecer_tablas(chess.BLACK)
