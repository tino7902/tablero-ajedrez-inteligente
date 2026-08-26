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
- **Environment markers (PEP 508) en `pygame`, `rpi-lgpio` y `rpi-ws281x`**:
  `; sys_platform == 'linux' and platform_machine in 'aarch64 armv7l armv6l'`. Estas
  tres dependencias hablan con hardware específico de la Raspberry Pi (GPIO real,
  DRM-KMS, PWM de Broadcom) y no tiene sentido que `uv sync` intente instalarlas ni
  compilarlas fuera de la Pi — de hecho en Windows `uv sync` fallaba al buildear la
  extensión en C de `rpi-ws281x` por falta de Microsoft Visual C++ Build Tools. Esto
  coincide con el boundary que ya documenta `CLAUDE.md`: `io/` es Pi-only,
  `logica/`/`motor/` son multiplataforma. Con el marker, en cualquier máquina que no
  sea Linux ARM (notebooks de desarrollo) `uv sync` solo instala `python-chess` y el
  grupo `dev` (`pytest`), dejando `logica/`/`motor/` testeables sin hardware ni
  toolchain de compilación.

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
