# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Tablero de ajedrez físico con sensores Hall por casilla y LEDs (WS2812B), controlado por una
Raspberry Pi 3B. Valida movimientos y mantiene el estado de la partida usando `python-chess`, y
puede jugar contra Stockfish en modo vs-máquina. La lógica, el motor y la interfaz corren en la
Pi; desde el 2026-10-17 la única excepción es la matriz de sensores, que la barre un **Arduino
Nano** (un NPN por fila, Hall a 5 V) conectado a la Pi por USB.

**Hardware architecture change (v3, built and working end to end on the Pi)**: the sensor matrix
moved off the Pi's GPIO. The v2 design (Pi → 74HC138 + 74HC165 at 3.3 V, each Hall's GND
on a 138 output) was tested and failed — the active 138 output read 1.6 V because it can't sink
~35 mA per row. The chosen replacement is an Arduino Nano driving one NPN per row (D2–D9) and
reading columns (D10–D12, A0–A4), reporting to the Pi over USB serial. Rows/columns keep their
old Yk/Dk numbering so `CASILLA_DE_CELDA_HALL` stays valid. The 64 cells are already soldered
with the diode in each Hall's GND and OUT straight to the column (not the diode-on-OUT layout
first planned), which is why the drivers use BC337/2N2222/S8050 with 470 Ω bases (up to ~200 mA
per full row) and why there's an analog-read "plan B" for the columns. **The Nano firmware exists**
(`firmware/matriz-nano/matriz-nano.ino`): a command/response text protocol over USB serial at
115200 (`?`, `L [µs]`, `F k`, `C`, `X`, `A`, `V`) where the Nano only runs scan primitives and all
debounce/calibration/mapping stays in Python; each command maps to an `io/matriz.py` function, and
the same commands serve for manual hardware tests from a serial monitor. Plan B is a compile-time
switch (`-DPLAN_B=1`). Protocol spec and that mapping: `software-docs/firmware-nano.md`. **Tested
on the real Nano with the full matrix** (plan A, digital columns; all 64 squares detected) from
the serial monitor on the notebook. **`io/matriz.py` now talks to the Nano over USB serial**
(`pyserial`, port from `config.NANO_PUERTO` or autodetected, `ErrorNano` with a what-to-check
message on any port/protocol failure) with the same public API the v2 GPIO driver had; the
protocol text (building `L <µs>`, decoding `M`/`C`/`A`/`LISTO`) is pure code in
`logica/matriz.py`, tested in `tests/test_matriz.py`. **Verified on the Pi (2026-10-18)**: the
Halls (`sensores mapear`) and the LEDs (`prueba_tablero leds`) are mapped in `config.py`, and
`prueba_tablero recorrido`/`espejo` pass. Still pending, waiting for the 32 pieces: `sensores
calibrar` (so `HALL_ESPERA_ENCENDIDO`/`HALL_LECTURAS_ESTABLES` are still the defaults) and
`prueba_tablero inicial`. Power is temporary: the Pi on one phone charger, LEDs + Nano on
another (the Nano still talks to the Pi over USB); to be unified later. Build guide:
`hardware-docs/matriz-hall-nano.md`;
iterations (v1 reed, v2 Hall+138/165, v3 Nano) and every rejected alternative with its reason:
`hardware-docs/historial-deteccion.md`.

**Current state**: early-stage but with the first vertical slices implemented. Done:
`config.py` (Stockfish + pantalla config), `logica/estado_tablero.py` (wraps `chess.Board`,
tested in `tests/test_logica.py`), `logica/eventos.py` (interprets each occupancy reading by
comparing it with the occupancy every legal move would leave — normal, captures, castling,
en passant, promotion always to queen — plus a vacated/refilled-squares history to tell apart
captures by the same piece; **never applies the move**, and `marcas()` says what to light on
each square; tested in `tests/test_eventos.py`, see `software-docs/eventos.md`), `motor/stockfish.py` (UCI integration via
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
buttons — GPIO event detection on the two limit-switch buttons, BOARD pins 33/35,
hardware-verified by Tino, consumed by `io/menus_gpio.py` — plus the occupancy matrix with
**Hall sensors** (A3144, scanned by the Nano): a calibrable per-row power-on wait
(`HALL_ESPERA_ENCENDIDO`, sent to the Nano in µs on each scan), a 64-entry celda→casilla table
(`CASILLA_DE_CELDA_HALL` in `config.py`, rows/columns printed as F0..F7/C0..C7), and
`medir`/`matriz`/`calibrar`/`mapear` CLIs (`medir F0` pins one row on and shows the `C`/`A`
readings live; the row takes an uppercase F because `f3` is a square) — Pi-side test steps in
"Cómo probarlo" of `software-docs/sensores.md`; consumed by `io/juego.py`),
`io/matriz.py` (Nano serial driver shared by both sensor versions: open port + wait for `LISTO`,
one function per firmware command, retries on malformed replies, debounced `LectorMatriz`, live
view), `io/sensores_reed.py` (the previous reed-switch version, kept on purpose in case of a
switch back: same API, two-permutation mapping, own CLI; works over the Nano too since a reed +
diode pulls its column like a Hall — see `software-docs/sensores-reed.md`),
`io/prueba_tablero.py` (sensors + LEDs together: sensor-assisted LED↔square association, guided
a1..h8 walk, live mirror, initial-position check; re-execs itself via `sudo` like `io/leds.py` —
see `software-docs/prueba-tablero.md`), `logica/matriz.py` (hardware-free processing of raw
matrix reads: table validation, celda→casilla, the math behind `calibrar`, the Nano protocol text; tested in
`tests/test_matriz.py`), `io/leds.py` (WS2812B via `rpi-ws281x` on BCM 12, needs root (the `__main__` re-execs itself via `sudo` so `uv run python -m tablero.io.leds` works) +
`dtparam=audio=off`, casilla→LED table `LED_DE_CASILLA` generated by a `calibrar` CLI (or, with the Halls mapped, by `prueba_tablero leds`), `todos`/`recorrer`/`esquinas`/`verificar` test CLIs;
**hardware-verified**, real mapping in `config.py` — see `software-docs/leds.md`), `logica/reloj.py` (`RelojAjedrez`, the project's **only** chess
clock — `io/menus.py` no longer implements its own, see `software-docs/partida.md`),
`logica/notacion.py` (parses typed moves: Spanish/English SAN + UCI; the language is chosen
rather than guessed because `R` is king in Spanish and rook in English),
`logica/partida.py` (`Partida` = board + clock + the two-condition rule: the turn passes only
if the right player made a legal move AND then pressed their clock button; typed moves via
`intentar_movimiento`, already-resolved `chess.Move`s via `intentar_jugada`),
`logica/partida_fisica.py` (`PartidaFisica` = `Partida` + `RastreadorMovimientos` on the same
board: on the physical board the move **counts when the clock button is pressed** — until then
pieces can be rearranged freely; on the press, a legal move is applied and the turn passes
together, otherwise the press is ignored with what to fix; tested in
`tests/test_partida_fisica.py`, see `software-docs/partida.md`), `io/juego.py` (the terminal
program on the Pi that wires the Nano matrix, the GPIO clock buttons (via a `queue.Queue`) and
the LEDs into `PartidaFisica`; waits for the starting position first; `--fen` lets it run with
a few magnets; re-execs via `sudo` unless `--sin-leds`, and chowns the registros back to
`SUDO_UID`; **not yet tested on the Pi** — see `software-docs/juego.md`), `logica/registro.py` (per-game
PGN for the last 15 games plus a detailed event log for the last 5, under `tablero/registros/`,
gitignored — see `software-docs/registro.md`), and `simulacion.py` (terminal-only game
simulation: type a move, the program answers how the board would react, with a real running
clock; runs anywhere, no hardware — see `software-docs/simulacion.md`). Still empty: `web/` and
`tests/test_sensores.py`. Not yet wired: the touchscreen PvP screen (`io/menus.py`) still runs
its clock on the buttons alone; `PartidaFisica` is ready for it, but reading the Nano without
blocking the pygame loop is still to do.
`pytest` is a declared dev dependency (`uv add --dev pytest`) and
`uv run pytest` works (169 tests, all hardware-free except `test_motor.py`, which skips itself
without the `stockfish` binary). Don't assume implementations exist just because a file is present; check
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
│       ├── config.py         # Pines GPIO, pantalla, registros y configuración general
│       ├── simulacion.py      # Simulación de partida por terminal (sin hardware)
│       ├── io/                # pantalla.py, calibracion_touch.py, menus.py, menus_gpio.py, sensores.py (Hall),
│       │                      #   sensores_reed.py, matriz.py, leds.py, prueba_tablero.py, juego.py (implementados)
│       ├── logica/            # estado_tablero.py, eventos.py, reloj.py, notacion.py, partida.py, registro.py,
│       │                      #   partida_fisica.py, matriz.py (implementados)
│       ├── motor/             # stockfish.py (implementado)
│       └── web/                # Dashboard/API de estado (a futuro, vacío)
├── firmware/matriz-nano/      # Firmware del Arduino Nano (matriz Hall v3), un solo .ino; arduino-cli
├── hardware/scematichs/       # Directorio vacío (.gitkeep); esquemáticos aún no subidos acá
├── hardware-docs/             # Componentes, pines GPIO, esquema de detección de casillas (docs + fotos),
│                              #   conexiones pata por pata de los chips, celdas Hall, guías de prueba
│                              #   de la matriz (Hall y reed), redes wifi de la Raspberry,
│                              #   matriz-hall-nano.md (v3 actual) e historial-deteccion.md
├── software-docs/             # Notas de diseño por módulo (config, logica, eventos, partida, registro,
│                              #   simulacion, motor, pantalla, menus, sensores, sensores-reed, leds,
│                              #   prueba-tablero, juego, firmware-nano, comandos, pyproject, testing)
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
so Claude Code runs it. The same split applies to the Nano firmware: compiling it locally with
`arduino-cli compile` is fine (it's the firmware's syntax check), but uploading it and opening the
serial monitor need the physical Nano, so give Tino those commands.

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
uv run pytest -v                       # the whole suite (see software-docs/testing.md)
uv run python -m tablero.simulacion    # terminal game simulation, no hardware
```

The Nano firmware builds from the **repo root** (not `tablero/`) with the `arduino-cli` +
`arduino:avr` core installed on the notebook:

```bash
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 firmware/matriz-nano   # add --build-property "compiler.cpp.extra_flags=-DPLAN_B=1" for plan B
```

Upload/monitor commands (Tino runs them) are in `software-docs/comandos.md`.

Only `test_motor.py` needs anything special (the `stockfish` binary in PATH; it skips itself
via `pytest.mark.skipif` if missing) — everything else runs anywhere. `test_sensores.py` is
still empty: it needs real hardware to test meaningfully, see `software-docs/testing.md`.
`io/sensores.py` covers the chess-clock buttons and the Hall-sensor occupancy matrix (the Nano
serial driver itself is in `io/matriz.py`; the old reed version in `io/sensores_reed.py`).

`tablero/simulacion.py` is the way to exercise the game logic (move validation + clock rules)
off-device: it lives at the package root, **not** under `io/`, precisely so it can be run here
— it imports nothing from `io/`, so the "never run `io/` code" rule below doesn't apply to it.

## Dependencies

- `python-chess` (installed as the `python-chess==1.999` compat shim, which pulls in the real
  `chess` package) — move validation and board state
- `rpi-lgpio` — GPIO access; used by `io/sensores.py` for the chess-clock buttons
- `pyserial` — USB serial link to the Arduino Nano that scans the sensor matrix, used by
  `io/matriz.py`; pure Python, no platform marker. On the Pi the user must be in `dialout`
- `rpi-ws281x` — WS2812B LED strip control, used by `io/leds.py` (and `io/prueba_tablero.py`)
- `pygame` — renders to the RPI LCD V3 touchscreen via DRM/KMS in `io/pantalla.py`; must be
  compiled from source (`[tool.uv] no-binary-package = ["pygame"]` in `pyproject.toml`) because
  the PyPI wheel ships its own SDL2 without KMSDRM support — see `software-docs/pantalla.md`
- `pytest` (dev dependency) — test runner for `tablero/tests/`; shared fixtures (the fake
  clock used by the time-dependent tests) live in `tablero/tests/conftest.py`
- Stockfish — external binary, required for vs-machine mode (installed via system package
  manager, not a Python dependency)

Requires Python >= 3.12 (see `tablero/.python-version`).
