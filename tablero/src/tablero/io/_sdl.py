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
import re
import sys
from pathlib import Path

# Driver DRM del panel (overlay `piscreen`). Se busca por nombre porque el número de
# `/dev/dri/cardN` depende del orden en que el kernel carga los drivers.
_DRIVER_DRM_PANEL = "ili9486"
_INDICE_DRM_POR_DEFECTO = 1


def _indice_drm_del_panel(directorio: Path = Path("/sys/class/drm")) -> int | None:
    """Número N de `/dev/dri/cardN` cuyo driver es el del panel, o None si no aparece."""
    for card in sorted(directorio.glob("card*")):
        coincidencia = re.fullmatch(r"card(\d+)", card.name)  # saltea conectores (card0-HDMI-A-1)
        if coincidencia is None:
            continue
        driver = card / "device" / "driver"
        if driver.exists() and driver.resolve().name == _DRIVER_DRM_PANEL:
            return int(coincidencia.group(1))
    return None


def configurar_entorno_sdl() -> None:
    """Fuerza el backend KMS/DRM sin mouse, salvo que `TABLERO_PANTALLA_VENTANA=1`.

    En modo ventana, sobre Linux se fuerza además `SDL_VIDEODRIVER=wayland` (vía
    `setdefault`, así que se puede pisar seteándola antes de correr el script):
    probamos primero forzar `x11` (vía XWayland) pensando que era la opción más
    compatible, pero en niri (el compositor de Tino) da ventana completamente negra —
    niri no soporta Xwayland de forma nativa (usa `xwayland-satellite`) y su propia
    documentación marca las ventanas Xwayland como negras por defecto, sin relación
    con `pygame`. El backend `wayland` nativo de SDL2 no pasa por Xwayland y funciona
    correctamente. En otras plataformas (Windows, macOS) no se toca `SDL_VIDEODRIVER`
    en modo ventana — `wayland` no existe ahí y SDL ya elige el backend nativo
    correcto por su cuenta.

    En modo Raspberry (KMS/DRM) se fija además `SDL_KMSDRM_DEVICE_INDEX` al `cardN` del
    panel: esta Raspberry tiene dos dispositivos DRM, la GPU integrada vc4/HDMI (que sin
    monitor reporta "Cannot find any crtc or sizes") y el panel `ili9486`. Si SDL abre el
    de la vc4 no hay error, pero el panel queda en blanco sin ningún traceback (confirmado
    por Tino el 2026-08-13). El índice no es fijo: el 2026-08-13 el panel era `card1` y el
    2026-10-22, en otro arranque, `card0`, así que se busca por el nombre del driver en
    `/sys/class/drm`; si no aparece, se usa 1 y se avisa.
    """
    if os.environ.get("TABLERO_PANTALLA_VENTANA") == "1":
        if sys.platform.startswith("linux"):
            os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
        return
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    os.environ.setdefault("SDL_NOMOUSE", "1")
    if "SDL_KMSDRM_DEVICE_INDEX" not in os.environ:
        indice = _indice_drm_del_panel()
        if indice is None:
            print(
                f"Aviso: no se encontró el panel {_DRIVER_DRM_PANEL} en /sys/class/drm; "
                f"se usa /dev/dri/card{_INDICE_DRM_POR_DEFECTO}. ¿Está el overlay piscreen?",
                file=sys.stderr,
            )
            indice = _INDICE_DRM_POR_DEFECTO
        os.environ["SDL_KMSDRM_DEVICE_INDEX"] = str(indice)
