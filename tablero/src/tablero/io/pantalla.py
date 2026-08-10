"""Control de la pantalla táctil RPI LCD V3 (480x320, ILI9486 + touch XPT2046).

Requiere el overlay de kernel `piscreen` en modo DRM activado en la Raspberry
(ver docs/pantalla.md). El panel aparece como un dispositivo DRM/KMS, así que
se le indica a SDL que use ese backend en vez de abrir una ventana.
"""

import logging
import os

os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
os.environ.setdefault("SDL_NOMOUSE", "1")

import pygame

from tablero import config

logger = logging.getLogger(__name__)

_NEGRO = (0, 0, 0)
_BLANCO = (255, 255, 255)
_GRIS = (80, 80, 80)
_VERDE = (60, 180, 75)


def mostrar_texto(texto: str) -> None:
    """Dibuja `texto` centrado en la pantalla, sobre fondo negro."""
    pygame.init()
    pantalla = pygame.display.set_mode((config.PANTALLA_ANCHO, config.PANTALLA_ALTO))
    fuente = pygame.font.Font(None, config.PANTALLA_TAMANO_FUENTE)

    pantalla.fill(_NEGRO)
    superficie_texto = fuente.render(texto, True, _BLANCO)
    rect_texto = superficie_texto.get_rect(center=pantalla.get_rect().center)
    pantalla.blit(superficie_texto, rect_texto)
    pygame.display.flip()


def _dibujar_boton(pantalla, rect, texto, fuente, color) -> None:
    pantalla.fill(_NEGRO)
    pygame.draw.rect(pantalla, color, rect, border_radius=8)
    superficie_texto = fuente.render(texto, True, _BLANCO)
    pantalla.blit(superficie_texto, superficie_texto.get_rect(center=rect.center))
    pygame.display.flip()


def probar_boton() -> None:
    """Dibuja un botón táctil y loguea cada evento de toque que recibe.

    Test manual para validar que el touch XPT2046 llega a pygame antes de
    construir una UI real sobre `logica/estado_tablero.py`. No hace debounce
    ni filtra eventos repetidos a propósito: el objetivo es ver en los logs
    exactamente qué manda el hardware (FINGERDOWN vs. MOUSEBUTTONDOWN,
    cuántos eventos por toque físico, coordenadas reportadas).
    """
    pygame.init()
    pantalla = pygame.display.set_mode((config.PANTALLA_ANCHO, config.PANTALLA_ALTO))
    fuente = pygame.font.Font(None, config.PANTALLA_TAMANO_FUENTE)

    rect_boton = pygame.Rect(0, 0, 200, 80)
    rect_boton.center = pantalla.get_rect().center

    contador = 0
    _dibujar_boton(pantalla, rect_boton, "Tocame", fuente, _GRIS)
    logger.info("Esperando toques en el botón (Ctrl+C para salir)...")

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

                logger.info("Evento %s en %s", pygame.event.event_name(evento.type), pos)
                if rect_boton.collidepoint(pos):
                    contador += 1
                    logger.info("Botón presionado (toque #%d)", contador)
                    _dibujar_boton(pantalla, rect_boton, f"Toques: {contador}", fuente, _VERDE)

            pygame.time.wait(20)
    except KeyboardInterrupt:
        pygame.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    probar_boton()
