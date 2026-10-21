"""Partida jugada en el tablero físico: lecturas de los sensores + botón del reloj.

Compone `Partida` (reglas, reloj y registro) con `RastreadorMovimientos`
(`logica/eventos.py`) sobre el mismo tablero lógico. La jugada recién cuenta cuando el
jugador aprieta su botón del reloj: hasta entonces puede acomodar las piezas como quiera
(el enroque y las capturas pasan por posiciones intermedias). Al apretar:

- si la posición física es una jugada legal de quien tiene el turno, se aplica
  (`Partida.intentar_jugada`) y se pasa el turno (`Partida.pulsar_boton`), las dos cosas
  juntas, así que la regla de las dos condiciones se cumple siempre en orden;
- si no, el botón no hace nada y el resultado explica qué corregir.

No depende de hardware: `io/juego.py` le pasa las lecturas de la matriz y los botones, y
los tests (`tests/test_partida_fisica.py`) le pasan ocupaciones armadas a mano.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import chess

from tablero.logica.eventos import (
    Lectura,
    Marca,
    Ocupacion,
    RastreadorMovimientos,
    TipoLectura,
    casillas_ocupadas,
    marcas,
)
from tablero.logica.notacion import describir_pieza
from tablero.logica.partida import (
    MOTIVO_ABANDONO,
    Partida,
    ResultadoBoton,
    ResultadoJugada,
    TipoBoton,
)

if TYPE_CHECKING:  # pragma: no cover - solo para tipos
    from tablero.logica.registro import RegistroPartida


def _lista(casillas: Ocupacion) -> str:
    return ", ".join(chess.square_name(sq) for sq in sorted(casillas))


def describir_jugada(board: chess.Board, movimiento: chess.Move) -> str:
    """"caballo g1→f3 (Nf3)", con la posición de antes de jugarla."""
    pieza = board.piece_at(movimiento.from_square)
    return (
        f"{describir_pieza(pieza.piece_type, con_articulo=False)} "
        f"{chess.square_name(movimiento.from_square)}→{chess.square_name(movimiento.to_square)} "
        f"({board.san(movimiento)})"
    )


def describir_diferencias(faltan: Ocupacion, sobran: Ocupacion) -> str:
    """"falta pieza en e2; sobra pieza en d4", con las casillas que no coinciden."""
    partes = []
    if faltan:
        partes.append(f"falta pieza en {_lista(faltan)}")
    if sobran:
        partes.append(f"sobra pieza en {_lista(sobran)}")
    return "; ".join(partes)


def describir_lectura(lectura: Lectura, board: chess.Board) -> str:
    """Qué ve el tablero en la posición física, en castellano y listo para mostrar."""
    if lectura.tipo is TipoLectura.REPOSO:
        return "no se movió ninguna pieza"
    if lectura.tipo is TipoLectura.JUGADA:
        return f"{describir_jugada(board, lectura.movimiento)}, falta apretar el reloj"
    if lectura.tipo is TipoLectura.AMBIGUA:
        destinos = " o ".join(chess.square_name(m.to_square) for m in lectura.candidatos)
        return (
            f"no se sabe dónde se capturó ({destinos}): levantá y volvé a apoyar la pieza "
            "que capturó"
        )
    return "no es una jugada legal: " + describir_diferencias(lectura.faltan, lectura.sobran)


@dataclass(frozen=True)
class ResultadoConfirmacion:
    """Respuesta del tablero a `PartidaFisica.pulsar_boton`.

    `jugada` es `None` cuando no se intentó ninguna (no había una jugada legal armada, o el
    botón no era el de quien tiene el turno). `motivo` explica, con la posición física, por
    qué no se confirmó nada; vacío si el turno pasó o si el motivo ya está en `boton`.
    """

    boton: ResultadoBoton
    lectura: Lectura
    jugada: ResultadoJugada | None = None
    motivo: str = ""

    @property
    def paso_turno(self) -> bool:
        return self.boton.paso_turno


class PartidaFisica:
    """Una partida en el tablero físico: la posición la dan los sensores, no el teclado."""

    def __init__(
        self,
        *,
        segundos_por_jugador: float | None,
        fen: str | None = None,
        registro: RegistroPartida | None = None,
        fuente_tiempo: Callable[[], float] = time.monotonic,
    ) -> None:
        self._partida = Partida(
            segundos_por_jugador=segundos_por_jugador,
            fen=fen,
            registro=registro,
            fuente_tiempo=fuente_tiempo,
        )
        self._rastreador = RastreadorMovimientos(self._partida.estado)
        # Se asume que la partida arranca con las piezas bien puestas (`io/juego.py` lo
        # espera antes de crearla); la primera lectura lo corrige si no.
        self._lectura = Lectura(TipoLectura.REPOSO, casillas_ocupadas(self.board))

    # -- Lecturas -----------------------------------------------------------------

    @property
    def partida(self) -> Partida:
        return self._partida

    @property
    def board(self) -> chess.Board:
        return self._partida.estado.board

    @property
    def lectura(self) -> Lectura:
        """Última interpretación de la posición física."""
        return self._lectura

    @property
    def terminada(self) -> bool:
        return self._partida.terminada

    def marcas(self) -> dict[chess.Square, Marca]:
        """Qué mostrar en cada casilla para la última lectura (ver `eventos.marcas`)."""
        return marcas(self._lectura, self.board)

    def describir(self) -> str:
        """La última lectura en castellano (ver `describir_lectura`)."""
        return describir_lectura(self._lectura, self.board)

    # -- Entradas -----------------------------------------------------------------

    def procesar_ocupacion(self, ocupacion: Ocupacion) -> Lectura:
        """Interpreta una lectura de los sensores; la jugada no se aplica hasta el botón."""
        self._lectura = self._rastreador.procesar_ocupacion(ocupacion)
        return self._lectura

    def pulsar_boton(self, color: chess.Color) -> ResultadoConfirmacion:
        """Botón del reloj de `color`: confirma la jugada armada, si hay una legal."""
        partida = self._partida
        lectura = self._lectura
        jugada = None
        if (
            color == partida.turno
            and not partida.terminada
            and lectura.tipo is TipoLectura.JUGADA
        ):
            jugada = partida.intentar_jugada(lectura.movimiento)
        boton = partida.pulsar_boton(color)

        motivo = ""
        if jugada is not None and jugada.aceptado:
            # La posición física pasa a ser la nueva posición de reposo.
            self._lectura = self._rastreador.procesar_ocupacion(lectura.ocupacion)
        elif jugada is not None:
            motivo = jugada.motivo
        elif boton.tipo is TipoBoton.IGNORADO_SIN_MOVIMIENTO:
            motivo = describir_lectura(lectura, self.board)
        return ResultadoConfirmacion(boton=boton, lectura=lectura, jugada=jugada, motivo=motivo)

    # -- Tiempo y fin -------------------------------------------------------------

    def actualizar_tiempo(self) -> bool:
        """Descuenta el tiempo real transcurrido; `True` si recién ahora se agotó."""
        return self._partida.actualizar_tiempo()

    def finalizar(self, motivo: str = MOTIVO_ABANDONO) -> None:
        """Cierra la partida y su registro (ver `Partida.finalizar`)."""
        self._partida.finalizar(motivo)
