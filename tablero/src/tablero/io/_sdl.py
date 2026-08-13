"""Configuración del backend de SDL, compartida por todo `io/` que use `pygame`.

Debe llamarse a `configurar_entorno_sdl()` ANTES de `import pygame` en cualquier módulo
de `io/`, porque SDL lee estas variables de entorno una sola vez al inicializar el video.
Vive en un módulo aparte (en vez de duplicar las mismas dos líneas en cada archivo) porque
duplicarlo llevó a un bug real: como los módulos de `io/` se importan entre sí (`menus.py`
importa `calibracion_touch.py`), alcanza con que UNO de ellos siga forzando `kmsdrm`
incondicionalmente para pisarle el modo ventana a todos los demás, sin importar lo que
haga cada uno por su cuenta.
"""

import os


def configurar_entorno_sdl() -> None:
    """Fuerza el backend KMS/DRM sin mouse, salvo que `TABLERO_PANTALLA_VENTANA=1`.

    En modo ventana se fuerza además `SDL_VIDEODRIVER=wayland` (vía `setdefault`, así que
    se puede pisar seteándola antes de correr el script): probamos primero forzar `x11`
    (vía XWayland) pensando que era la opción más compatible, pero en niri (el compositor
    de Tino) da ventana completamente negra — niri no soporta Xwayland de forma nativa
    (usa `xwayland-satellite`) y su propia documentación marca las ventanas Xwayland como
    negras por defecto, sin relación con `pygame`. El backend `wayland` nativo de SDL2 no
    pasa por Xwayland y funciona correctamente.
    """
    if os.environ.get("TABLERO_PANTALLA_VENTANA") == "1":
        os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
        return
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    os.environ.setdefault("SDL_NOMOUSE", "1")
