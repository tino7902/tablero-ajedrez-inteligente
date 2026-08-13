# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Tablero de ajedrez físico con sensores por casilla (74HC165) y LEDs (WS2812B), controlado
íntegramente por una Raspberry Pi 3B. Valida movimientos y mantiene el estado de la partida
usando `python-chess`, y puede jugar contra Stockfish en modo vs-máquina. Todo corre en un único
dispositivo, sin hardware ni proceso adicional.

**Current state**: early-stage but with the first vertical slices implemented. Done:
`config.py` (Stockfish + pantalla config), `logica/estado_tablero.py` (wraps `chess.Board`,
tested in `tests/test_logica.py`), `logica/eventos.py` (translates sensor occupancy diffs into
`chess.Move`, state machine for illegal-move correction, tested in `tests/test_eventos.py` — v1
only, captures/castling/en-passant explicitly detected and rejected as unsupported rather than
applied, see `software-docs/eventos.md`), `motor/stockfish.py` (UCI integration via
`SimpleEngine`, tested in `tests/test_motor.py`), `io/pantalla.py` (static text on the RPI LCD V3
touchscreen via `pygame`/DRM-KMS), `io/calibracion_touch.py` (affine least-squares calibration
for the XPT2046 touch controller, no hardware test yet — see `software-docs/pantalla.md`),
`io/menus.py` (navigable menu screens matching `diseño-docs/diseño-interfaz.md`; PvP game screen
has a real chess clock — countdown, two independent timers, turn switch on boton_1/boton_2,
timeout message — while vs-Magnus is still a static placeholder aside from color selection; can
also run windowed on a regular desktop via `TABLERO_PANTALLA_VENTANA=1`, no hardware needed, with
the clock buttons simulated by the ←/→ keys — see `software-docs/menus.md`), `io/menus_gpio.py`
(thin hardware-real driver: wires `io/sensores.py`'s GPIO buttons into `io/menus.py`'s shared
loop via a custom pygame event, kept in a separate file from `io/menus.py` on purpose so the
notebook-only keyboard-testing code path and the Raspberry-only GPIO code path can't break each
other — see "Modo hardware real" in `software-docs/menus.md`), `io/sensores.py` (chess-clock
buttons — GPIO event detection on the two limit-switch buttons, BOARD pins 33/35, no occupancy
matrix yet; hardware-verified by Tino, consumed by `io/menus_gpio.py` — see
`software-docs/sensores.md`). Still empty: `io/leds.py`, `web/`, and `tests/test_sensores.py`.
`pytest` is a declared dev dependency (`uv add --dev pytest`) and
`uv run pytest` works. Don't assume implementations exist just because a file is present; check
its actual contents. See `software-docs/` (per-module design notes) and `hardware-docs/`
(componentes, pines GPIO, esquema de detección de casillas) for details beyond this file.

Docs, module names, and commit messages are in Spanish (`logica`, `motor`, `tablero`, etc.) —
match that convention for new comments/docstrings in this repo.

## Project structure

```
tablero-ajedrez-inteligente/
├── tablero/                  # Paquete Python (gestionado con uv), raíz de trabajo para uv/pytest
│   └── src/tablero/
│       ├── __init__.py       # Entry point (main()) — mapped via pyproject [project.scripts]
│       ├── config.py         # Pines GPIO y configuración general (implementado)
│       ├── io/                # leds.py (vacío); pantalla.py, calibracion_touch.py, menus.py, menus_gpio.py, sensores.py (implementados)
│       ├── logica/            # estado_tablero.py (implementado); eventos.py (vacío)
│       ├── motor/             # stockfish.py (implementado)
│       └── web/                # Dashboard/API de estado (a futuro, vacío)
├── hardware/scematichs/       # Directorio vacío (.gitkeep); esquemáticos aún no subidos acá
├── hardware-docs/             # Componentes, pines GPIO, esquema de detección de casillas (docs + fotos)
├── software-docs/             # Notas de diseño por módulo (config, logica, motor, pantalla, menus, comandos, pyproject, testing)
└── README.md
```

Key architectural boundary: `io/` (sensores, leds) depends on real GPIO hardware and only runs
on the Raspberry Pi. `logica/` and `motor/` have no hardware dependency and can be developed and
tested on any machine. Keep that separation when adding code — hardware access should stay behind
the `io/` boundary so `logica/`/`motor/` remain testable off-device.

**Syntax-check `io/` code locally, but never run it.** Claude Code sessions on this project run
on Tino's notebook (x86_64, no real GPIO/DRM/touch hardware) — the Raspberry Pi 3B is only
reachable through a separate SSH session Tino runs himself. Static syntax checks against files
under `tablero/src/tablero/io/` are fine (`python -m py_compile`, linters, `ast.parse`, etc.).
Don't actually run or import them (`uv run python -m tablero.io.<module>`, `uv run python -c
"import ..."`, `uv run pytest tests/test_sensores.py`, etc.) — hardware-backed modules will fail
or behave meaninglessly off-device regardless of whether the code is correct, so an import/run
attempt here doesn't prove anything and isn't wanted. Instead, give Tino the exact command(s) to
run over his SSH session and wait for him to report the result. This still applies even for
`io/menus.py`'s windowed mode (`TABLERO_PANTALLA_VENTANA=1`, see `software-docs/menus.md`) — that
mode exists so **Tino** can visually iterate the UI on his own notebook without the Raspberry, not
so Claude Code runs it.

## Commands

All commands run from the `tablero/` subdirectory (that's where `pyproject.toml` lives).

```bash
cd tablero

uv sync              # install/sync dependencies into .venv
uv run tablero        # run the entry point (tablero:main)
uv add <package>      # add a runtime dependency
uv run python -m tablero  # alternative way to run the package
```

```bash
uv run pytest tests/test_logica.py tests/test_motor.py -v   # runnable now (see software-docs/testing.md)
```

`test_logica.py` needs no hardware or external binaries. `test_motor.py` needs the `stockfish`
binary in PATH and skips itself (`pytest.mark.skipif`) if it's missing. `test_sensores.py` is
still empty — needs real hardware to test meaningfully, see `software-docs/testing.md`.
`io/sensores.py` now covers the chess-clock buttons only; the occupancy matrix (74HC165) isn't
implemented yet.

## Dependencies

- `python-chess` (installed as the `python-chess==1.999` compat shim, which pulls in the real
  `chess` package) — move validation and board state
- `rpi-lgpio` — GPIO access; used by `io/sensores.py` for the chess-clock buttons, not yet by the
  occupancy matrix
- `rpi-ws281x` — WS2812B LED strip control (not yet used by any implemented module)
- `pygame` — renders to the RPI LCD V3 touchscreen via DRM/KMS in `io/pantalla.py`; must be
  compiled from source (`[tool.uv] no-binary-package = ["pygame"]` in `pyproject.toml`) because
  the PyPI wheel ships its own SDL2 without KMSDRM support — see `software-docs/pantalla.md`
- `pytest` (dev dependency) — test runner for `tablero/tests/`
- Stockfish — external binary, required for vs-machine mode (installed via system package
  manager, not a Python dependency)

Requires Python >= 3.12 (see `tablero/.python-version`).
