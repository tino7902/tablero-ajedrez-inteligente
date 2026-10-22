"""Interfaz de la pantalla táctil (RPI LCD V3, 480x320): menús y partidas en el tablero.

Implementa los bocetos de `diseño-docs/diseño-interfaz.md` y el flujo de
`software-docs/menus.md`:

    menú → contra un amigo → tiempo → acomodá las piezas → 3, 2, 1 → partida PvP → fin
         → contra Magnus  → dificultad → color → acomodá las piezas → partida → fin

La partida en sí la maneja `logica/sesion.py` (`SesionPvP`, `SesionMagnus`): esta pantalla
la crea, le pasa los toques y los botones del reloj, llama a `actualizar()` en cada vuelta
del loop y dibuja lo que la sesión expone. Lo que depende del hardware (de dónde sale la
ocupación de las casillas, cómo se pintan los LEDs, cómo se abre Stockfish) llega en un
`Hardware`: este archivo **no importa** nada de GPIO, del Nano ni de los LEDs.

- En la Raspberry: `io/menus_gpio.py` arma el `Hardware` real (matriz del Nano, tira de
  LEDs, botones GPIO) y llama a `ejecutar_menus`.
- En la notebook, corriendo este módulo con `TABLERO_PANTALLA_VENTANA=1`: tablero simulado
  manejado desde la terminal (`e2e4`, ver `logica/tablero_simulado.py`), sin LEDs, y los
  botones del reloj en las teclas ← (blancas) y → (negras):

    env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus
"""

from __future__ import annotations

import enum
import functools
import logging
import random
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from tablero.io._sdl import configurar_entorno_sdl

configurar_entorno_sdl()

import chess
import pygame

from tablero import config
from tablero.io import calibracion_touch
from tablero.logica.notacion import NOMBRES_COLOR
from tablero.logica.partida_magnus import nombres_pgn
from tablero.logica.registro import RegistroPartida
from tablero.logica.reloj import formatear_duracion, formatear_tiempo
from tablero.logica.sesion import (
    TEXTOS_CUENTA_REGRESIVA,
    ErrorTablero,
    FaseSesion,
    FuenteOcupacion,
    Pintar,
    SesionMagnus,
    SesionPvP,
)

logger = logging.getLogger(__name__)

_BLANCO = (255, 255, 255)
_NEGRO = (0, 0, 0)
_AZUL = (0, 0, 205)
_ROJO = (200, 30, 30)
_GRIS = (140, 140, 140)
_VERDE = (60, 180, 75)  # mismo verde que ya usa io/pantalla.py; indicador de turno activo
_NARANJA = (215, 120, 0)

_TAM_TITULO = 40
_TAM_SUBTITULO = 18
_TAM_PREGUNTA = 18
_TAM_BOTON = 22
_TAM_BOTON_CHICO = 18
_TAM_INDICADOR = 15
_TAM_RELOJ = 44
_TAM_PIE = 12
_TAM_ESTADO = 15
_TAM_TEXTO = 22
_TAM_CUENTA_REGRESIVA_NUMERO = 90

_SUBTITULO_MAGNUS = "El tablero de ajedrez inteligente"
_PIE_MAGNUS = "Desarrollado por CDR-FPUNA 2026"

_RECT_VOLVER = pygame.Rect(10, 10, 90, 32)
_X_COLUMNA = {chess.WHITE: 120, chess.BLACK: 360}  # centro de cada mitad en PvP

NOMBRE_MENU_PRINCIPAL = "menu_principal"
NOMBRE_SELECTOR_TIEMPO = "selector_tiempo"
NOMBRE_SELECTOR_DIFICULTAD = "selector_dificultad"
NOMBRE_SELECTOR_COLOR = "selector_color"
NOMBRE_PARTIDA = "partida"  # lo que se ve lo decide la sesión (ver `_vista`)

EVENTO_BOTON_RELOJ = pygame.USEREVENT + 1  # público: lo usa io/menus_gpio.py
_COLOR_DE_BOTON = {"boton_1": chess.WHITE, "boton_2": chess.BLACK}


# -- Hardware ---------------------------------------------------------------------------


class Motor(Protocol):
    def mejor_movimiento(self, tablero: chess.Board) -> chess.Move: ...

    def cerrar(self) -> None: ...


@dataclass
class Hardware:
    """Lo que la pantalla necesita del mundo físico, sin saber de dónde sale.

    `crear_fuente` puede tirar `ErrorTablero` (por ejemplo, si no está el Nano) y
    `crear_motor` `FileNotFoundError` si no está Stockfish: la pantalla muestra el error.
    """

    crear_fuente: Callable[[], FuenteOcupacion]
    pintar: Pintar
    crear_motor: Callable[[str], Motor]


def crear_motor_stockfish(nivel: str) -> Motor:
    from tablero.motor.stockfish import MotorStockfish  # no hace falta para PvP

    return MotorStockfish(nivel=nivel)


# -- Estado de la aplicación ------------------------------------------------------------


class EleccionColor(enum.Enum):
    """Qué color eligió tocar el jugador en `selector_color` (antes de resolver 'Aleatorio')."""

    BLANCAS = enum.auto()
    NEGRAS = enum.auto()
    ALEATORIO = enum.auto()


@dataclass(frozen=True)
class Boton:
    texto: str
    rect: pygame.Rect
    destino: str
    eleccion_color: EleccionColor | None = None
    duracion_segundos: int | None = None
    dificultad: str | None = None


@dataclass(frozen=True)
class Pantalla:
    nombre: str
    dibujar: Callable[[pygame.Surface, Pantalla], None]
    botones: list[Boton] = field(default_factory=list)
    permite_volver: bool = True


@dataclass
class EstadoApp:
    """Lo elegido en los menús, la sesión en curso y lo que se muestra encima de ella."""

    historial: list[str] = field(default_factory=lambda: [NOMBRE_MENU_PRINCIPAL])
    duracion_segundos: int = 5 * 60
    dificultad: str = "facil"
    color_humano: chess.Color = chess.WHITE
    sesion: SesionPvP | SesionMagnus | None = None
    motor: Motor | None = None
    confirmar_rendicion: chess.Color | None = None
    error: str = ""


def _resolver_color(eleccion: EleccionColor) -> chess.Color:
    if eleccion is EleccionColor.BLANCAS:
        return chess.WHITE
    if eleccion is EleccionColor.NEGRAS:
        return chess.BLACK
    return random.choice([chess.WHITE, chess.BLACK])


# -- Dibujo: piezas comunes -------------------------------------------------------------


@functools.cache
def _fuente(tamano: int) -> pygame.font.Font:
    # DejaVu tiene "→", "½" y "…", que usan los textos de la partida; la fuente por
    # defecto de pygame no.
    return pygame.font.Font(pygame.font.match_font("dejavusans"), tamano)


def _texto(surf: pygame.Surface, texto: str, tamano: int, color, centro: tuple[int, int]) -> None:
    if not texto:
        return
    render = _fuente(tamano).render(texto, True, color)
    surf.blit(render, render.get_rect(center=centro))


def _envolver(texto: str, tamano: int, ancho: int) -> list[str]:
    """Parte `texto` en líneas que entren en `ancho` píxeles (respeta los saltos de línea)."""
    fuente = _fuente(tamano)
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split(" "):
            prueba = f"{actual} {palabra}".strip()
            if fuente.size(prueba)[0] <= ancho or not actual:
                actual = prueba
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
    return lineas


def _parrafo(
    surf: pygame.Surface, texto: str, tamano: int, color, centro_x: int, y: int, ancho: int, max_lineas: int = 4
) -> None:
    alto = _fuente(tamano).get_linesize()
    for i, linea in enumerate(_envolver(texto, tamano, ancho)[:max_lineas]):
        _texto(surf, linea, tamano, color, (centro_x, y + i * alto))


def _rect(centro: tuple[int, int], ancho: int, alto: int) -> pygame.Rect:
    rect = pygame.Rect(0, 0, ancho, alto)
    rect.center = centro
    return rect


def _dibujar_rect_boton(surf: pygame.Surface, rect: pygame.Rect, texto: str, color, tamano: int = _TAM_BOTON) -> None:
    pygame.draw.rect(surf, color, rect, width=3, border_radius=10)
    _texto(surf, texto, tamano, color, rect.center)


def _fila_de_botones(cantidad: int, y: int, alto: int = 80, gap: int = 20) -> list[pygame.Rect]:
    """Centra `cantidad` rects del mismo tamaño en una fila horizontal, a la altura `y`."""
    margen = 30
    ancho = (config.PANTALLA_ANCHO - 2 * margen - gap * (cantidad - 1)) // cantidad
    ancho_total = ancho * cantidad + gap * (cantidad - 1)
    x0 = (config.PANTALLA_ANCHO - ancho_total) // 2
    return [pygame.Rect(x0 + i * (ancho + gap), y, ancho, alto) for i in range(cantidad)]


def _dibujar_indicador(surf: pygame.Surface, centro: tuple[int, int], texto: str, color) -> None:
    render = _fuente(_TAM_INDICADOR).render(texto, True, color)
    rect = render.get_rect(center=centro).inflate(16, 8)
    pygame.draw.rect(surf, color, rect, width=2, border_radius=6)
    surf.blit(render, render.get_rect(center=centro))


def _dibujar_reloj(surf: pygame.Surface, centro: tuple[int, int], texto: str, activo: bool) -> None:
    rect = _rect(centro, 170, 66)
    pygame.draw.rect(surf, _VERDE if activo else _AZUL, rect, width=4 if activo else 3, border_radius=12)
    _texto(surf, texto, _TAM_RELOJ, _NEGRO, rect.center)


def _dibujar_linea_estado(surf: pygame.Surface, texto: str) -> None:
    if texto:
        linea = _envolver(texto, _TAM_ESTADO, config.PANTALLA_ANCHO - 20)
        for i, parte in enumerate(linea[:2]):
            _texto(surf, parte, _TAM_ESTADO, _NARANJA, (config.PANTALLA_ANCHO // 2, 280 + i * 18))


# -- Menús ------------------------------------------------------------------------------


def _dibujar_pantalla_seleccion(
    surf: pygame.Surface, pantalla: Pantalla, *, titulo: str, subtitulo: str, pregunta: str
) -> None:
    centro_x = config.PANTALLA_ANCHO // 2
    _texto(surf, titulo, _TAM_TITULO, _AZUL, (centro_x, 45))
    _texto(surf, subtitulo, _TAM_SUBTITULO, _AZUL, (centro_x, 78))
    _texto(surf, pregunta, _TAM_PREGUNTA, _NEGRO, (centro_x, 110))
    for boton in pantalla.botones:
        _dibujar_rect_boton(surf, boton.rect, boton.texto, _AZUL)


def _construir_menus() -> dict[str, Pantalla]:
    def seleccion(nombre: str, pregunta: str, botones: list[Boton], volver: bool = True) -> Pantalla:
        dibujar = functools.partial(
            _dibujar_pantalla_seleccion, titulo="Magnus", subtitulo=_SUBTITULO_MAGNUS, pregunta=pregunta
        )
        return Pantalla(nombre, dibujar, botones, volver)

    dos, tres = _fila_de_botones(2, y=150), _fila_de_botones(3, y=150)
    pantallas = [
        seleccion(
            NOMBRE_MENU_PRINCIPAL,
            "¿Quién será tu oponente?",
            [
                Boton("Contra un amigo", dos[0], NOMBRE_SELECTOR_TIEMPO),
                Boton("Contra Magnus", dos[1], NOMBRE_SELECTOR_DIFICULTAD),
            ],
            volver=False,
        ),
        seleccion(
            NOMBRE_SELECTOR_TIEMPO,
            "¿Cuánto va a durar tu partida?",
            [
                Boton("3 minutos", tres[0], NOMBRE_PARTIDA, duracion_segundos=3 * 60),
                Boton("5 minutos", tres[1], NOMBRE_PARTIDA, duracion_segundos=5 * 60),
                Boton("10 minutos", tres[2], NOMBRE_PARTIDA, duracion_segundos=10 * 60),
            ],
        ),
        seleccion(
            NOMBRE_SELECTOR_DIFICULTAD,
            "¿Qué nivel de desafío estás buscando?",
            [
                Boton("Fácil", tres[0], NOMBRE_SELECTOR_COLOR, dificultad="facil"),
                Boton("Medio", tres[1], NOMBRE_SELECTOR_COLOR, dificultad="medio"),
                Boton("Difícil", tres[2], NOMBRE_SELECTOR_COLOR, dificultad="dificil"),
            ],
        ),
        seleccion(
            NOMBRE_SELECTOR_COLOR,
            "¿Con qué color querés jugar?",
            [
                Boton("Blancas", tres[0], NOMBRE_PARTIDA, EleccionColor.BLANCAS),
                Boton("Aleatorio", tres[1], NOMBRE_PARTIDA, EleccionColor.ALEATORIO),
                Boton("Negras", tres[2], NOMBRE_PARTIDA, EleccionColor.NEGRAS),
            ],
        ),
    ]
    return {p.nombre: p for p in pantallas}


# -- Partida: qué se ve y dónde se toca --------------------------------------------------


class Vista(enum.Enum):
    PREPARAR = enum.auto()
    CUENTA_REGRESIVA = enum.auto()
    JUEGO_PVP = enum.auto()
    JUEGO_MAGNUS = enum.auto()
    CONFIRMAR_RENDICION = enum.auto()
    FIN = enum.auto()
    ERROR = enum.auto()


def _vista(estado: EstadoApp) -> Vista | None:
    """Qué pantalla de partida corresponde; `None` si se está en los menús."""
    if estado.error:
        return Vista.ERROR
    sesion = estado.sesion
    if sesion is None:
        return None
    if estado.confirmar_rendicion is not None and sesion.fase is FaseSesion.JUGANDO:
        return Vista.CONFIRMAR_RENDICION
    if sesion.fase is FaseSesion.PREPARANDO:
        return Vista.PREPARAR
    if sesion.fase is FaseSesion.CUENTA_REGRESIVA:
        return Vista.CUENTA_REGRESIVA
    if sesion.fase is FaseSesion.TERMINADA:
        return Vista.FIN
    return Vista.JUEGO_PVP if isinstance(sesion, SesionPvP) else Vista.JUEGO_MAGNUS


# Botones de las pantallas de partida: (texto, rect) se calculan en un solo lugar, así
# el dibujo y el toque usan los mismos rects.
_RECT_SI = _rect((140, 200), 180, 70)
_RECT_NO = _rect((340, 200), 180, 70)
_RECT_MENU = _rect((config.PANTALLA_ANCHO // 2, 245), 220, 60)
_RECT_RENDIRSE_MAGNUS = _rect((config.PANTALLA_ANCHO // 2, 238), 170, 46)


def _rects_pvp(color: chess.Color) -> tuple[pygame.Rect, pygame.Rect]:
    """Los dos botones de la columna de `color`: el de la izquierda y el de la derecha."""
    x = _X_COLUMNA[color]
    return _rect((x - 55, 228), 104, 46), _rect((x + 55, 228), 104, 46)


def _dibujar_preparar(surf: pygame.Surface, sesion: SesionPvP | SesionMagnus) -> None:
    centro_x = config.PANTALLA_ANCHO // 2
    _texto(surf, "Acomodá las piezas", 30, _AZUL, (centro_x, 70))
    if sesion.posicion_lista:
        _texto(surf, "¡Posición lista!", _TAM_TEXTO, _VERDE, (centro_x, 140))
        _texto(surf, "Apretá un botón del reloj para empezar", _TAM_PREGUNTA, _NEGRO, (centro_x, 180))
        return
    _texto(surf, f"Faltan {len(sesion.faltan)}  ·  sobran {len(sesion.sobran)}", _TAM_TEXTO, _ROJO, (centro_x, 130))
    _texto(surf, "En el tablero: rojo = falta, amarillo = sobra", _TAM_PREGUNTA, _NEGRO, (centro_x, 175))
    casillas = sorted(sesion.faltan | sesion.sobran)
    if casillas:
        nombres = ", ".join(chess.square_name(c) for c in casillas[:12]) + ("…" if len(casillas) > 12 else "")
        _parrafo(surf, nombres, _TAM_ESTADO, _GRIS, centro_x, 210, config.PANTALLA_ANCHO - 40, max_lineas=2)


def _dibujar_cuenta_regresiva(surf: pygame.Surface, sesion: SesionPvP) -> None:
    texto = TEXTOS_CUENTA_REGRESIVA[sesion.paso_cuenta_regresiva]
    tamano = _TAM_CUENTA_REGRESIVA_NUMERO if texto.isdigit() else _TAM_TITULO
    _texto(surf, texto, tamano, _AZUL, (config.PANTALLA_ANCHO // 2, config.PANTALLA_ALTO // 2))


def _dibujar_juego_pvp(surf: pygame.Surface, sesion: SesionPvP) -> None:
    pygame.draw.line(surf, _GRIS, (240, 20), (240, 255), 1)
    oferta = sesion.oferta_tablas
    for color, x in _X_COLUMNA.items():
        _texto(surf, NOMBRES_COLOR[color].capitalize(), _TAM_TEXTO, _NEGRO, (x, 30))
        es_turno = sesion.turno == color
        if es_turno:
            _dibujar_indicador(surf, (x, 66), "¡Es tu turno!", _VERDE)
        _dibujar_reloj(surf, (x, 128), formatear_tiempo(sesion.restante(color)), es_turno)
        izquierda, derecha = _rects_pvp(color)
        if oferta is not None and oferta != color:
            _texto(surf, f"{NOMBRES_COLOR[oferta].capitalize()} ofrecen tablas", _TAM_ESTADO, _NARANJA, (x, 186))
            _dibujar_rect_boton(surf, izquierda, "Aceptar", _VERDE, _TAM_BOTON_CHICO)
            _dibujar_rect_boton(surf, derecha, "Rechazar", _ROJO, _TAM_BOTON_CHICO)
        else:
            _dibujar_rect_boton(surf, izquierda, "¿Rendirse?", _ROJO, _TAM_BOTON_CHICO)
            if oferta == color:
                _dibujar_rect_boton(surf, derecha, "Ofrecidas", _GRIS, _TAM_BOTON_CHICO)
            else:
                _dibujar_rect_boton(surf, derecha, "Tablas", _AZUL, _TAM_BOTON_CHICO)
    _dibujar_linea_estado(surf, sesion.linea_estado)


def _dibujar_juego_magnus(surf: pygame.Surface, sesion: SesionMagnus) -> None:
    _texto(surf, f"¡Sos {NOMBRES_COLOR[sesion.color_humano]}!", _TAM_TEXTO, _NEGRO, (170, 30))
    _texto(surf, f"Tiempo {formatear_duracion(sesion.duracion)}", _TAM_TEXTO, _AZUL, (380, 30))
    recuadro = pygame.Rect(20, 58, config.PANTALLA_ANCHO - 40, 142)
    pygame.draw.rect(surf, _AZUL, recuadro, width=3, border_radius=12)
    lineas = _envolver(sesion.texto_estado, _TAM_TEXTO, recuadro.width - 24)[:4]
    alto = _fuente(_TAM_TEXTO).get_linesize()
    y0 = recuadro.centery - (len(lineas) - 1) * alto // 2
    for i, linea in enumerate(lineas):
        _texto(surf, linea, _TAM_TEXTO, _NEGRO, (recuadro.centerx, y0 + i * alto))
    _dibujar_rect_boton(surf, _RECT_RENDIRSE_MAGNUS, "¿Rendirse?", _ROJO, _TAM_BOTON_CHICO)
    _dibujar_linea_estado(surf, sesion.linea_estado)


def _dibujar_confirmar(surf: pygame.Surface, estado: EstadoApp) -> None:
    color = estado.confirmar_rendicion
    assert color is not None
    pregunta = (
        "¿Te rendís?"
        if isinstance(estado.sesion, SesionMagnus)
        else f"¿{NOMBRES_COLOR[color].capitalize()} se rinden?"
    )
    _texto(surf, pregunta, 32, _ROJO, (config.PANTALLA_ANCHO // 2, 100))
    _dibujar_rect_boton(surf, _RECT_SI, "Sí, me rindo", _ROJO)
    _dibujar_rect_boton(surf, _RECT_NO, "No", _AZUL)


def _dibujar_fin(surf: pygame.Surface, sesion: SesionPvP | SesionMagnus) -> None:
    centro_x = config.PANTALLA_ANCHO // 2
    if isinstance(sesion, SesionPvP):
        titulo, detalle = sesion.texto_final()
        _texto(surf, titulo, 28, _AZUL, (centro_x, 90))
        _texto(surf, detalle, _TAM_TEXTO, _NEGRO, (centro_x, 145))
    else:
        _parrafo(surf, sesion.texto_estado, _TAM_TEXTO, _AZUL, centro_x, 70, config.PANTALLA_ANCHO - 40)
    _dibujar_rect_boton(surf, _RECT_MENU, "Menú principal", _AZUL)


def _dibujar_error(surf: pygame.Surface, estado: EstadoApp) -> None:
    centro_x = config.PANTALLA_ANCHO // 2
    _texto(surf, "Problema con el tablero", 28, _ROJO, (centro_x, 50))
    _parrafo(surf, estado.error, _TAM_ESTADO, _NEGRO, centro_x, 95, config.PANTALLA_ANCHO - 30, max_lineas=7)
    _dibujar_rect_boton(surf, _RECT_MENU, "Menú principal", _AZUL)


# -- Loop -------------------------------------------------------------------------------


class _App:
    def __init__(self, surf: pygame.Surface, hardware: Hardware) -> None:
        self.surf = surf
        self.hw = hardware
        self.estado = EstadoApp()
        self.menus = _construir_menus()
        self.calibracion = calibracion_touch.cargar_calibracion(config.CALIBRACION_TOUCH_PATH)
        if self.calibracion is None:
            logger.warning(
                "No hay calibración guardada (%s); usando coordenadas crudas del touch/mouse.",
                config.CALIBRACION_TOUCH_PATH,
            )

    # -- Navegación y sesión --------------------------------------------------------

    def ir_al_menu(self) -> None:
        self.cerrar_sesion()
        self.estado.error = ""
        self.estado.historial = [NOMBRE_MENU_PRINCIPAL]
        logger.info("Mostrando %s", NOMBRE_MENU_PRINCIPAL)

    def cerrar_sesion(self) -> None:
        estado = self.estado
        if estado.sesion is not None:
            estado.sesion.cerrar()
            estado.sesion = None
        if estado.motor is not None:
            try:
                estado.motor.cerrar()
            except Exception as error:  # noqa: BLE001 - cerrar no puede tirar la pantalla
                logger.warning("No se pudo cerrar Stockfish: %s", error)
            estado.motor = None
        estado.confirmar_rendicion = None

    def mostrar_error(self, mensaje: str) -> None:
        logger.error("%s", mensaje)
        self.cerrar_sesion()
        self.estado.error = mensaje

    def empezar_partida(self, magnus: bool) -> None:
        estado = self.estado
        try:
            fuente = self.hw.crear_fuente()
            if magnus:
                estado.motor = self.hw.crear_motor(estado.dificultad)
        except ErrorTablero as error:
            self.mostrar_error(str(error))
            return
        except FileNotFoundError:
            self.mostrar_error(
                f"No se encontró Stockfish ({config.STOCKFISH_PATH}): instalalo con 'sudo apt install stockfish'."
            )
            return
        if magnus:
            assert estado.motor is not None
            nivel = config.NIVELES_MAGNUS[estado.dificultad]
            color = estado.color_humano

            def registro_magnus() -> RegistroPartida:
                blancas, negras = nombres_pgn(color, nivel.nombre)
                return RegistroPartida(
                    config.DIRECTORIO_REGISTROS,
                    modo="vs_magnus",
                    segundos_por_jugador=None,
                    max_partidas=config.MAX_PARTIDAS_REGISTRADAS,
                    max_detalles=config.MAX_DETALLES_REGISTRADOS,
                    extras_cabecera=f"nivel={estado.dificultad} color={NOMBRES_COLOR[color]}",
                    blancas=blancas,
                    negras=negras,
                )

            estado.sesion = SesionMagnus(
                color, fuente, self.hw.pintar, estado.motor.mejor_movimiento, registro_magnus
            )
            logger.info("Partida contra Magnus (%s), jugás con %s", nivel.nombre, NOMBRES_COLOR[color])
        else:
            segundos = estado.duracion_segundos

            def registro_pvp() -> RegistroPartida:
                return RegistroPartida(
                    config.DIRECTORIO_REGISTROS,
                    modo="pvp",
                    segundos_por_jugador=segundos,
                    max_partidas=config.MAX_PARTIDAS_REGISTRADAS,
                    max_detalles=config.MAX_DETALLES_REGISTRADOS,
                )

            estado.sesion = SesionPvP(segundos, fuente, self.hw.pintar, registro_pvp)
            logger.info("Partida contra un amigo, %d minutos", segundos // 60)

    # -- Entradas -------------------------------------------------------------------

    def boton_reloj(self, nombre: str) -> None:
        sesion = self.estado.sesion
        if sesion is None or self.estado.confirmar_rendicion is not None:
            return
        logger.info("Botón del reloj: %s", nombre)
        sesion.pulsar_boton(_COLOR_DE_BOTON[nombre])

    def tocar(self, pos: tuple[float, float]) -> None:
        estado = self.estado
        vista = _vista(estado)
        if vista is None:
            self._tocar_menu(pos)
            return
        sesion = estado.sesion
        if vista in (Vista.ERROR, Vista.FIN):
            if _RECT_MENU.collidepoint(pos):
                logger.info("Input: Menú principal")
                self.ir_al_menu()
        elif vista is Vista.PREPARAR:
            if _RECT_VOLVER.collidepoint(pos):
                logger.info("Input: Volver (acomodar piezas)")
                self.cerrar_sesion()
        elif vista is Vista.CONFIRMAR_RENDICION:
            assert sesion is not None and estado.confirmar_rendicion is not None
            if _RECT_SI.collidepoint(pos):
                logger.info("Input: se rinden %s", NOMBRES_COLOR[estado.confirmar_rendicion])
                sesion.rendirse(estado.confirmar_rendicion)
                estado.confirmar_rendicion = None
            elif _RECT_NO.collidepoint(pos):
                estado.confirmar_rendicion = None
        elif vista is Vista.JUEGO_PVP:
            assert isinstance(sesion, SesionPvP)
            self._tocar_pvp(sesion, pos)
        elif vista is Vista.JUEGO_MAGNUS:
            assert isinstance(sesion, SesionMagnus)
            if _RECT_RENDIRSE_MAGNUS.collidepoint(pos):
                estado.confirmar_rendicion = sesion.color_humano

    def _tocar_pvp(self, sesion: SesionPvP, pos: tuple[float, float]) -> None:
        oferta = sesion.oferta_tablas
        for color in (chess.WHITE, chess.BLACK):
            izquierda, derecha = _rects_pvp(color)
            if oferta is not None and oferta != color:
                if izquierda.collidepoint(pos) or derecha.collidepoint(pos):
                    acepta = izquierda.collidepoint(pos)
                    logger.info("Input: %s %s las tablas", NOMBRES_COLOR[color], "acepta" if acepta else "rechaza")
                    sesion.responder_tablas(acepta)
                    return
            elif izquierda.collidepoint(pos):
                self.estado.confirmar_rendicion = color
                return
            elif derecha.collidepoint(pos) and oferta is None:
                logger.info("Input: %s ofrecen tablas", NOMBRES_COLOR[color])
                sesion.ofrecer_tablas(color)
                return

    def _tocar_menu(self, pos: tuple[float, float]) -> None:
        estado = self.estado
        pantalla = self.menus[estado.historial[-1]]
        if pantalla.permite_volver and _RECT_VOLVER.collidepoint(pos):
            logger.info("Input: Volver (desde %s)", pantalla.nombre)
            estado.historial.pop()
            return
        for boton in pantalla.botones:
            if not boton.rect.collidepoint(pos):
                continue
            logger.info("Input: %s (%s -> %s)", boton.texto, pantalla.nombre, boton.destino)
            if boton.duracion_segundos is not None:
                estado.duracion_segundos = boton.duracion_segundos
            if boton.dificultad is not None:
                estado.dificultad = boton.dificultad
            if boton.eleccion_color is not None:
                estado.color_humano = _resolver_color(boton.eleccion_color)
            if boton.destino == NOMBRE_PARTIDA:
                self.empezar_partida(magnus=pantalla.nombre == NOMBRE_SELECTOR_COLOR)
            else:
                estado.historial.append(boton.destino)
            return

    # -- Dibujo ---------------------------------------------------------------------

    def renderizar(self) -> None:
        surf, estado = self.surf, self.estado
        surf.fill(_BLANCO)
        vista = _vista(estado)
        sesion = estado.sesion
        con_pie = True
        if vista is None:
            pantalla = self.menus[estado.historial[-1]]
            pantalla.dibujar(surf, pantalla)
            volver = pantalla.permite_volver
        else:
            volver = vista is Vista.PREPARAR
            if vista is Vista.ERROR:
                _dibujar_error(surf, estado)
            elif vista is Vista.CONFIRMAR_RENDICION:
                _dibujar_confirmar(surf, estado)
            else:
                assert sesion is not None
                if vista is Vista.PREPARAR:
                    _dibujar_preparar(surf, sesion)
                elif vista is Vista.CUENTA_REGRESIVA:
                    assert isinstance(sesion, SesionPvP)
                    _dibujar_cuenta_regresiva(surf, sesion)
                elif vista is Vista.JUEGO_PVP:
                    assert isinstance(sesion, SesionPvP)
                    _dibujar_juego_pvp(surf, sesion)
                    con_pie = False
                elif vista is Vista.JUEGO_MAGNUS:
                    assert isinstance(sesion, SesionMagnus)
                    _dibujar_juego_magnus(surf, sesion)
                    con_pie = False
                else:
                    _dibujar_fin(surf, sesion)
        if con_pie:
            _texto(surf, _PIE_MAGNUS, _TAM_PIE, _GRIS, (110, config.PANTALLA_ALTO - 14))
        if volver:
            _dibujar_rect_boton(surf, _RECT_VOLVER, "‹ Volver", _AZUL, _TAM_BOTON_CHICO)
        pygame.display.flip()

    # -- Loop -----------------------------------------------------------------------

    def correr(self) -> None:
        self.renderizar()
        while True:
            hubo_eventos = False
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    return
                if evento.type == EVENTO_BOTON_RELOJ:
                    self.boton_reloj(evento.boton)
                elif evento.type == pygame.KEYDOWN and evento.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    self.boton_reloj("boton_1" if evento.key == pygame.K_LEFT else "boton_2")
                elif evento.type in (pygame.FINGERDOWN, pygame.MOUSEBUTTONDOWN):
                    if evento.type == pygame.FINGERDOWN:
                        pos = (evento.x * config.PANTALLA_ANCHO, evento.y * config.PANTALLA_ALTO)
                    else:
                        pos = evento.pos
                    if self.calibracion is not None:
                        pos = calibracion_touch.aplicar_transformacion(pos, self.calibracion)
                    self.tocar(pos)
                else:
                    continue
                hubo_eventos = True

            cambio = False
            if self.estado.sesion is not None:
                try:
                    cambio = self.estado.sesion.actualizar()
                except ErrorTablero as error:
                    self.mostrar_error(str(error))
                    cambio = True
            # Redibujar solo ante un evento o un cambio de la sesión (que avisa una vez
            # por segundo por el reloj): `flip()` en cada vuelta deja en blanco la
            # pantalla con el backend KMSDRM de la Raspberry (ver software-docs/menus.md).
            if hubo_eventos or cambio:
                self.renderizar()
            pygame.time.wait(20)

    def cerrar(self) -> None:
        self.cerrar_sesion()


def ejecutar_menus(hardware: Hardware) -> None:
    """Corre la interfaz hasta `Ctrl+C` o cerrar la ventana. Al salir, abandona la partida en curso."""
    pygame.init()
    surf = pygame.display.set_mode((config.PANTALLA_ANCHO, config.PANTALLA_ALTO))
    app = _App(surf, hardware)
    try:
        app.correr()
    except KeyboardInterrupt:
        pass
    finally:
        app.cerrar()
        pygame.quit()


# -- Notebook: tablero simulado ----------------------------------------------------------


def _hardware_simulado() -> Hardware:
    from tablero.logica.tablero_simulado import AYUDA, TableroSimulado

    tablero = TableroSimulado()

    def leer_terminal() -> None:
        print(AYUDA)
        for linea in sys.stdin:
            if linea.strip() and (error := tablero.enviar(linea)):
                print(error)

    threading.Thread(target=leer_terminal, daemon=True).start()

    def pintar(marcas) -> None:
        if marcas:
            resumen = ", ".join(f"{chess.square_name(c)}={m.name.lower()}" for c, m in sorted(marcas.items()))
            logger.info("LEDs: %s", resumen)

    def crear_fuente() -> TableroSimulado:
        tablero.reiniciar()  # una partida nueva parte de lo que hay en el tablero
        return tablero

    return Hardware(crear_fuente=crear_fuente, pintar=pintar, crear_motor=crear_motor_stockfish)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ejecutar_menus(_hardware_simulado())
