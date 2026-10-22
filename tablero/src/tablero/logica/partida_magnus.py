"""Partida contra Magnus (Stockfish) en el tablero físico, sin límite de tiempo.

Compone `PartidaFisica` (sensores + botón + regla de las dos condiciones) y agrega la
jugada de la máquina, que el jugador tiene que hacer a mano en el tablero. **No importa
`motor/`**: `io/juego.py` corre el motor en otro hilo con `board_para_motor()` y le pasa la
respuesta a `recibir_jugada_motor()`, así esto se testea sin el binario
(`tests/test_partida_magnus.py`) y los LEDs no se congelan mientras Magnus piensa.

La jugada de Magnus usa la misma regla que una tipeada en la simulación: se aplica con
`Partida.intentar_jugada`, queda `esperando_boton == color_magnus`, y el botón que aprieta
el jugador después de moverla es `Partida.pulsar_boton(color_magnus)`, "en nombre de
Magnus". Así el registro y la regla no cambian.

Las fases no se guardan aparte: se deducen del estado de `Partida` (ver `fase`). Diseño
completo en `software-docs/vs-magnus.md`.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import chess

from tablero.logica.eventos import (
    Lectura,
    Marca,
    Ocupacion,
    TipoLectura,
    casillas_tocadas,
    ocupacion_tras,
)
from tablero.logica.notacion import GENERO_PIEZA, describir_pieza
from tablero.logica.partida import MOTIVO_ABANDONO, Partida, ResultadoJugada
from tablero.logica.partida_fisica import PartidaFisica, describir_diferencias
from tablero.logica.reloj import formatear_duracion

if TYPE_CHECKING:  # pragma: no cover - solo para tipos
    from tablero.logica.registro import RegistroPartida


class Fase(enum.Enum):
    """En qué está la partida contra Magnus."""

    TURNO_HUMANO = enum.auto()  # el jugador arma su jugada y la confirma con un botón
    MAGNUS_PENSANDO = enum.auto()  # hay que pedirle la jugada al motor
    MOVER_MAGNUS = enum.auto()  # el jugador tiene que hacer la jugada de Magnus en el tablero
    TERMINADA = enum.auto()


_TEXTO_MOVER = "Movelo y apretá un botón"


def describir_jugada_magnus(board: chess.Board, movimiento: chess.Move) -> str:
    """Qué hay que hacer en el tablero para la jugada de Magnus (con `board` de antes).

    "Magnus: caballo g8→f6", "Magnus enroca corto: rey e8→g8 y torre h8→f8",
    "Magnus: peón a2→b1, captura el caballo y poné una dama". La pieza de una promoción
    se aclara siempre, porque Magnus puede subpromover y los sensores no ven cuál se pone.
    """
    origen, destino = movimiento.from_square, movimiento.to_square
    if board.is_castling(movimiento):
        corto = board.is_kingside_castling(movimiento)
        fila = chess.square_rank(origen)
        torre_origen = chess.square(7 if corto else 0, fila)
        torre_destino = chess.square(5 if corto else 3, fila)
        return (
            f"Magnus enroca {'corto' if corto else 'largo'}: "
            f"rey {chess.square_name(origen)}→{chess.square_name(destino)} y "
            f"torre {chess.square_name(torre_origen)}→{chess.square_name(torre_destino)}"
        )

    pieza = board.piece_at(origen)
    assert pieza is not None  # la jugada es legal: hay una pieza en el origen
    texto = (
        f"Magnus: {describir_pieza(pieza.piece_type, con_articulo=False)} "
        f"{chess.square_name(origen)}→{chess.square_name(destino)}"
    )
    extras = []
    if board.is_en_passant(movimiento):
        capturado = chess.square(chess.square_file(destino), chess.square_rank(origen))
        extras.append(f"captura al paso el peón de {chess.square_name(capturado)}")
    elif (capturada := board.piece_at(destino)) is not None:
        extras.append(f"captura {describir_pieza(capturada.piece_type)}")
    if movimiento.promotion is not None:
        articulo = "una" if GENERO_PIEZA[movimiento.promotion] == "f" else "un"
        extras.append(f"poné {articulo} {describir_pieza(movimiento.promotion, con_articulo=False)}")
    return f"{texto}, {' y '.join(extras)}" if extras else texto


def mensaje_final_magnus(resultado: str, color_humano: chess.Color, duracion: float) -> str | None:
    """Mensaje del final según el resultado PGN; `None` si la partida no terminó ("*")."""
    tiempo = formatear_duracion(duracion)
    if resultado == "1/2-1/2":
        return f"Tablas con Magnus en {tiempo}"
    ganador = {"1-0": chess.WHITE, "0-1": chess.BLACK}.get(resultado)
    if ganador is None:
        return None
    if ganador == color_humano:
        return f"¡Derrotaste a Magnus en {tiempo}!"
    return f"Aguantaste {tiempo} contra Magnus"


# Lo que `chess.Board.status()` marca pero no le molesta a Stockfish: `board.fen()` ya
# descarta los enroques y el al paso imposibles antes de mandárselos.
_STATUS_INOFENSIVOS = chess.STATUS_BAD_CASTLING_RIGHTS | chess.STATUS_INVALID_EP_SQUARE


def validar_posicion_magnus(board: chess.Board) -> None:
    """`ValueError` si Stockfish no puede jugar desde `board`.

    El PvP acepta posiciones sin reyes (sirven para probar con pocos imanes), pero
    Stockfish necesita exactamente un rey de cada color y una posición legal.
    """
    estado = board.status() & ~_STATUS_INOFENSIVOS
    reyes = chess.STATUS_NO_WHITE_KING | chess.STATUS_NO_BLACK_KING | chess.STATUS_TOO_MANY_KINGS
    if estado & reyes:
        raise ValueError("contra Magnus tiene que haber exactamente un rey de cada color")
    if estado:
        raise ValueError("la posición no es legal (por ejemplo, el bando que no mueve está en jaque)")


def nombres_pgn(color_humano: chess.Color, nombre_nivel: str) -> tuple[str, str]:
    """`(White, Black)` para el PGN: "Jugador" y "Magnus (fácil)" según tu color."""
    magnus = f"Magnus ({nombre_nivel})"
    return ("Jugador", magnus) if color_humano == chess.WHITE else (magnus, "Jugador")


@dataclass(frozen=True)
class ResultadoPulsacion:
    """Respuesta a `PartidaVsMagnus.pulsar_boton`.

    `fase` es la fase en la que se apretó. `jugada` es la que se confirmó (la tuya o la de
    Magnus), o `None`; `motivo` explica por qué no se confirmó nada.
    """

    fase: Fase
    confirmado: bool
    motivo: str = ""
    jugada: ResultadoJugada | None = None


class PartidaVsMagnus:
    """Una partida del jugador contra Magnus en el tablero físico, sin límite de tiempo."""

    def __init__(
        self,
        *,
        color_humano: chess.Color,
        fen: str | None = None,
        registro: RegistroPartida | None = None,
        fuente_tiempo: Callable[[], float] = time.monotonic,
    ) -> None:
        if fen is not None:
            validar_posicion_magnus(chess.Board(fen))
        self._fisica = PartidaFisica(
            segundos_por_jugador=None, fen=fen, registro=registro, fuente_tiempo=fuente_tiempo
        )
        self._humano = color_humano
        # La jugada de Magnus que falta hacer en el tablero (o la que terminó la partida),
        # con la posición de antes, para las marcas y el texto.
        self._jugada_magnus: ResultadoJugada | None = None
        self._antes_magnus: chess.Board | None = None
        # Si Magnus captura, la casilla de la pieza capturada mientras no se la vio vacía: con
        # la pieza de Magnus en la mano, la ocupación ya es la de la jugada hecha (la casilla
        # sigue ocupada, por la pieza capturada), así que no alcanza con mirar la lectura.
        self._capturada_por_sacar: chess.Square | None = None

    # -- Lecturas -----------------------------------------------------------------

    @property
    def partida(self) -> Partida:
        return self._fisica.partida

    @property
    def board(self) -> chess.Board:
        return self._fisica.board

    @property
    def lectura(self) -> Lectura:
        """Última interpretación de la posición física."""
        return self._fisica.lectura

    @property
    def color_humano(self) -> chess.Color:
        return self._humano

    @property
    def color_magnus(self) -> chess.Color:
        return not self._humano

    @property
    def terminada(self) -> bool:
        return self.partida.terminada

    @property
    def fase(self) -> Fase:
        partida = self.partida
        if partida.terminada:
            return Fase.TERMINADA
        if partida.esperando_boton == self.color_magnus:
            return Fase.MOVER_MAGNUS
        if partida.turno == self._humano:
            return Fase.TURNO_HUMANO
        return Fase.MAGNUS_PENSANDO

    @property
    def duracion(self) -> float:
        """Segundos que lleva la partida (se congela al terminar)."""
        return self.partida.reloj.duracion

    def board_para_motor(self) -> chess.Board:
        """Copia del tablero, para pasársela al motor desde otro hilo."""
        return self.board.copy()

    def describir(self) -> str:
        """La última lectura en castellano, como en PvP (ver `PartidaFisica.describir`)."""
        return self._fisica.describir()

    def _mostrar_jugada_final(self) -> bool:
        """La partida terminó con la jugada de Magnus: sigue a la vista para ver el mate."""
        return self._jugada_magnus is not None and self.partida.estado.terminada()

    def marcas(self) -> dict[chess.Square, Marca]:
        """Qué mostrar en cada casilla según la fase (ver `software-docs/vs-magnus.md`)."""
        fase = self.fase
        if fase is Fase.TURNO_HUMANO:
            return self._fisica.marcas()
        if fase is Fase.MAGNUS_PENSANDO:
            return self._diferencias(self.lectura, frozenset())
        if fase is Fase.MOVER_MAGNUS or self._mostrar_jugada_final():
            return self._marcas_magnus()
        return {}

    def _magnus(self) -> tuple[chess.Board, chess.Move]:
        """La posición de antes de la jugada de Magnus y la jugada (solo si hay una)."""
        assert self._antes_magnus is not None and self._jugada_magnus is not None
        movimiento = self._jugada_magnus.movimiento
        assert movimiento is not None  # se guarda solo una jugada aceptada
        return self._antes_magnus, movimiento

    def _magnus_hecha(self) -> bool:
        """La posición física es la de después de la jugada de Magnus, captura incluida."""
        return self.lectura.tipo is TipoLectura.REPOSO and self._capturada_por_sacar is None

    def _marcas_magnus(self) -> dict[chess.Square, Marca]:
        antes, movimiento = self._magnus()
        todas, _ = casillas_tocadas(antes, movimiento)
        lectura = self.lectura
        if self._magnus_hecha():
            return dict.fromkeys(todas, Marca.JUGADA)
        quedan = ocupacion_tras(antes, movimiento)
        resultado = {
            sq: Marca.MAGNUS_DESTINO if sq in quedan else Marca.MAGNUS_ORIGEN for sq in todas
        }
        resultado.update(self._diferencias(lectura, todas))
        return resultado

    @staticmethod
    def _diferencias(lectura: Lectura, salvo: Ocupacion) -> dict[chess.Square, Marca]:
        resultado = dict.fromkeys(lectura.faltan - salvo, Marca.FALTA)
        resultado.update(dict.fromkeys(lectura.sobran - salvo, Marca.SOBRA))
        return resultado

    def texto_estado(self) -> str:
        """Lo que va en el recuadro de la pantalla (una o dos líneas)."""
        fase = self.fase
        if fase is Fase.TURNO_HUMANO:
            return "Tu turno"
        if fase is Fase.MAGNUS_PENSANDO:
            return "Magnus está pensando…"
        if fase is Fase.MOVER_MAGNUS:
            return f"{self._describir_magnus()}\n{_TEXTO_MOVER}"
        lineas = [self._describir_magnus()] if self._mostrar_jugada_final() else []
        lineas.append(self.mensaje_final() or "Partida abandonada")
        return "\n".join(lineas)

    def _describir_magnus(self) -> str:
        return describir_jugada_magnus(*self._magnus())

    def mensaje_final(self) -> str | None:
        """"¡Derrotaste a Magnus en MM:SS!" y compañía; `None` si sigue o se abandonó."""
        if not self.terminada:
            return None
        return mensaje_final_magnus(self.partida.resultado(), self._humano, self.duracion)

    # -- Entradas -----------------------------------------------------------------

    def procesar_ocupacion(self, ocupacion: Ocupacion) -> Lectura:
        """Interpreta una lectura de los sensores (ver `PartidaFisica.procesar_ocupacion`)."""
        if self._capturada_por_sacar not in ocupacion:
            self._capturada_por_sacar = None
        return self._fisica.procesar_ocupacion(ocupacion)

    def pulsar_boton(self) -> ResultadoPulsacion:
        """Cualquier botón del reloj: confirma tu jugada o la de Magnus, según la fase."""
        fase = self.fase
        if fase is Fase.TURNO_HUMANO:
            confirmacion = self._fisica.pulsar_boton(self._humano)
            jugada = confirmacion.jugada
            if jugada is not None and jugada.aceptado:
                return ResultadoPulsacion(fase, True, jugada=jugada)
            return ResultadoPulsacion(fase, False, confirmacion.motivo or confirmacion.boton.motivo)
        if fase is Fase.MOVER_MAGNUS:
            return self._confirmar_magnus()
        if fase is Fase.MAGNUS_PENSANDO:
            return ResultadoPulsacion(fase, False, "Magnus está pensando")
        return ResultadoPulsacion(fase, False, "la partida ya terminó")

    def _confirmar_magnus(self) -> ResultadoPulsacion:
        lectura = self.lectura
        if lectura.tipo is TipoLectura.REPOSO and self._capturada_por_sacar is not None:
            nombre = chess.square_name(self._capturada_por_sacar)
            motivo = (
                f"la jugada de Magnus no está terminada: sacá la pieza de {nombre} y apoyá ahí la de "
                "Magnus (si ya lo hiciste, levantala y volvé a apoyarla)"
            )
            return ResultadoPulsacion(Fase.MOVER_MAGNUS, False, motivo)
        if lectura.tipo is TipoLectura.REPOSO:
            self.partida.pulsar_boton(self.color_magnus)
            jugada, self._jugada_magnus, self._antes_magnus = self._jugada_magnus, None, None
            return ResultadoPulsacion(Fase.MOVER_MAGNUS, True, jugada=jugada)
        if lectura.tipo in (TipoLectura.JUGADA, TipoLectura.AMBIGUA):
            # La de Magnus ya está hecha y encima hay una jugada tuya armada.
            motivo = "primero hay que confirmar la jugada de Magnus: deshacé la tuya y apretá un botón"
        else:
            motivo = "la jugada de Magnus no está terminada: " + describir_diferencias(
                lectura.faltan, lectura.sobran
            )
        return ResultadoPulsacion(Fase.MOVER_MAGNUS, False, motivo)

    def recibir_jugada_motor(self, movimiento: chess.Move) -> ResultadoJugada:
        """Aplica la jugada de Magnus; falta que el jugador la haga y apriete un botón.

        `ValueError` si no es la fase `MAGNUS_PENSANDO` o la jugada es ilegal: sería un bug
        de quien llama, no algo que pueda pasar en el tablero.
        """
        fase = self.fase
        if fase is not Fase.MAGNUS_PENSANDO:
            raise ValueError(f"no se esperaba una jugada de Magnus (fase {fase.name})")
        if not self.board.is_legal(movimiento):
            raise ValueError(f"jugada ilegal de Magnus: {movimiento.uci()}")
        antes = self.board.copy(stack=False)
        resultado = self.partida.intentar_jugada(movimiento)
        self._jugada_magnus, self._antes_magnus = resultado, antes
        # Al paso no hace falta: deja una ocupación propia (la casilla de destino está vacía).
        self._capturada_por_sacar = movimiento.to_square if antes.piece_at(movimiento.to_square) else None
        # `LectorMatriz.leer()` solo devuelve algo cuando la matriz cambia: sin esto, la
        # última lectura seguiría siendo el reposo de antes de la jugada, y un botón
        # apretado sin tocar nada la confirmaría.
        self._fisica.procesar_ocupacion(self.lectura.ocupacion)
        return resultado

    # -- Tiempo y fin -------------------------------------------------------------

    def actualizar_tiempo(self) -> None:
        """Hace correr el cronómetro (sin límite, nunca se agota)."""
        self._fisica.actualizar_tiempo()

    def rendirse(self) -> None:
        """El jugador abandona: gana Magnus (ver `Partida.rendirse`)."""
        self.partida.rendirse(self._humano)

    def finalizar(self, motivo: str = MOTIVO_ABANDONO) -> None:
        """Cierra la partida y su registro (ver `Partida.finalizar`)."""
        self._fisica.finalizar(motivo)
