# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Tablero de ajedrez físico con sensores por casilla (74HC165) y LEDs (WS2812B), controlado
íntegramente por una Raspberry Pi 3B. Valida movimientos y mantiene el estado de la partida
usando `python-chess`, y puede jugar contra Stockfish en modo vs-máquina. Todo corre en un único
dispositivo, sin hardware ni proceso adicional.

**Current state**: this is an early-stage scaffold. All modules under `tablero/src/tablero/`
(`config.py`, `io/`, `logica/`, `motor/`, `web/`) and all files under `tablero/tests/` exist but
are currently empty — only the package layout and entry point (`main()` in `__init__.py`,
printing a placeholder) have been implemented so far. `pytest` is not yet a declared dependency.
Don't assume implementations exist just because a file is present; check its actual contents.

Docs, module names, and commit messages are in Spanish (`logica`, `motor`, `tablero`, etc.) —
match that convention for new comments/docstrings in this repo.

## Project structure

```
tablero-ajedrez-inteligente/
├── tablero/                  # Paquete Python (gestionado con uv), raíz de trabajo para uv/pytest
│   └── src/tablero/
│       ├── __init__.py       # Entry point (main()) — mapped via pyproject [project.scripts]
│       ├── config.py         # Pines GPIO y configuración general
│       ├── io/                # Lectura de sensores (74HC165) y control de LEDs (WS2812B)
│       ├── logica/            # Reglas del juego y estado del tablero (python-chess)
│       ├── motor/             # Integración con Stockfish (modo vs-máquina)
│       └── web/                # Dashboard/API de estado (a futuro)
├── hardware/scematichs/       # Esquemáticos y documentación de electrónica
└── README.md
```

Key architectural boundary: `io/` (sensores, leds) depends on real GPIO hardware and only runs
on the Raspberry Pi. `logica/` and `motor/` have no hardware dependency and can be developed and
tested on any machine. Keep that separation when adding code — hardware access should stay behind
the `io/` boundary so `logica/`/`motor/` remain testable off-device.

## Commands

All commands run from the `tablero/` subdirectory (that's where `pyproject.toml` lives).

```bash
cd tablero

uv sync              # install/sync dependencies into .venv
uv run tablero        # run the entry point (tablero:main)
uv add <package>      # add a runtime dependency
uv run python -m tablero  # alternative way to run the package
```

There is no test runner configured yet (`pytest` isn't in `pyproject.toml` dependencies, and all
test files are empty). Before running tests, add pytest as a dev dependency
(`uv add --dev pytest`) and then use `uv run pytest`.

## Dependencies

- `python-chess` — move validation and board state
- `rpi-lgpio` — GPIO access (sensor matrix)
- `rpi-ws281x` — WS2812B LED strip control
- Stockfish — external binary, required for vs-machine mode (installed via system package
  manager, not a Python dependency)

Requires Python >= 3.12 (see `tablero/.python-version`).
