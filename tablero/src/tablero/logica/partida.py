"""Árbitro de una partida: tablero + reloj + la regla de las dos condiciones.

Compone `EstadoTablero` (reglas de ajedrez), `RelojAjedrez` (tiempo) y, opcionalmente,
`RegistroPartida` (PGN + log detallado), y agrega la regla que define el turno en el
tablero físico:

    el turno pasa al otro jugador SOLO si se cumplen las dos condiciones
    1. el jugador correcto hizo un movimiento legal, y
    2. presionó su botón del reloj DESPUÉS de hacerlo.

Mientras falte la segunda, ningún movimiento se acepta (ni del rival ni un segundo del
mismo jugador) y el tiempo le sigue corriendo a quien movió — igual que un reloj físico
si te olvidás de apretarlo.

No depende de hardware: la simulación por terminal (`tablero/simulacion.py`) y, a
futuro, el tablero real (`io/sensores.py` → `logica/eventos.py`) llaman a los mismos
métodos, así que la regla y el registro se comportan idéntico en los dos casos.

## Por qué el board cambia de turno antes que el reloj

`intentar_movimiento` aplica el movimiento al `chess.Board` en el acto (igual que hace
`logica/eventos.py` cuando lo detecta por sensores), porque el board es lo que valida la
posición y necesita estar sincronizado con las piezas físicas. El "turno de la partida"
que percibe el jugador es el del **reloj**, que solo avanza con el botón. Por eso
`board.turn` y `reloj.turno` quedan desfasados entre el movimiento y la pulsación: ese
desfase *es* la condición 2 pendiente (`esperando_boton`).
"""

from __future__ import annotations

import enum
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import chess

from tablero.logica.estado_tablero import EstadoTablero, MovimientoIlegalError
from tablero.logica.notacion import (
    NOMBRES_COLOR,
    Idioma,
    NotacionInvalidaError,
    describir_pieza,
    ninguna_pieza,
    parsear_movimiento,
    traducir_san,
)
from tablero.logica.reloj import RelojAjedrez

if TYPE_CHECKING:  # pragma: no cover - solo para tipos; en runtime sería circular
    from tablero.logica.registro import RegistroPartida


class TipoJugada(enum.Enum):
    """Cómo respondió el tablero a un movimiento intentado."""

    ACEPTADO = enum.auto()
    BLOQUEADO_FALTA_RELOJ = enum.auto()
    BLOQUEADO_ILEGAL = enum.auto()
    BLOQUEADO_TURNO = enum.auto()
    BLOQUEADO_NOTACION = enum.auto()
    BLOQUEADO_TIEMPO = enum.auto()
    BLOQUEADO_TERMINADA = enum.auto()


class TipoBoton(enum.Enum):
    """Cómo respondió el tablero a una pulsación del botón del reloj."""

    TURNO_PASADO = enum.auto()
    IGNORADO_SIN_MOVIMIENTO = enum.auto()
    IGNORADO_COLOR = enum.auto()
    IGNORADO_TIEMPO = enum.auto()
    IGNORADO_TERMINADA = enum.auto()


@dataclass(frozen=True)
class ResultadoJugada:
    """Respuesta del tablero a `Partida.intentar_movimiento`."""

    tipo: TipoJugada
    texto: str
    turno: chess.Color
    numero_jugada: int
    motivo: str = ""
    movimiento: chess.Move | None = None
    san: str | None = None
    descripcion: str = ""

    @property
    def aceptado(self) -> bool:
        return self.tipo is TipoJugada.ACEPTADO


@dataclass(frozen=True)
class ResultadoBoton:
    """Respuesta del tablero a `Partida.pulsar_boton`."""

    tipo: TipoBoton
    color: chess.Color
    motivo: str = ""
    turno_nuevo: chess.Color | None = None

    @property
    def paso_turno(self) -> bool:
        return self.tipo is TipoBoton.TURNO_PASADO


# Destino y letra de pieza de un SAN ya traducido al inglés, para explicar por qué un
# movimiento es ilegal ("la dama no puede ir de d1 a h5") sin reimplementar el parser.
_RE_SAN = re.compile(r"^(?P<pieza>[KQRBN])?.*?(?P<destino>[a-h][1-8])(?:=[QRBN])?[+#]?$")

MOTIVO_MATE = "jaque mate"
MOTIVO_TABLAS = "tablas"
MOTIVO_TIEMPO = "tiempo"
MOTIVO_ABANDONO = "abandonada"


class Partida:
    """Una partida en curso, con la regla de las dos condiciones y registro opcional."""

    def __init__(
        self,
        *,
        segundos_por_jugador: float,
        idioma: Idioma = Idioma.ESPANOL,
        fen: str | None = None,
        registro: RegistroPartida | None = None,
        fuente_tiempo: Callable[[], float] = time.monotonic,
    ) -> None:
        self._estado = EstadoTablero(fen)
        self._reloj = RelojAjedrez(segundos_por_jugador, fuente_tiempo)
        self._idioma = idioma
        self._registro = registro
        self._pendiente_de_reloj: chess.Color | None = None
        self._motivo_fin: str | None = None
        if fen:
            # Con un FEN de arranque el reloj tiene que empezar en el color que mueve.
            while self._reloj.turno != self._estado.turno:
                self._reloj.pulsar(self._reloj.turno)

    # -- Lecturas -----------------------------------------------------------------

    @property
    def estado(self) -> EstadoTablero:
        return self._estado

    @property
    def reloj(self) -> RelojAjedrez:
        return self._reloj

    @property
    def idioma(self) -> Idioma:
        return self._idioma

    @property
    def turno(self) -> chess.Color:
        """Color al que le toca jugar según el reloj (el turno que percibe el jugador)."""
        return self._reloj.turno

    @property
    def esperando_boton(self) -> chess.Color | None:
        """Color que ya movió y todavía no pulsó su botón (condición 2 pendiente)."""
        return self._pendiente_de_reloj

    @property
    def terminada(self) -> bool:
        return self._motivo_fin is not None or self._estado.terminada() or self._reloj.tiempo_agotado

    @property
    def motivo_fin(self) -> str | None:
        """Por qué terminó la partida, o `None` si sigue en curso."""
        if self._motivo_fin is not None:
            return self._motivo_fin
        if self._reloj.tiempo_agotado:
            return MOTIVO_TIEMPO
        if self._estado.es_jaque_mate():
            return MOTIVO_MATE
        if self._estado.terminada():
            return MOTIVO_TABLAS
        return None

    def resultado(self) -> str:
        """Resultado en notación PGN: "1-0", "0-1", "1/2-1/2" o "*" si no terminó."""
        if self._reloj.tiempo_agotado:
            return "0-1" if self._reloj.perdedor == chess.WHITE else "1-0"
        return self._estado.resultado() or "*"

    # -- Tiempo -------------------------------------------------------------------

    def actualizar_tiempo(self) -> bool:
        """Descuenta el tiempo real transcurrido; `True` si recién ahora se agotó."""
        return self._notificar_si_agotado(self._reloj.actualizar())

    def avanzar_tiempo(self, segundos: float) -> bool:
        """Descuenta `segundos` de tiempo simulado; `True` si recién ahora se agotó."""
        return self._notificar_si_agotado(self._reloj.avanzar(segundos))

    def _notificar_si_agotado(self, agotado: bool) -> bool:
        if agotado and self._registro is not None:
            self._registro.anotar_tiempo_agotado(self._reloj)
        return agotado

    # -- Movimientos --------------------------------------------------------------

    def intentar_movimiento(self, texto: str) -> ResultadoJugada:
        """Procesa un movimiento tipeado y devuelve cómo respondió el tablero."""
        self.actualizar_tiempo()
        resultado = self._resolver_movimiento(texto)
        if self._registro is not None:
            self._registro.anotar_jugada(resultado, self._reloj, self._estado.board)
        return resultado

    def _resolver_movimiento(self, texto: str) -> ResultadoJugada:
        turno, numero = self.turno, self._estado.board.fullmove_number

        def bloqueado(tipo: TipoJugada, motivo: str) -> ResultadoJugada:
            return ResultadoJugada(
                tipo=tipo, texto=texto, turno=turno, numero_jugada=numero, motivo=motivo
            )

        if self._reloj.tiempo_agotado:
            perdedor = NOMBRES_COLOR[self._reloj.perdedor]
            return bloqueado(TipoJugada.BLOQUEADO_TIEMPO, f"la partida terminó: {perdedor} se quedó sin tiempo")
        if self.terminada:
            return bloqueado(TipoJugada.BLOQUEADO_TERMINADA, f"la partida ya terminó ({self.motivo_fin})")
        if self._pendiente_de_reloj is not None:
            pendiente = NOMBRES_COLOR[self._pendiente_de_reloj]
            return bloqueado(
                TipoJugada.BLOQUEADO_FALTA_RELOJ,
                f"{pendiente} todavía no presionaron su botón del reloj",
            )

        try:
            movimiento = parsear_movimiento(texto, self._estado.board, self._idioma)
        except NotacionInvalidaError as exc:
            return bloqueado(TipoJugada.BLOQUEADO_NOTACION, str(exc))
        except MovimientoIlegalError:
            if self._es_del_otro_color(texto):
                return bloqueado(
                    TipoJugada.BLOQUEADO_TURNO,
                    f"'{texto}' es un movimiento de {NOMBRES_COLOR[not turno]}, "
                    f"pero el turno es de {NOMBRES_COLOR[turno]}",
                )
            return bloqueado(TipoJugada.BLOQUEADO_ILEGAL, self._motivo_ilegal(texto))

        san = self._estado.board.san(movimiento)
        pieza = self._estado.board.piece_at(movimiento.from_square)
        descripcion = (
            f"{describir_pieza(pieza.piece_type, con_articulo=False)} "
            f"{chess.square_name(movimiento.from_square)}→{chess.square_name(movimiento.to_square)}"
        )
        self._estado.aplicar_movimiento(movimiento)
        self._pendiente_de_reloj = turno

        if self._estado.terminada():
            # Mate o tablas: no tiene sentido esperar el botón, la partida ya terminó.
            self._pendiente_de_reloj = None
            self._motivo_fin = MOTIVO_MATE if self._estado.es_jaque_mate() else MOTIVO_TABLAS

        return ResultadoJugada(
            tipo=TipoJugada.ACEPTADO,
            texto=texto,
            turno=turno,
            numero_jugada=numero,
            movimiento=movimiento,
            san=san,
            descripcion=descripcion,
        )

    def _es_del_otro_color(self, texto: str) -> bool:
        """Indica si `texto` sería legal para el color que NO tiene el turno.

        Sirve solo para dar un mensaje útil ("ese movimiento es de las negras"): se
        prueba sobre una copia con el turno invertido, así que un fallo se trata como
        "no, es simplemente ilegal".
        """
        espejo = self._estado.board.copy(stack=False)
        espejo.turn = not espejo.turn
        try:
            parsear_movimiento(texto, espejo, self._idioma)
        except (NotacionInvalidaError, MovimientoIlegalError, ValueError):
            return False
        return True

    def _motivo_ilegal(self, texto: str) -> str:
        """Explica por qué un movimiento entendido no se puede hacer en esta posición."""
        board = self._estado.board
        color = NOMBRES_COLOR[board.turn]

        if len(texto) >= 4 and re.fullmatch(r"[a-h][1-8][a-h][1-8][a-z]?", texto.lower()):
            origen = chess.parse_square(texto[:2].lower())
            destino = chess.parse_square(texto[2:4].lower())
            pieza = board.piece_at(origen)
            if pieza is None:
                return f"no hay ninguna pieza en {chess.square_name(origen)}"
            if pieza.color != board.turn:
                return (
                    f"en {chess.square_name(origen)} hay una pieza de "
                    f"{NOMBRES_COLOR[pieza.color]}, y el turno es de {color}"
                )
            return (
                f"{describir_pieza(pieza.piece_type)} de {chess.square_name(origen)} "
                f"no puede ir a {chess.square_name(destino)}"
            )

        coincidencia = _RE_SAN.match(traducir_san(texto, self._idioma))
        if coincidencia is None:
            return f"{color} no pueden hacer '{texto}' en esta posición"

        letra = coincidencia.group("pieza")
        tipo = chess.PIECE_SYMBOLS.index(letra.lower()) if letra else chess.PAWN
        destino = coincidencia.group("destino")
        origenes = list(board.pieces(tipo, board.turn))
        if not origenes:
            return f"{color} no tienen {ninguna_pieza(tipo)} en el tablero"
        if len(origenes) == 1:
            return (
                f"{describir_pieza(tipo)} de {chess.square_name(origenes[0])} "
                f"no puede ir a {destino}"
            )
        return f"{ninguna_pieza(tipo)} de {color} puede ir a {destino}"

    # -- Botón del reloj ----------------------------------------------------------

    def pulsar_boton(self, color: chess.Color) -> ResultadoBoton:
        """Procesa la pulsación del botón de `color` y devuelve si el turno pasó."""
        self.actualizar_tiempo()
        resultado = self._resolver_boton(color)
        if self._registro is not None:
            self._registro.anotar_boton(resultado, self._reloj)
        return resultado

    def _resolver_boton(self, color: chess.Color) -> ResultadoBoton:
        if self._reloj.tiempo_agotado:
            perdedor = NOMBRES_COLOR[self._reloj.perdedor]
            return ResultadoBoton(
                TipoBoton.IGNORADO_TIEMPO, color, f"la partida terminó: {perdedor} se quedó sin tiempo"
            )
        if self.terminada:
            return ResultadoBoton(
                TipoBoton.IGNORADO_TERMINADA, color, f"la partida ya terminó ({self.motivo_fin})"
            )
        if color != self._reloj.turno:
            return ResultadoBoton(
                TipoBoton.IGNORADO_COLOR,
                color,
                f"el botón de {NOMBRES_COLOR[color]} no hace nada: el turno es de "
                f"{NOMBRES_COLOR[self._reloj.turno]}",
            )
        if self._pendiente_de_reloj != color:
            # Condición 1 incumplida: pulsar sin haber movido no pasa el turno.
            return ResultadoBoton(
                TipoBoton.IGNORADO_SIN_MOVIMIENTO,
                color,
                f"{NOMBRES_COLOR[color]} todavía no hicieron ningún movimiento legal",
            )

        self._reloj.pulsar(color)
        self._pendiente_de_reloj = None
        return ResultadoBoton(TipoBoton.TURNO_PASADO, color, turno_nuevo=self._reloj.turno)

    # -- Fin de partida -----------------------------------------------------------

    def finalizar(self, motivo: str = MOTIVO_ABANDONO) -> None:
        """Cierra la partida y su registro. Idempotente: repetirlo no cambia nada."""
        if self._motivo_fin is None:
            self._motivo_fin = self.motivo_fin or motivo
        if self._registro is not None:
            self._registro.cerrar(self.resultado(), self._motivo_fin, self._estado.board)
