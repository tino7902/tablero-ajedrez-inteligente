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

## Dependencias

| Grupo | Paquete | Uso |
|---|---|---|
| `dependencies` | `python-chess>=1.999` | Shim de compatibilidad; instala el paquete real `chess` (ver [`docs/logica.md`](./logica.md), [`docs/motor.md`](./motor.md)) |
| `dependencies` | `rpi-lgpio>=0.6` | Acceso a GPIO para `io/sensores.py` (todavía no implementado) |
| `dependencies` | `rpi-ws281x>=5.0.0` | Control de LEDs WS2812B para `io/leds.py` (todavía no implementado) |
| `dependency-groups.dev` | `pytest>=9.1.1` | Test runner para `tablero/tests/` |

`[project.scripts]` mapea el comando `tablero` a `tablero:main` (`main()` en
`src/tablero/__init__.py`), y el build backend es `uv_build` (nativo de `uv`, no
`setuptools`/`hatchling`).
