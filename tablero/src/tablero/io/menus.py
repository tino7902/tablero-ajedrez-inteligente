"""Interfaz gráfica de navegación por menús (RPI LCD V3, 480x320).

Implementa los bocetos de `diseño-docs/diseño-interfaz.md`: menú principal, selectores
de tiempo/dificultad/color, y las pantallas de juego. El modo Jugador vs Jugador (PvP)
tiene reloj real: cuenta regresiva al iniciar, dos temporizadores independientes, cambio
de turno al presionar boton_1/boton_2 (ver más abajo), y mensaje de fin de partida cuando
alguno se queda sin tiempo. vs-Magnus sigue con placeholders estáticos (reloj/indicadores
fijos), salvo el color del jugador humano, ya resuelto en `selector_color`.

Cada botón tocado se loguea (`logging`) y navega a la pantalla correspondiente; hay un
botón "Volver" en todas las pantallas salvo el menú principal, que retrocede sobre un
historial de navegación (pila de nombres de pantalla).

Modo ventana (sin la Raspberry): seteando `TABLERO_PANTALLA_VENTANA=1` en el entorno,
no se fuerza el backend KMS/DRM ni se deshabilita el mouse, así que corre en una ventana
normal de escritorio — pensado para iterar el diseño visual en un notebook cualquiera:

    env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus

Sin esa variable, el comportamiento es el de siempre (piensa que corre en la Raspberry).

Los botones físicos del reloj (boton_1/boton_2) se simulan acá con las teclas ←/→ (ver
`ejecutar_menus()`) — funciona en cualquier modo, no solo en modo ventana. Este archivo no
importa `io/sensores.py` ni sabe nada de GPIO a propósito: es el punto de entrada para
probar la interfaz sin hardware. Para los botones físicos reales, correr
`io/menus_gpio.py`, que reusa este mismo diseño gráfico y loop sin modificarlos.
"""

import enum
import functools
import logging
import random
import time
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
_VERDE = (60, 180, 75)  # mismo verde que ya usa io/pantalla.py; indicador de turno activo

_TAM_TITULO = 40
_TAM_SUBTITULO = 18
_TAM_PREGUNTA = 18
_TAM_BOTON = 22
_TAM_BOTON_CHICO = 16
_TAM_INDICADOR = 14
_TAM_RELOJ = 40
_TAM_RELOJ_GRANDE = 52
_TAM_PIE = 12
_TAM_MENSAJE_FIN = 24
_TAM_CUENTA_REGRESIVA_NUMERO = 90

_SUBTITULO_MAGNUS = "El tablero de ajedrez inteligente"
_PIE_MAGNUS = "Desarrollado por CDR-FPUNA 2026"

_TEXTOS_CUENTA_REGRESIVA = ("3", "2", "1", "¡Partida iniciada!")
_DURACION_PASO_CUENTA_REGRESIVA = 1.0  # segundos por paso

_RECT_VOLVER = pygame.Rect(10, 10, 90, 32)

NOMBRE_MENU_PRINCIPAL = "menu_principal"
NOMBRE_SELECTOR_TIEMPO = "selector_tiempo"
NOMBRE_SELECTOR_DIFICULTAD = "selector_dificultad"
NOMBRE_SELECTOR_COLOR = "selector_color"
NOMBRE_CUENTA_REGRESIVA = "cuenta_regresiva"
NOMBRE_JUEGO_PVP = "juego_pvp"
NOMBRE_JUEGO_VS_MAGNUS = "juego_vs_magnus"

EVENTO_BOTON_RELOJ = pygame.USEREVENT + 1  # público: lo usa io/menus_gpio.py

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
    duracion_segundos: int | None = None


@dataclass(frozen=True)
class Pantalla:
    nombre: str
    dibujar: Callable[[pygame.Surface, "Pantalla"], None]
    botones: list[Boton] = field(default_factory=list)
    permite_volver: bool = True


@dataclass
class EstadoPartida:
    """Estado que necesitan las pantallas de juego más allá de la navegación entre ellas.

    `color_humano` es para vs. Magnus (se resuelve al elegir "Blancas"/"Aleatorio"/"Negras"
    en `selector_color`). El resto es el reloj PvP: `turno_blancas` indica de quién es el
    turno mientras se juega, y queda "congelado" en el lado que se quedó sin tiempo una vez
    `tiempo_agotado=True` (no se vuelve a alternar) — así identifica a la vez "de quién es
    el turno" y "quién perdió por tiempo" sin necesitar un campo separado.
    """

    color_humano: chess.Color | None = None
    tiempo_restante_blancas: float = 0.0
    tiempo_restante_negras: float = 0.0
    turno_blancas: bool = True
    reloj_corriendo: bool = False
    tiempo_agotado: bool = False
    entrada_pantalla_ts: float = 0.0


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


def _dibujar_indicador(surf: pygame.Surface, centro: tuple[int, int], texto_str: str, color: tuple) -> None:
    texto = _fuente(_TAM_INDICADOR).render(texto_str, True, color)
    rect = texto.get_rect(center=centro).inflate(16, 8)
    pygame.draw.rect(surf, color, rect, width=2, border_radius=6)
    surf.blit(texto, texto.get_rect(center=centro))


def _formatear_tiempo(segundos: float) -> str:
    total = max(0, int(segundos))
    minutos, segs = divmod(total, 60)
    return f"{minutos:02d}:{segs:02d}"


def _dibujar_reloj(
    surf: pygame.Surface, centro: tuple[int, int], size: tuple[int, int], tamano_fuente: int, segundos_restantes: float
) -> None:
    rect = pygame.Rect(0, 0, *size)
    rect.center = centro
    pygame.draw.rect(surf, _AZUL, rect, width=3, border_radius=12)
    texto = _fuente(tamano_fuente).render(_formatear_tiempo(segundos_restantes), True, _NEGRO)
    surf.blit(texto, texto.get_rect(center=rect.center))


def _dibujar_juego_pvp(surf: pygame.Surface, pantalla: Pantalla, estado: EstadoPartida) -> None:
    surf.fill(_BLANCO)
    if estado.tiempo_agotado:
        color_perdedor = "Blancas" if estado.turno_blancas else "Negras"
        color_ganador = "Negras" if estado.turno_blancas else "Blancas"
        for y, linea in ((55, f"¡{color_perdedor} se quedó sin tiempo!"), (85, f"Gana {color_ganador}")):
            texto = _fuente(_TAM_MENSAJE_FIN).render(linea, True, _ROJO)
            surf.blit(texto, texto.get_rect(center=(config.PANTALLA_ANCHO // 2, y)))
    else:
        for x_centro, encabezado, es_turno in (
            (130, "Blancas", estado.turno_blancas),
            (350, "Negras", not estado.turno_blancas),
        ):
            texto = _fuente(_TAM_PREGUNTA).render(encabezado, True, _NEGRO)
            surf.blit(texto, texto.get_rect(center=(x_centro, 48)))
            if es_turno:
                _dibujar_indicador(surf, (x_centro, 80), "¡Es tu turno!", _VERDE)

    _dibujar_reloj(surf, (130, 168), (140, 70), _TAM_RELOJ, estado.tiempo_restante_blancas)
    _dibujar_reloj(surf, (350, 168), (140, 70), _TAM_RELOJ, estado.tiempo_restante_negras)
    for boton in pantalla.botones:
        _dibujar_boton(surf, boton, _ROJO, _TAM_BOTON_CHICO)


def _dibujar_juego_vs_magnus(surf: pygame.Surface, pantalla: Pantalla, estado: EstadoPartida) -> None:
    surf.fill(_BLANCO)
    centro_x = config.PANTALLA_ANCHO // 2
    texto = _fuente(_TAM_PREGUNTA).render(f"¡Sos {_nombre_color(estado.color_humano)}!", True, _NEGRO)
    surf.blit(texto, texto.get_rect(center=(centro_x, 40)))
    _dibujar_indicador(surf, (centro_x, 80), "¡Es tu turno!", _GRIS)
    _dibujar_indicador(surf, (centro_x, 115), "¡Te quedaste sin tiempo!", _GRIS)
    _dibujar_reloj(surf, (centro_x, 190), (180, 90), _TAM_RELOJ_GRANDE, 4 * 60 + 53)
    for boton in pantalla.botones:
        _dibujar_boton(surf, boton, _ROJO, _TAM_BOTON_CHICO)


def _dibujar_cuenta_regresiva(surf: pygame.Surface, pantalla: Pantalla, estado: EstadoPartida) -> None:
    surf.fill(_BLANCO)
    elapsed = time.monotonic() - estado.entrada_pantalla_ts
    paso = min(int(elapsed / _DURACION_PASO_CUENTA_REGRESIVA), len(_TEXTOS_CUENTA_REGRESIVA) - 1)
    texto_str = _TEXTOS_CUENTA_REGRESIVA[paso]
    tamano = _TAM_CUENTA_REGRESIVA_NUMERO if texto_str.isdigit() else _TAM_TITULO
    texto = _fuente(tamano).render(texto_str, True, _AZUL)
    surf.blit(texto, texto.get_rect(center=(config.PANTALLA_ANCHO // 2, config.PANTALLA_ALTO // 2)))


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
            Boton("3 minutos", rects[0], NOMBRE_CUENTA_REGRESIVA, duracion_segundos=3 * 60),
            Boton("5 minutos", rects[1], NOMBRE_CUENTA_REGRESIVA, duracion_segundos=5 * 60),
            Boton("10 minutos", rects[2], NOMBRE_CUENTA_REGRESIVA, duracion_segundos=10 * 60),
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

    pantalla_cuenta_regresiva = Pantalla(
        nombre=NOMBRE_CUENTA_REGRESIVA,
        dibujar=functools.partial(_dibujar_cuenta_regresiva, estado=estado),
        botones=[],
        permite_volver=False,
    )

    pantalla_pvp = Pantalla(
        nombre=NOMBRE_JUEGO_PVP,
        dibujar=functools.partial(_dibujar_juego_pvp, estado=estado),
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
        pantalla_cuenta_regresiva,
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


def _procesar_boton_reloj(estado: EstadoPartida, pantalla_nombre: str, boton_nombre: str) -> None:
    if pantalla_nombre != NOMBRE_JUEGO_PVP or not estado.reloj_corriendo:
        return
    if boton_nombre == "boton_1" and estado.turno_blancas:
        estado.turno_blancas = False
        logger.info("boton_1 presionado: pasa el turno a negras")
    elif boton_nombre == "boton_2" and not estado.turno_blancas:
        estado.turno_blancas = True
        logger.info("boton_2 presionado: pasa el turno a blancas")


def ejecutar_menus() -> None:
    """Corre el loop de navegación entre pantallas hasta `Ctrl+C`.

    Los botones del reloj se pueden simular con las teclas ← (boton_1/blancas) y →
    (boton_2/negras) — funciona siempre, no solo en modo ventana (inofensivo en la
    Raspberry, que normalmente no tiene teclado conectado). Para manejar los botones
    físicos reales (GPIO) en vez de o además del teclado, correr `io/menus_gpio.py`, que
    llama a esta misma función después de configurar GPIO — ver ese archivo.
    """
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
    estado.entrada_pantalla_ts = time.monotonic()
    logger.info("Mostrando %s", historial[-1])
    _renderizar(surf, pantallas[historial[-1]])

    def _navegar(destino: str) -> None:
        nonlocal historial
        if destino == NOMBRE_MENU_PRINCIPAL:
            historial = [NOMBRE_MENU_PRINCIPAL]
        else:
            historial.append(destino)
        estado.entrada_pantalla_ts = time.monotonic()
        logger.info("Mostrando %s", historial[-1])

    ultimo_tick = time.monotonic()

    try:
        while True:
            ahora = time.monotonic()
            dt = ahora - ultimo_tick
            ultimo_tick = ahora

            eventos = pygame.event.get()
            for evento in eventos:
                pantalla_actual = pantallas[historial[-1]]

                if evento.type == EVENTO_BOTON_RELOJ:
                    _procesar_boton_reloj(estado, pantalla_actual.nombre, evento.boton)
                    continue
                if evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_LEFT:
                        _procesar_boton_reloj(estado, pantalla_actual.nombre, "boton_1")
                    elif evento.key == pygame.K_RIGHT:
                        _procesar_boton_reloj(estado, pantalla_actual.nombre, "boton_2")
                    continue

                pos = None
                if evento.type == pygame.FINGERDOWN:
                    pos = (evento.x * config.PANTALLA_ANCHO, evento.y * config.PANTALLA_ALTO)
                elif evento.type == pygame.MOUSEBUTTONDOWN:
                    pos = evento.pos

                if pos is None:
                    continue

                if coefs_calibracion is not None:
                    pos = calibracion_touch.aplicar_transformacion(pos, coefs_calibracion)

                if pantalla_actual.permite_volver and _RECT_VOLVER.collidepoint(pos):
                    logger.info("Input: Volver (desde %s)", pantalla_actual.nombre)
                    historial.pop()
                    estado.entrada_pantalla_ts = time.monotonic()
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
                    if boton.duracion_segundos is not None:
                        estado.tiempo_restante_blancas = float(boton.duracion_segundos)
                        estado.tiempo_restante_negras = float(boton.duracion_segundos)
                        logger.info("Duración elegida: %d segundos por jugador", boton.duracion_segundos)
                    _navegar(boton.destino)
                    break

            pantalla_actual = pantallas[historial[-1]]

            if pantalla_actual.nombre == NOMBRE_CUENTA_REGRESIVA:
                duracion_total = len(_TEXTOS_CUENTA_REGRESIVA) * _DURACION_PASO_CUENTA_REGRESIVA
                if ahora - estado.entrada_pantalla_ts >= duracion_total:
                    estado.turno_blancas = True
                    estado.reloj_corriendo = True
                    estado.tiempo_agotado = False
                    _navegar(NOMBRE_JUEGO_PVP)

            reloj_tick = False
            if pantalla_actual.nombre == NOMBRE_JUEGO_PVP and estado.reloj_corriendo:
                reloj_tick = True
                if estado.turno_blancas:
                    estado.tiempo_restante_blancas = max(0.0, estado.tiempo_restante_blancas - dt)
                    agotado = estado.tiempo_restante_blancas <= 0
                else:
                    estado.tiempo_restante_negras = max(0.0, estado.tiempo_restante_negras - dt)
                    agotado = estado.tiempo_restante_negras <= 0
                if agotado:
                    estado.reloj_corriendo = False
                    estado.tiempo_agotado = True
                    logger.info(
                        "%s se quedó sin tiempo, gana %s",
                        "Blancas" if estado.turno_blancas else "Negras",
                        "negras" if estado.turno_blancas else "blancas",
                    )

            # Solo se redibuja cada frame en las pantallas "vivas" (cuenta regresiva, reloj
            # corriendo) — el resto vuelve al comportamiento original de redibujar solo ante
            # un evento real. Llamar a pygame.display.flip() en cada vuelta del loop (~50/s)
            # sin necesidad rompe el backend KMSDRM de la Raspberry (pantalla queda en blanco;
            # no pasa con el backend de escritorio/ventana).
            pantalla_viva = pantalla_actual.nombre == NOMBRE_CUENTA_REGRESIVA or reloj_tick
            if eventos or pantalla_viva:
                _renderizar(surf, pantallas[historial[-1]])
            pygame.time.wait(20)
    except KeyboardInterrupt:
        pygame.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ejecutar_menus()
