# `pyproject.toml`

Configuración del paquete `tablero`, gestionado con `uv`.

## Cambios de esta sesión

- **Fix: `readme = "README.md"` → `readme = "../README.md"`**. El `README.md` del
  proyecto vive en la raíz del repo, no dentro de `tablero/`. Con la ruta relativa a
  un archivo inexistente, cualquier `uv add`/`uv sync` fallaba al intentar buildear el
  paquete (`failed to open file .../tablero/README.md`). Era un bug preexistente, no
  relacionado con `logica/`/`motor/`, pero bloqueaba instalar `pytest`.
- **Nuevo `[dependency-groups]` con `dev = ["pytest>=9.1.1"]`**, agregado vía
  `uv add --dev pytest`. Antes no había ningún test runner instalado, a pesar de que
  ya existían archivos de test vacíos.
- **Environment markers (PEP 508) en `rpi-lgpio` y `rpi-ws281x`**:
  `; sys_platform == 'linux' and platform_machine in 'aarch64 armv7l armv6l'`. Estas
  dos dependencias hablan con hardware específico de la Raspberry Pi (GPIO real, PWM
  de Broadcom) y no tiene sentido que `uv sync` intente instalarlas ni compilarlas
  fuera de la Pi — de hecho en Windows `uv sync` fallaba al buildear la extensión en
  C de `rpi-ws281x` por falta de Microsoft Visual C++ Build Tools. Esto coincide con
  el boundary que ya documenta `CLAUDE.md`: `io/` es Pi-only, `logica/`/`motor/` son
  multiplataforma. Con el marker, en cualquier máquina que no sea Linux ARM
  (notebooks de desarrollo) `uv sync` solo instala `python-chess`, `pygame` y el
  grupo `dev` (`pytest`).
- **`pygame` quedó sin marker, a propósito** (a diferencia de `rpi-lgpio`/`rpi-ws281x`
  arriba): primer intento de este mismo fix le había puesto el mismo marker de Linux
  ARM, pero eso rompe el modo ventana de `menus.py` (`TABLERO_PANTALLA_VENTANA=1`,
  ver [`menus.md`](./menus.md)), que existe justamente para probar la UI en
  cualquier notebook sin la Raspberry. `pygame` sí tiene que instalarse en cualquier
  plataforma; lo único Pi-specific es *cómo* se instala (ver el punto siguiente).
- **`[tool.uv] no-binary-package = ["pygame"]` sacado de `pyproject.toml`**. Forzaba
  compilar `pygame` desde fuente en toda máquina (necesario en la Pi para enlazar
  contra el SDL2 del sistema con soporte KMSDRM, ver
  [`pantalla.md`](./pantalla.md#instalación-de-pygame)), pero en Windows ese build
  desde fuente requiere su propio toolchain (MSYS2/pacman) que tampoco está
  instalado, y fallaba igual que fallaba `rpi-ws281x` — mismo síntoma, otra causa.
  Como es una config global de `[tool.uv]`, no soporta un marker de plataforma como
  las dependencias de arriba. Se reemplaza por el flag `--no-binary-package pygame`
  (o la variable `UV_NO_BINARY_PACKAGE=pygame`), que se pasa solo al sincronizar en
  la Pi — ver `pantalla.md`.

## Dependencias

| Grupo | Paquete | Uso |
|---|---|---|
| `dependencies` | `python-chess>=1.999` | Shim de compatibilidad; instala el paquete real `chess` (ver [`docs/logica.md`](./logica.md), [`docs/motor.md`](./motor.md)) |
| `dependencies` | `rpi-lgpio>=0.6` | Acceso a GPIO para `io/sensores.py` (todavía no implementado) |
| `dependencies` | `rpi-ws281x>=5.0.0` | Control de LEDs WS2812B para `io/leds.py` (todavía no implementado) |
| `dependencies` | `pygame>=2.6.1` | Renderizado sobre DRM/KMS para `io/pantalla.py` (ver [`docs/pantalla.md`](./pantalla.md)), agregado vía `uv add pygame` |
| `dependency-groups.dev` | `pytest>=9.1.1` | Test runner para `tablero/tests/` |

`[project.scripts]` mapea el comando `tablero` a `tablero:main` (`main()` en
`src/tablero/__init__.py`), y el build backend es `uv_build` (nativo de `uv`, no
`setuptools`/`hatchling`).
