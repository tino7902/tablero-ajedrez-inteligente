"""Una partida desde la pantalla táctil, de punta a punta y sin bloquear nunca.

`SesionPvP` y `SesionMagnus` envuelven a `PartidaFisica` y a `PartidaVsMagnus` con lo que
necesita la pantalla (`io/menus.py`): acomodar las piezas antes de empezar, la cuenta
regresiva de PvP, las tablas y el texto del final. La pantalla llama a `actualizar()` en
cada vuelta de su loop y dibuja lo que la sesión expone; los botones del reloj y los
toques llegan como llamadas (`pulsar_boton`, `rendirse`, ...).

No toca hardware: recibe una fuente de ocupación (la matriz del Nano en la Pi, el tablero
simulado en la notebook), una función para pintar los LEDs y, contra Magnus, una función
que devuelve la jugada del motor, que la sesión corre en su propio hilo. Así se testea sin
nada de eso (`tests/test_sesion.py`). Diseño en `software-docs/menus.md`.
"""

from __future__ import annotations

import enum
import math
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Protocol

import chess

from tablero.logica.estado_tablero import EstadoTablero
from tablero.logica.eventos import Marca, Ocupacion, RastreadorMovimientos, TipoLectura
from tablero.logica.notacion import NOMBRES_COLOR
from tablero.logica.partida import (
    MOTIVO_ABANDONO,
    MOTIVO_ACUERDO,
    MOTIVO_MATE,
    MOTIVO_RENDICION,
    MOTIVO_TIEMPO,
    TipoBoton,
)
from tablero.logica.partida_fisica import PartidaFisica, describir_diferencias
from tablero.logica.partida_magnus import Fase, PartidaVsMagnus

if TYPE_CHECKING:  # pragma: no cover - solo para tipos
    from tablero.logica.registro import RegistroPartida

# Cuenta regresiva de PvP: un segundo por texto, después arranca el reloj.
TEXTOS_CUENTA_REGRESIVA = ("3", "2", "1", "¡Partida iniciada!")
SEGUNDOS_POR_PASO = 1.0


class FaseSesion(enum.Enum):
    PREPARANDO = enum.auto()  # acomodar las piezas; un botón arranca
    CUENTA_REGRESIVA = enum.auto()  # solo PvP
    JUGANDO = enum.auto()
    TERMINADA = enum.auto()


class ErrorTablero(Exception):
    """La fuente de ocupación falló (por ejemplo, se desconectó el Nano). El texto dice qué revisar."""


class FuenteOcupacion(Protocol):
    def leer(self) -> Ocupacion | None:
        """La ocupación nueva si cambió desde la última vez, si no `None`. `ErrorTablero` si falla."""
        ...


Pintar = Callable[[dict[chess.Square, Marca]], None]
CrearRegistro = Callable[[], "RegistroPartida | None"]


def _sin_registro() -> None:
    return None


class _Sesion:
    """Lo común: acomodar las piezas, la línea de estado y saber cuándo redibujar."""

    def __init__(self, fuente: FuenteOcupacion, pintar: Pintar, fuente_tiempo: Callable[[], float]) -> None:
        self._fuente = fuente
        self._pintar = pintar
        self._ahora = fuente_tiempo
        self.fase = FaseSesion.PREPARANDO
        self._preparacion = RastreadorMovimientos(EstadoTablero())
        self._ocupacion: Ocupacion | None = None
        self.faltan: Ocupacion = frozenset()
        self.sobran: Ocupacion = frozenset()
        # Lo último que contestó un botón rechazado; se borra cuando cambian las piezas.
        self._mensaje = ""
        self._firma_dibujada: object = None
        self._pintadas: dict[chess.Square, Marca] | None = None

    # -- Acomodar las piezas --------------------------------------------------------

    @property
    def posicion_lista(self) -> bool:
        return self._ocupacion is not None and not self.faltan and not self.sobran

    def _preparar(self, ocupacion: Ocupacion) -> None:
        lectura = self._preparacion.procesar_ocupacion(ocupacion)
        self.faltan, self.sobran = lectura.faltan, lectura.sobran
        if self.posicion_lista:
            self._pintar_si_cambio(dict.fromkeys(ocupacion, Marca.JUGADA))
        else:
            self._pintar_si_cambio(
                {**dict.fromkeys(self.faltan, Marca.FALTA), **dict.fromkeys(self.sobran, Marca.SOBRA)}
            )

    # -- Comunes --------------------------------------------------------------------

    def _pintar_si_cambio(self, marcas: dict[chess.Square, Marca]) -> None:
        if marcas != self._pintadas:
            self._pintadas = marcas
            self._pintar(marcas)

    def _leer(self) -> Ocupacion | None:
        ocupacion = self._fuente.leer()
        if ocupacion is not None:
            self._ocupacion = ocupacion
            self._mensaje = ""
        return ocupacion

    def _firma(self) -> object:  # pragma: no cover - lo definen las subclases
        raise NotImplementedError

    def _hay_cambios(self) -> bool:
        firma = self._firma()
        if firma == self._firma_dibujada:
            return False
        self._firma_dibujada = firma
        return True


class SesionPvP(_Sesion):
    """Jugador contra jugador, con reloj: acomodar, cuenta regresiva, partida y final."""

    def __init__(
        self,
        segundos_por_jugador: float,
        fuente: FuenteOcupacion,
        pintar: Pintar,
        crear_registro: CrearRegistro = _sin_registro,
        fuente_tiempo: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(fuente, pintar, fuente_tiempo)
        self.segundos_por_jugador = segundos_por_jugador
        self._crear_registro = crear_registro
        self.partida: PartidaFisica | None = None
        self._inicio_cuenta = 0.0

    # -- Lecturas para dibujar ------------------------------------------------------

    @property
    def paso_cuenta_regresiva(self) -> int:
        transcurrido = self._ahora() - self._inicio_cuenta
        return min(int(transcurrido / SEGUNDOS_POR_PASO), len(TEXTOS_CUENTA_REGRESIVA) - 1)

    def restante(self, color: chess.Color) -> float:
        if self.partida is None:
            return self.segundos_por_jugador
        restante = self.partida.partida.reloj.restante(color)
        assert restante is not None  # PvP: siempre con límite
        return restante

    @property
    def turno(self) -> chess.Color | None:
        """A quién le corre el reloj; `None` antes de empezar y al terminar."""
        if self.partida is None or self.fase is not FaseSesion.JUGANDO:
            return None
        return self.partida.partida.turno

    @property
    def oferta_tablas(self) -> chess.Color | None:
        return None if self.partida is None else self.partida.oferta_tablas

    @property
    def linea_estado(self) -> str:
        """Una línea para abajo de la pantalla: el último rechazo o lo que se está armando."""
        if self.fase is not FaseSesion.JUGANDO or self.partida is None:
            return ""
        if self._mensaje:
            return self._mensaje
        lectura = self.partida.lectura
        if lectura.tipo is TipoLectura.REPOSO:
            return ""
        return f"{NOMBRES_COLOR[self.partida.partida.turno].capitalize()}: {self.partida.describir()}"

    def texto_final(self) -> tuple[str, str]:
        """Título y detalle de la pantalla final."""
        assert self.partida is not None
        return describir_fin(self.partida)

    # -- Entradas -------------------------------------------------------------------

    def actualizar(self) -> bool:
        """Una vuelta: lee la fuente, avanza la cuenta o el reloj y pinta. `True` si hay que redibujar."""
        ocupacion = self._leer()
        if self.fase is FaseSesion.PREPARANDO:
            if ocupacion is not None:
                self._preparar(ocupacion)
        elif self.fase is FaseSesion.CUENTA_REGRESIVA:
            if ocupacion is not None:
                self._preparar(ocupacion)
            if self._ahora() - self._inicio_cuenta >= len(TEXTOS_CUENTA_REGRESIVA) * SEGUNDOS_POR_PASO:
                self._empezar()
        elif self.fase is FaseSesion.JUGANDO:
            assert self.partida is not None
            if ocupacion is not None:
                self.partida.procesar_ocupacion(ocupacion)
                self._pintar_si_cambio(self.partida.marcas())
            self.partida.actualizar_tiempo()
            self._revisar_fin()
        return self._hay_cambios()

    def pulsar_boton(self, color: chess.Color) -> None:
        if self.fase is FaseSesion.PREPARANDO and self.posicion_lista:
            self.fase = FaseSesion.CUENTA_REGRESIVA
            self._inicio_cuenta = self._ahora()
            return
        if self.fase is not FaseSesion.JUGANDO:
            return
        assert self.partida is not None
        resultado = self.partida.pulsar_boton(color)
        if resultado.paso_turno:
            self._mensaje = ""
            self._pintar_si_cambio(self.partida.marcas())
        elif resultado.boton.tipo is not TipoBoton.IGNORADO_TERMINADA:
            motivo = resultado.motivo or resultado.boton.motivo
            self._mensaje = f"Botón de {NOMBRES_COLOR[color]}: {motivo}"
        self._revisar_fin()

    def rendirse(self, color: chess.Color) -> None:
        if self.fase is FaseSesion.JUGANDO and self.partida is not None:
            self.partida.partida.rendirse(color)
            self._revisar_fin()

    def ofrecer_tablas(self, color: chess.Color) -> None:
        if self.fase is FaseSesion.JUGANDO and self.partida is not None:
            self.partida.ofrecer_tablas(color)

    def responder_tablas(self, acepta: bool) -> None:
        if self.fase is FaseSesion.JUGANDO and self.partida is not None:
            self.partida.responder_tablas(acepta)
            self._revisar_fin()

    def cerrar(self) -> None:
        """Se sale de la pantalla: abandona la partida si seguía y apaga los LEDs."""
        if self.partida is not None:
            self.partida.finalizar(MOTIVO_ABANDONO)
        self._pintar_si_cambio({})

    # -- Internos -------------------------------------------------------------------

    def _empezar(self) -> None:
        self.partida = PartidaFisica(
            segundos_por_jugador=self.segundos_por_jugador,
            registro=self._crear_registro(),
            fuente_tiempo=self._ahora,
        )
        self.fase = FaseSesion.JUGANDO
        if self._ocupacion is not None:
            self.partida.procesar_ocupacion(self._ocupacion)
        self._pintar_si_cambio(self.partida.marcas())

    def _revisar_fin(self) -> None:
        if self.partida is not None and self.partida.terminada and self.fase is FaseSesion.JUGANDO:
            self.fase = FaseSesion.TERMINADA
            self.partida.finalizar()
            self._pintar_si_cambio({})

    def _firma(self) -> object:
        relojes = tuple(math.ceil(self.restante(c)) for c in (chess.WHITE, chess.BLACK))
        paso = self.paso_cuenta_regresiva if self.fase is FaseSesion.CUENTA_REGRESIVA else None
        return (
            self.fase,
            self.faltan,
            self.sobran,
            self._ocupacion is not None,
            paso,
            relojes,
            self.turno,
            self.oferta_tablas,
            self.linea_estado,
        )


class SesionMagnus(_Sesion):
    """Jugador contra Magnus, sin límite de tiempo: acomodar, partida y final."""

    def __init__(
        self,
        color_humano: chess.Color,
        fuente: FuenteOcupacion,
        pintar: Pintar,
        motor: Callable[[chess.Board], chess.Move],
        crear_registro: CrearRegistro = _sin_registro,
        fuente_tiempo: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(fuente, pintar, fuente_tiempo)
        self.color_humano = color_humano
        self._motor = motor
        self._crear_registro = crear_registro
        self.partida: PartidaVsMagnus | None = None
        self._ejecutor = ThreadPoolExecutor(max_workers=1)
        self._pedido: Future[chess.Move] | None = None
        self.error_motor = ""

    # -- Lecturas para dibujar ------------------------------------------------------

    @property
    def duracion(self) -> float:
        return 0.0 if self.partida is None else self.partida.duracion

    @property
    def fase_partida(self) -> Fase | None:
        return None if self.partida is None else self.partida.fase

    @property
    def texto_estado(self) -> str:
        """El texto del recuadro grande: la fase, la jugada de Magnus o el final."""
        if self.error_motor:
            return f"Magnus dejó de responder: {self.error_motor}"
        if self.partida is None:
            return ""
        return self.partida.texto_estado()

    @property
    def linea_estado(self) -> str:
        if self.fase is not FaseSesion.JUGANDO or self.partida is None:
            return ""
        if self._mensaje:
            return self._mensaje
        if self.partida.fase is Fase.TURNO_HUMANO and self.partida.lectura.tipo is not TipoLectura.REPOSO:
            return self.partida.describir()
        if self.partida.fase is Fase.MOVER_MAGNUS and self.partida.lectura.tipo is not TipoLectura.REPOSO:
            lectura = self.partida.lectura
            return describir_diferencias(lectura.faltan, lectura.sobran)
        return ""

    # -- Entradas -------------------------------------------------------------------

    def actualizar(self) -> bool:
        ocupacion = self._leer()
        if self.fase is FaseSesion.PREPARANDO:
            if ocupacion is not None:
                self._preparar(ocupacion)
        elif self.partida is not None:
            if ocupacion is not None:
                self.partida.procesar_ocupacion(ocupacion)
            if self.fase is FaseSesion.JUGANDO:
                self._consultar_motor()
                self.partida.actualizar_tiempo()
                if self.partida.terminada:
                    self.fase = FaseSesion.TERMINADA
            # También al terminar: si Magnus dio mate, su jugada sigue en los LEDs.
            self._pintar_si_cambio(self.partida.marcas())
        return self._hay_cambios()

    def pulsar_boton(self, color: chess.Color) -> None:  # cualquier botón sirve
        if self.fase is FaseSesion.PREPARANDO and self.posicion_lista:
            self.partida = PartidaVsMagnus(
                color_humano=self.color_humano, registro=self._crear_registro(), fuente_tiempo=self._ahora
            )
            self.fase = FaseSesion.JUGANDO
            if self._ocupacion is not None:
                self.partida.procesar_ocupacion(self._ocupacion)
            self._pintar_si_cambio(self.partida.marcas())
            return
        if self.fase is not FaseSesion.JUGANDO or self.partida is None:
            return
        resultado = self.partida.pulsar_boton()
        self._mensaje = "" if resultado.confirmado else resultado.motivo
        self._pintar_si_cambio(self.partida.marcas())
        if self.partida.terminada:
            self.fase = FaseSesion.TERMINADA

    def rendirse(self, color: chess.Color | None = None) -> None:  # se rinde el humano
        if self.fase is FaseSesion.JUGANDO and self.partida is not None:
            self.partida.rendirse()
            self.fase = FaseSesion.TERMINADA
            self._pintar_si_cambio(self.partida.marcas())

    def cerrar(self) -> None:
        """Abandona si seguía, espera la jugada en curso del motor (como mucho un nivel) y apaga los LEDs."""
        if self.partida is not None:
            self.partida.finalizar(MOTIVO_ABANDONO)
        self._ejecutor.shutdown(wait=True, cancel_futures=True)
        self._pintar_si_cambio({})

    # -- Internos -------------------------------------------------------------------

    def _consultar_motor(self) -> None:
        assert self.partida is not None
        if self.partida.fase is Fase.MAGNUS_PENSANDO and self._pedido is None:
            self._pedido = self._ejecutor.submit(self._motor, self.partida.board_para_motor())
        if self._pedido is not None and self._pedido.done():
            pedido, self._pedido = self._pedido, None
            try:
                movimiento = pedido.result()
            except Exception as error:  # noqa: BLE001 - cualquier falla del motor termina la partida
                self.error_motor = str(error) or type(error).__name__
                self.partida.finalizar(MOTIVO_ABANDONO)
                self.fase = FaseSesion.TERMINADA
                return
            self.partida.recibir_jugada_motor(movimiento)

    def _firma(self) -> object:
        return (
            self.fase,
            self.faltan,
            self.sobran,
            self._ocupacion is not None,
            self.fase_partida,
            self.texto_estado,
            int(self.duracion),
            self.linea_estado,
        )


def describir_fin(partida: PartidaFisica) -> tuple[str, str]:
    """Título y detalle del final de una partida PvP, para la pantalla."""
    p = partida.partida
    motivo = p.motivo_fin
    resultado = p.resultado()
    ganador = {"1-0": chess.WHITE, "0-1": chess.BLACK}.get(resultado)
    ganan = f"Ganan {NOMBRES_COLOR[ganador]}" if ganador is not None else "Tablas"
    if motivo == MOTIVO_TIEMPO and ganador is not None:
        return f"¡{NOMBRES_COLOR[not ganador].capitalize()} se quedaron sin tiempo!", ganan
    if motivo == MOTIVO_MATE:
        return "¡Jaque mate!", ganan
    if motivo == MOTIVO_RENDICION and ganador is not None:
        return f"{NOMBRES_COLOR[not ganador].capitalize()} se rindieron", ganan
    if motivo == MOTIVO_ACUERDO:
        return "Tablas por acuerdo", "½-½"
    if motivo == MOTIVO_ABANDONO:
        return "Partida abandonada", ""
    return f"Tablas: {_motivo_tablas(p.estado.board)}", "½-½"


def _motivo_tablas(board: chess.Board) -> str:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return "fin de la partida"
    return {
        chess.Termination.STALEMATE: "ahogado",
        chess.Termination.INSUFFICIENT_MATERIAL: "material insuficiente",
        chess.Termination.THREEFOLD_REPETITION: "triple repetición",
        chess.Termination.FIVEFOLD_REPETITION: "quíntuple repetición",
        chess.Termination.FIFTY_MOVES: "50 jugadas",
        chess.Termination.SEVENTYFIVE_MOVES: "75 jugadas",
    }.get(outcome.termination, "fin de la partida")
