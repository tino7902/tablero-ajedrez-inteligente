"""Interfaz gráfica de navegación por menús (RPI LCD V3, 480x320).

Implementa los bocetos de `diseño-docs/diseño-interfaz.md`: menú principal, selectores
de tiempo/dificultad/color, y las pantallas de juego (mayormente estáticas por ahora — el
reloj y los indicadores de turno son valores fijos de ejemplo, sin lógica real de partida
detrás; eso se conecta más adelante con `logica/estado_tablero.py`. La única pieza de
lógica real ya conectada es el color del jugador humano vs. Magnus, resuelto en
`selector_color` y reflejado en `juego_vs_magnus`).

Cada botón tocado se loguea (`logging`) y navega a la pantalla correspondiente; hay un
botón "Volver" en todas las pantallas salvo el menú principal, que retrocede sobre un
historial de navegación (pila de nombres de pantalla).

Modo ventana (sin la Raspberry): seteando `TABLERO_PANTALLA_VENTANA=1` en el entorno,
no se fuerza el backend KMS/DRM ni se deshabilita el mouse, así que corre en una ventana
normal de escritorio — pensado para iterar el diseño visual en un notebook cualquiera:

    env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus

Sin esa variable, el comportamiento es el de siempre (piensa que corre en la Raspberry).
"""

import enum
import functools
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field

from tablero.io._sdl import configurar_entorno_sdl

configurar_entorno_sdl()

import chess
import pygame

from tablero import config
from tablero.io import calibracion_touch

logger = logging.getLogger(__name__)

_BLANCO = (255, 255, 255)
_NEGRO = (0, 0, 0)
_AZUL = (0, 0, 205)
_ROJO = (200, 30, 30)
_GRIS = (140, 140, 140)

_TAM_TITULO = 40
_TAM_SUBTITULO = 18
_TAM_PREGUNTA = 18
_TAM_BOTON = 22
_TAM_BOTON_CHICO = 16
_TAM_INDICADOR = 14
_TAM_RELOJ = 40
_TAM_RELOJ_GRANDE = 52
_TAM_PIE = 12

_SUBTITULO_MAGNUS = "El tablero de ajedrez inteligente"
_PIE_MAGNUS = "Desarrollado por CDR-FPUNA 2026"

_RECT_VOLVER = pygame.Rect(10, 10, 90, 32)

NOMBRE_MENU_PRINCIPAL = "menu_principal"
NOMBRE_SELECTOR_TIEMPO = "selector_tiempo"
NOMBRE_SELECTOR_DIFICULTAD = "selector_dificultad"
NOMBRE_SELECTOR_COLOR = "selector_color"
NOMBRE_JUEGO_PVP = "juego_pvp"
NOMBRE_JUEGO_VS_MAGNUS = "juego_vs_magnus"

_RECT_RENDIRSE_PVP_BLANCAS = pygame.Rect(0, 0, 110, 34)
_RECT_RENDIRSE_PVP_BLANCAS.center = (130, 232)
_RECT_RENDIRSE_PVP_NEGRAS = pygame.Rect(0, 0, 110, 34)
_RECT_RENDIRSE_PVP_NEGRAS.center = (350, 232)
_RECT_RENDIRSE_VS_MAGNUS = pygame.Rect(0, 0, 130, 36)
_RECT_RENDIRSE_VS_MAGNUS.center = (config.PANTALLA_ANCHO // 2, 265)


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


@dataclass(frozen=True)
class Pantalla:
    nombre: str
    dibujar: Callable[[pygame.Surface, "Pantalla"], None]
    botones: list[Boton] = field(default_factory=list)
    permite_volver: bool = True


@dataclass
class EstadoPartida:
    """Estado que necesitan las pantallas de juego más allá de la navegación entre ellas.

    Por ahora solo el color del jugador humano vs. Magnus (se resuelve al elegir "Blancas"/
    "Aleatorio"/"Negras" en `selector_color`); crece cuando se conecte `logica/estado_tablero.py`.
    """

    color_humano: chess.Color | None = None


def _resolver_color(eleccion: EleccionColor) -> chess.Color:
    if eleccion is EleccionColor.BLANCAS:
        return chess.WHITE
    if eleccion is EleccionColor.NEGRAS:
        return chess.BLACK
    return random.choice([chess.WHITE, chess.BLACK])


def _nombre_color(color: chess.Color) -> str:
    return "blancas" if color == chess.WHITE else "negras"


@functools.lru_cache(maxsize=None)
def _fuente(tamano: int) -> pygame.font.Font:
    return pygame.font.Font(None, tamano)


def _fila_de_botones(cantidad: int, y: int, alto: int = 80, gap: int = 20) -> list[pygame.Rect]:
    """Centra `cantidad` rects del mismo tamaño en una fila horizontal, a la altura `y`."""
    margen = 30
    ancho = (config.PANTALLA_ANCHO - 2 * margen - gap * (cantidad - 1)) // cantidad
    ancho_total = ancho * cantidad + gap * (cantidad - 1)
    x0 = (config.PANTALLA_ANCHO - ancho_total) // 2
    return [pygame.Rect(x0 + i * (ancho + gap), y, ancho, alto) for i in range(cantidad)]


def _dibujar_boton(surf: pygame.Surface, boton: Boton, color: tuple, tamano_fuente: int) -> None:
    pygame.draw.rect(surf, color, boton.rect, width=3, border_radius=10)
    texto = _fuente(tamano_fuente).render(boton.texto, True, color)
    surf.blit(texto, texto.get_rect(center=boton.rect.center))


def _dibujar_pantalla_seleccion(
    surf: pygame.Surface, pantalla: Pantalla, *, titulo: str, subtitulo: str, pregunta: str
) -> None:
    surf.fill(_BLANCO)
    texto = _fuente(_TAM_TITULO).render(titulo, True, _AZUL)
    surf.blit(texto, texto.get_rect(center=(config.PANTALLA_ANCHO // 2, 45)))
    texto = _fuente(_TAM_SUBTITULO).render(subtitulo, True, _AZUL)
    surf.blit(texto, texto.get_rect(center=(config.PANTALLA_ANCHO // 2, 78)))
    texto = _fuente(_TAM_PREGUNTA).render(pregunta, True, _NEGRO)
    surf.blit(texto, texto.get_rect(center=(config.PANTALLA_ANCHO // 2, 105)))
    for boton in pantalla.botones:
        _dibujar_boton(surf, boton, _AZUL, _TAM_BOTON)


def _dibujar_indicador_gris(surf: pygame.Surface, centro: tuple[int, int], texto_str: str) -> None:
    texto = _fuente(_TAM_INDICADOR).render(texto_str, True, _GRIS)
    rect = texto.get_rect(center=centro).inflate(16, 8)
    pygame.draw.rect(surf, _GRIS, rect, width=2, border_radius=6)
    surf.blit(texto, texto.get_rect(center=centro))


def _dibujar_reloj(surf: pygame.Surface, centro: tuple[int, int], size: tuple[int, int], tamano_fuente: int) -> None:
    rect = pygame.Rect(0, 0, *size)
    rect.center = centro
    pygame.draw.rect(surf, _AZUL, rect, width=3, border_radius=12)
    texto = _fuente(tamano_fuente).render("04:53", True, _NEGRO)
    surf.blit(texto, texto.get_rect(center=rect.center))


def _dibujar_juego_pvp(surf: pygame.Surface, pantalla: Pantalla) -> None:
    surf.fill(_BLANCO)
    for x_centro, encabezado in ((130, "Blancas"), (350, "Negras")):
        texto = _fuente(_TAM_PREGUNTA).render(encabezado, True, _NEGRO)
        surf.blit(texto, texto.get_rect(center=(x_centro, 48)))
        _dibujar_indicador_gris(surf, (x_centro, 80), "¡Es tu turno!")
        _dibujar_indicador_gris(surf, (x_centro, 110), "¡Te quedaste sin tiempo!")
        _dibujar_reloj(surf, (x_centro, 168), (140, 70), _TAM_RELOJ)
    for boton in pantalla.botones:
        _dibujar_boton(surf, boton, _ROJO, _TAM_BOTON_CHICO)


def _dibujar_juego_vs_magnus(surf: pygame.Surface, pantalla: Pantalla, estado: EstadoPartida) -> None:
    surf.fill(_BLANCO)
    centro_x = config.PANTALLA_ANCHO // 2
    texto = _fuente(_TAM_PREGUNTA).render(f"¡Sos {_nombre_color(estado.color_humano)}!", True, _NEGRO)
    surf.blit(texto, texto.get_rect(center=(centro_x, 40)))
    _dibujar_indicador_gris(surf, (centro_x, 80), "¡Es tu turno!")
    _dibujar_indicador_gris(surf, (centro_x, 115), "¡Te quedaste sin tiempo!")
    _dibujar_reloj(surf, (centro_x, 190), (180, 90), _TAM_RELOJ_GRANDE)
    for boton in pantalla.botones:
        _dibujar_boton(surf, boton, _ROJO, _TAM_BOTON_CHICO)


def _construir_pantallas(estado: EstadoPartida) -> dict[str, Pantalla]:
    rects = _fila_de_botones(2, y=150)
    pantalla_principal = Pantalla(
        nombre=NOMBRE_MENU_PRINCIPAL,
        dibujar=functools.partial(
            _dibujar_pantalla_seleccion,
            titulo="Magnus",
            subtitulo=_SUBTITULO_MAGNUS,
            pregunta="¿Quién será tu oponente?",
        ),
        botones=[
            Boton("Jugar contra un Amigo", rects[0], NOMBRE_SELECTOR_TIEMPO),
            Boton("Jugar contra Magnus", rects[1], NOMBRE_SELECTOR_DIFICULTAD),
        ],
        permite_volver=False,
    )

    rects = _fila_de_botones(3, y=150)
    pantalla_tiempo = Pantalla(
        nombre=NOMBRE_SELECTOR_TIEMPO,
        dibujar=functools.partial(
            _dibujar_pantalla_seleccion,
            titulo="Magnus",
            subtitulo=_SUBTITULO_MAGNUS,
            pregunta="¿Cuánto va a durar tu partida?",
        ),
        botones=[
            Boton("3 minutos", rects[0], NOMBRE_JUEGO_PVP),
            Boton("5 minutos", rects[1], NOMBRE_JUEGO_PVP),
            Boton("10 minutos", rects[2], NOMBRE_JUEGO_PVP),
        ],
    )

    rects = _fila_de_botones(3, y=150)
    pantalla_dificultad = Pantalla(
        nombre=NOMBRE_SELECTOR_DIFICULTAD,
        dibujar=functools.partial(
            _dibujar_pantalla_seleccion,
            titulo="Magnus",
            subtitulo=_SUBTITULO_MAGNUS,
            pregunta="¿Qué nivel de desafío estás buscando?",
        ),
        botones=[
            Boton("Fácil", rects[0], NOMBRE_SELECTOR_COLOR),
            Boton("Medio", rects[1], NOMBRE_SELECTOR_COLOR),
            Boton("Difícil", rects[2], NOMBRE_SELECTOR_COLOR),
        ],
    )

    rects = _fila_de_botones(3, y=150)
    pantalla_color = Pantalla(
        nombre=NOMBRE_SELECTOR_COLOR,
        dibujar=functools.partial(
            _dibujar_pantalla_seleccion,
            titulo="Magnus",
            subtitulo=_SUBTITULO_MAGNUS,
            pregunta="¿Qué color quieres ser?",
        ),
        botones=[
            Boton("Blancas", rects[0], NOMBRE_JUEGO_VS_MAGNUS, EleccionColor.BLANCAS),
            Boton("Aleatorio", rects[1], NOMBRE_JUEGO_VS_MAGNUS, EleccionColor.ALEATORIO),
            Boton("Negras", rects[2], NOMBRE_JUEGO_VS_MAGNUS, EleccionColor.NEGRAS),
        ],
    )

    pantalla_pvp = Pantalla(
        nombre=NOMBRE_JUEGO_PVP,
        dibujar=_dibujar_juego_pvp,
        botones=[
            Boton("¿Rendirse?", _RECT_RENDIRSE_PVP_BLANCAS, NOMBRE_MENU_PRINCIPAL),
            Boton("¿Rendirse?", _RECT_RENDIRSE_PVP_NEGRAS, NOMBRE_MENU_PRINCIPAL),
        ],
    )

    pantalla_vs_magnus = Pantalla(
        nombre=NOMBRE_JUEGO_VS_MAGNUS,
        dibujar=functools.partial(_dibujar_juego_vs_magnus, estado=estado),
        botones=[Boton("¿Rendirse?", _RECT_RENDIRSE_VS_MAGNUS, NOMBRE_MENU_PRINCIPAL)],
    )

    pantallas = [
        pantalla_principal,
        pantalla_tiempo,
        pantalla_dificultad,
        pantalla_color,
        pantalla_pvp,
        pantalla_vs_magnus,
    ]
    return {p.nombre: p for p in pantallas}


def _renderizar(surf: pygame.Surface, pantalla: Pantalla) -> None:
    pantalla.dibujar(surf, pantalla)

    texto_pie = _fuente(_TAM_PIE).render(_PIE_MAGNUS, True, _GRIS)
    surf.blit(texto_pie, (10, config.PANTALLA_ALTO - 22))

    if pantalla.permite_volver:
        pygame.draw.rect(surf, _AZUL, _RECT_VOLVER, width=2, border_radius=6)
        texto_volver = _fuente(_TAM_BOTON_CHICO).render("‹ Volver", True, _AZUL)
        surf.blit(texto_volver, texto_volver.get_rect(center=_RECT_VOLVER.center))

    pygame.display.flip()


def ejecutar_menus() -> None:
    """Corre el loop de navegación entre pantallas hasta `Ctrl+C`."""
    pygame.init()
    surf = pygame.display.set_mode((config.PANTALLA_ANCHO, config.PANTALLA_ALTO))
    estado = EstadoPartida()
    pantallas = _construir_pantallas(estado)

    coefs_calibracion = calibracion_touch.cargar_calibracion(config.CALIBRACION_TOUCH_PATH)
    if coefs_calibracion is None:
        logger.warning(
            "No hay calibración guardada (%s); usando coordenadas crudas del touch/mouse.",
            config.CALIBRACION_TOUCH_PATH,
        )

    historial = [NOMBRE_MENU_PRINCIPAL]
    _renderizar(surf, pantallas[historial[-1]])
    logger.info("Mostrando %s", historial[-1])

    try:
        while True:
            for evento in pygame.event.get():
                pos = None
                if evento.type == pygame.FINGERDOWN:
                    pos = (evento.x * config.PANTALLA_ANCHO, evento.y * config.PANTALLA_ALTO)
                elif evento.type == pygame.MOUSEBUTTONDOWN:
                    pos = evento.pos

                if pos is None:
                    continue

                if coefs_calibracion is not None:
                    pos = calibracion_touch.aplicar_transformacion(pos, coefs_calibracion)

                pantalla_actual = pantallas[historial[-1]]

                if pantalla_actual.permite_volver and _RECT_VOLVER.collidepoint(pos):
                    logger.info("Input: Volver (desde %s)", pantalla_actual.nombre)
                    historial.pop()
                    _renderizar(surf, pantallas[historial[-1]])
                    logger.info("Mostrando %s", historial[-1])
                    continue

                for boton in pantalla_actual.botones:
                    if not boton.rect.collidepoint(pos):
                        continue
                    logger.info(
                        "Input: %s (%s -> %s)", boton.texto, pantalla_actual.nombre, boton.destino
                    )
                    if boton.eleccion_color is not None:
                        estado.color_humano = _resolver_color(boton.eleccion_color)
                        logger.info(
                            "Color asignado: jugador humano %s, máquina %s",
                            _nombre_color(estado.color_humano),
                            _nombre_color(not estado.color_humano),
                        )
                    if boton.destino == NOMBRE_MENU_PRINCIPAL:
                        historial = [NOMBRE_MENU_PRINCIPAL]
                    else:
                        historial.append(boton.destino)
                    _renderizar(surf, pantallas[historial[-1]])
                    logger.info("Mostrando %s", historial[-1])
                    break

            pygame.time.wait(20)
    except KeyboardInterrupt:
        pygame.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ejecutar_menus()
