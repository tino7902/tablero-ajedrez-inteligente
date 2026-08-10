"""Traducción de diffs de ocupación de casillas a `chess.Move`.

Los sensores físicos (reed switches, ver `hardware-docs/`) solo van a poder reportar
presencia/ausencia de pieza por casilla, no identidad — este módulo reconstruye qué
movimiento se está haciendo comparando snapshots sucesivos de ocupación contra el
estado de `EstadoTablero`. No depende de `io/sensores.py` (todavía vacío): define su
propia entrada (`Ocupacion`, un `frozenset[chess.Square]`) para mantenerse testable sin
hardware, siguiendo el boundary documentado en `CLAUDE.md`.

Flujo soportado en esta v1 (ver `software-docs/eventos.md` para el detalle completo):
se levanta una pieza, se coloca en una casilla candidata; si el movimiento resultante es
ilegal se espera a que se retome esa misma pieza (el origen lógico nunca cambia mientras
el movimiento sigue en curso) y se coloque en una casilla donde sí sea legal. Cada cambio
de estado queda logueado con número de jugada y color.

Fuera de alcance v1 (rechazado de forma explícita, no aplicado a ciegas):
- Capturas, enroque y captura al paso (`TipoEvento.MOVIMIENTO_NO_SOPORTADO`).
- Ambigüedad quando el jugador mueve más rápido que la frecuencia de escaneo de
  sensores (lift y place cayendo en el mismo snapshot).
- Resincronización/timeout si el rastreador queda con un movimiento en curso sin
  resolver.
- Posición inicial incorrecta al arrancar: se asume que la primera `Ocupacion` que se
  procesa coincide con `estado.board.occupied`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto

import chess

from tablero.logica.estado_tablero import EstadoTablero

log = logging.getLogger(__name__)

Ocupacion = frozenset[chess.Square]

_NOMBRES_COLOR = {chess.WHITE: "blancas", chess.BLACK: "negras"}
_NOMBRES_PIEZA = {
    chess.PAWN: "peón",
    chess.KNIGHT: "caballo",
    chess.BISHOP: "alfil",
    chess.ROOK: "torre",
    chess.QUEEN: "dama",
    chess.KING: "rey",
}


def casillas_ocupadas(board: chess.Board) -> Ocupacion:
    """Casillas ocupadas de `board` como `frozenset[chess.Square]`."""
    return frozenset(chess.SquareSet(board.occupied))


class TipoEvento(Enum):
    """Qué tipo de cambio de estado representa un `EventoTablero`."""

    PIEZA_LEVANTADA = auto()
    PIEZA_REPUESTA = auto()
    MOVIMIENTO_ILEGAL_RECHAZADO = auto()
    MOVIMIENTO_APLICADO = auto()
    MOVIMIENTO_NO_SOPORTADO = auto()


@dataclass(frozen=True)
class EventoTablero:
    """Un cambio de estado detectado por `RastreadorMovimientos`, ya logueado."""

    tipo: TipoEvento
    pieza: chess.Piece
    origen: chess.Square
    destino: chess.Square | None
    turno: chess.Color
    numero_jugada: int


class RastreadorMovimientos:
    """Detecta movimientos comparando snapshots de ocupación contra `EstadoTablero`.

    Se alimenta llamando a `procesar_ocupacion` con cada lectura sucesiva de sensores.
    Asume que la primera lectura coincide con la posición ya cargada en `estado`.
    """

    def __init__(self, estado: EstadoTablero) -> None:
        self._estado = estado
        self._origen: chess.Square | None = None
        self._colocacion_actual: chess.Square | None = None
        self._pieza: chess.Piece | None = None
        # Casilla que se vació de forma inesperada mientras había una pieza en curso —
        # típicamente la pieza capturada retirándose antes de que la atacante se
        # coloque en su lugar. Se resta de la ocupación esperada para que, cuando esa
        # misma casilla vuelva a ocuparse, el diff no se pierda por coincidir con lo
        # esperado (ver `_procesar_desaparicion`/`_procesar_aparicion`).
        self._extra_vacia: chess.Square | None = None

    def _ocupacion_esperada(self) -> Ocupacion:
        base = casillas_ocupadas(self._estado.board)
        if self._origen is None:
            return base
        base = base - {self._origen}
        if self._extra_vacia is not None:
            base = base - {self._extra_vacia}
        if self._colocacion_actual is not None:
            base = base | {self._colocacion_actual}
        return base

    def _en_curso(self) -> bool:
        return self._origen is not None

    def _reiniciar(self) -> None:
        self._origen = None
        self._colocacion_actual = None
        self._pieza = None
        self._extra_vacia = None

    def _describir(self, pieza: chess.Piece, casilla: chess.Square) -> str:
        return f"{_NOMBRES_PIEZA[pieza.piece_type]} de {chess.square_name(casilla)}"

    def _prefijo_log(
        self, turno: chess.Color | None = None, numero_jugada: int | None = None
    ) -> str:
        turno = self._estado.turno if turno is None else turno
        numero_jugada = (
            self._estado.board.fullmove_number if numero_jugada is None else numero_jugada
        )
        return f"Jugada {numero_jugada} ({_NOMBRES_COLOR[turno]})"

    def _evento(
        self,
        tipo: TipoEvento,
        *,
        pieza: chess.Piece,
        origen: chess.Square,
        destino: chess.Square | None,
        turno: chess.Color,
        numero_jugada: int,
    ) -> EventoTablero:
        return EventoTablero(
            tipo=tipo,
            pieza=pieza,
            origen=origen,
            destino=destino,
            turno=turno,
            numero_jugada=numero_jugada,
        )

    def procesar_ocupacion(self, ocupacion: Ocupacion) -> EventoTablero | None:
        """Procesa una lectura de sensores y devuelve el evento detectado, si hay uno.

        Devuelve `None` cuando la lectura no trae ningún cambio interpretable: una
        lectura idéntica a la anterior (no se loguea), o un diff con una forma no
        soportada (se loguea un `WARNING`, pero no se toca el estado interno).
        """
        esperada = self._ocupacion_esperada()
        aparecidas = ocupacion - esperada
        desaparecidas = esperada - ocupacion

        if not aparecidas and not desaparecidas:
            return None

        if len(aparecidas) + len(desaparecidas) != 1:
            log.warning(
                "%s: diff de ocupación inesperado (aparecen=%s, desaparecen=%s); se ignora",
                self._prefijo_log(),
                {chess.square_name(sq) for sq in aparecidas},
                {chess.square_name(sq) for sq in desaparecidas},
            )
            return None

        if desaparecidas:
            return self._procesar_desaparicion(next(iter(desaparecidas)))
        return self._procesar_aparicion(next(iter(aparecidas)))

    def _procesar_desaparicion(self, sq: chess.Square) -> EventoTablero | None:
        if not self._en_curso():
            pieza = self._estado.board.piece_at(sq)
            if pieza is None or pieza.color != self._estado.turno:
                log.warning(
                    "%s: se detectó una pieza levantada en %s pero no corresponde a "
                    "quien tiene el turno; se ignora",
                    self._prefijo_log(),
                    chess.square_name(sq),
                )
                return None

            turno, numero_jugada = self._estado.turno, self._estado.board.fullmove_number
            self._origen = sq
            self._pieza = pieza
            log.info("%s: se levanta %s", self._prefijo_log(), self._describir(pieza, sq))
            return self._evento(
                TipoEvento.PIEZA_LEVANTADA,
                pieza=pieza,
                origen=sq,
                destino=None,
                turno=turno,
                numero_jugada=numero_jugada,
            )

        if sq == self._colocacion_actual:
            self._colocacion_actual = None
            log.info("%s: se retoma la pieza en %s", self._prefijo_log(), chess.square_name(sq))
            return self._evento(
                TipoEvento.PIEZA_LEVANTADA,
                pieza=self._pieza,
                origen=self._origen,
                destino=None,
                turno=self._estado.turno,
                numero_jugada=self._estado.board.fullmove_number,
            )

        if self._colocacion_actual is None and self._extra_vacia is None:
            # Una segunda casilla se vació sin haberse repuesto la primera: típico de
            # una captura física (se retira la pieza capturada antes de colocar la
            # atacante). Se recuerda para no perder el rastro cuando se vuelva a
            # ocupar — ver `_ocupacion_esperada`. El movimiento sigue sin soportarse
            # (se rechazará explícitamente en `_procesar_aparicion` si se completa).
            self._extra_vacia = sq
            log.warning(
                "%s: se vació %s además de %s (¿captura en curso?); fuera de alcance v1",
                self._prefijo_log(),
                chess.square_name(sq),
                chess.square_name(self._origen),
            )
            return None

        log.warning(
            "%s: se levantó una pieza en %s mientras había otra en curso desde %s; se ignora",
            self._prefijo_log(),
            chess.square_name(sq),
            chess.square_name(self._origen),
        )
        return None

    def _procesar_aparicion(self, sq: chess.Square) -> EventoTablero | None:
        if not self._en_curso() or self._colocacion_actual is not None:
            log.warning(
                "%s: apareció una pieza en %s sin una pieza en el aire que la explique; se ignora",
                self._prefijo_log(),
                chess.square_name(sq),
            )
            return None

        origen = self._origen
        pieza = self._pieza

        if sq == origen:
            log.info(
                "%s: se repone %s en su casilla original, se cancela el movimiento",
                self._prefijo_log(),
                self._describir(pieza, origen),
            )
            self._reiniciar()
            return self._evento(
                TipoEvento.PIEZA_REPUESTA,
                pieza=pieza,
                origen=origen,
                destino=None,
                turno=self._estado.turno,
                numero_jugada=self._estado.board.fullmove_number,
            )

        candidatos = [
            m
            for m in self._estado.board.legal_moves
            if m.from_square == origen and m.to_square == sq
        ]

        if not candidatos:
            self._colocacion_actual = sq
            log.warning(
                "%s: %s→%s es ILEGAL, se rechaza y se espera corrección",
                self._prefijo_log(),
                chess.square_name(origen),
                chess.square_name(sq),
            )
            return self._evento(
                TipoEvento.MOVIMIENTO_ILEGAL_RECHAZADO,
                pieza=pieza,
                origen=origen,
                destino=sq,
                turno=self._estado.turno,
                numero_jugada=self._estado.board.fullmove_number,
            )

        movimiento = candidatos[0]
        if len(candidatos) > 1:
            movimiento = next(m for m in candidatos if m.promotion == chess.QUEEN)

        board = self._estado.board
        if board.is_capture(movimiento) or board.is_castling(movimiento):
            self._colocacion_actual = sq
            log.warning(
                "%s: %s→%s parece captura/enroque/al paso, fuera de alcance v1; se rechaza",
                self._prefijo_log(),
                chess.square_name(origen),
                chess.square_name(sq),
            )
            return self._evento(
                TipoEvento.MOVIMIENTO_NO_SOPORTADO,
                pieza=pieza,
                origen=origen,
                destino=sq,
                turno=self._estado.turno,
                numero_jugada=self._estado.board.fullmove_number,
            )

        turno, numero_jugada = self._estado.turno, self._estado.board.fullmove_number
        self._estado.aplicar_movimiento(movimiento)
        log.info(
            "%s: %s→%s aplicado. Turno pasa a %s.",
            self._prefijo_log(turno, numero_jugada),
            chess.square_name(origen),
            chess.square_name(sq),
            _NOMBRES_COLOR[self._estado.turno],
        )
        self._reiniciar()
        return self._evento(
            TipoEvento.MOVIMIENTO_APLICADO,
            pieza=pieza,
            origen=origen,
            destino=sq,
            turno=turno,
            numero_jugada=numero_jugada,
        )
