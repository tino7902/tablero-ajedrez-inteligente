"""Control de la pantalla táctil RPI LCD V3 (480x320, ILI9486 + touch XPT2046).

Requiere el overlay de kernel `piscreen` en modo DRM activado en la Raspberry
(ver docs/pantalla.md). El panel aparece como un dispositivo DRM/KMS, así que
se le indica a SDL que use ese backend en vez de abrir una ventana.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
os.environ.setdefault("SDL_NOMOUSE", "1")

import pygame

from tablero import config

_NEGRO = (0, 0, 0)
_BLANCO = (255, 255, 255)


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


if __name__ == "__main__":
    mostrar_texto("Hola tablero")
    try:
        while True:
            pygame.time.wait(1000)
    except KeyboardInterrupt:
        pygame.quit()
