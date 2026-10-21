# `motor/stockfish.py`

Integración con el motor Stockfish para el modo vs-máquina ("Magnus", ver
[`vs-magnus.md`](./vs-magnus.md)): dada una posición, pide la mejor jugada según Stockfish,
a fuerza máxima o en uno de los niveles de `config.NIVELES_MAGNUS`.

## Por qué existe este módulo

Aísla al resto del proyecto del protocolo UCI y del manejo del proceso externo de
Stockfish. Cualquier código que quiera "la jugada del motor" solo necesita un
`chess.Board` y una instancia de `MotorStockfish`, sin conocer detalles de
`chess.engine` ni del ciclo de vida del subproceso.

## API

| Método | Qué hace |
|---|---|
| `MotorStockfish(ruta_binario=None, tiempo_por_jugada=None, nivel=None)` | Abre el proceso de Stockfish. Usa `config.STOCKFISH_PATH` si no se pasa la ruta. Con `nivel` (clave de `config.NIVELES_MAGNUS`: `facil`, `medio`, `dificil`) configura `Skill Level` y usa los segundos por jugada del nivel; un nivel que no existe da `ValueError` antes de abrir nada. `tiempo_por_jugada`, si se pasa, gana sobre el del nivel. Sin ninguno de los dos, `config.STOCKFISH_MOVETIME` a fuerza máxima |
| `.mejor_movimiento(tablero)` | `chess.Move` — mejor jugada de Stockfish para `tablero`, limitada por el tiempo por jugada. Bloquea mientras piensa |
| `.cerrar()` | Cierra el proceso de Stockfish |
| Context manager (`with MotorStockfish(...) as motor:`) | Garantiza `cerrar()` incluso si hay una excepción |

## Decisiones de diseño

- **Recibe `chess.Board`, no `EstadoTablero`**: para que `motor/` no dependa del
  wrapper definido en `logica/`. El llamador pasa `estado.board`. Esto mantiene a
  `motor/` y `logica/` como módulos independientes que solo comparten la dependencia
  común (`chess.Board`), en línea con el boundary de `CLAUDE.md`.
- **API síncrona (`SimpleEngine`, no `asyncio`)**: coherente con el resto del proyecto,
  que va a correr como un loop de polling de GPIO en la Raspberry Pi, no como una app
  asíncrona.
- **Niveles = `Skill Level` + tiempo por jugada**: la opción UCI `Skill Level` (0-20) se
  configura una sola vez al abrir el motor, y cada jugada usa
  `chess.engine.Limit(time=...)` con los segundos del nivel. Los valores viven en una
  tabla de `config.py` (`NIVELES_MAGNUS`) para afinarlos jugando sin tocar código, por
  ejemplo con `uv run simulacion --magnus facil`. Sin `nivel` se comporta como antes:
  fuerza máxima.
- **Bloquea mientras piensa, y está bien**: el que no puede bloquearse es el loop de
  `io/juego.py`, así que ahí el motor corre en un `ThreadPoolExecutor` de un hilo
  (`SimpleEngine` es thread-safe; se le pasa una copia del tablero). La simulación sí
  bloquea, porque igual está esperando lo que se tipea.
- **En su propio grupo de procesos (`setpgrp=True`)**: si no, un Ctrl+C en la terminal
  le llega también a Stockfish, que muere antes de que Python termine la jugada en curso
  y lo cierre ordenadamente.
- **Requiere `cerrar()` explícito**: `SimpleEngine.popen_uci` levanta un proceso del
  sistema operativo. Si no se llama a `cerrar()` (o no se usa como context manager)
  el proceso de Stockfish queda huérfano. Por eso `mejor_movimiento` no lo cierra
  solo — se puede pedir más de una jugada con la misma instancia sin reabrir el
  proceso cada vez.

## Configuración relacionada (`config.py`)

- `STOCKFISH_PATH` (lo calcula `buscar_stockfish()`): primero `shutil.which("stockfish")`;
  si no está en el PATH, `/usr/games/stockfish`, que es donde lo instala `apt` en
  Raspberry Pi OS. Hace falta porque `io/juego.py` se relanza con `sudo` por los LEDs, y
  el PATH de `sudo` (`secure_path`) normalmente no incluye `/usr/games`. Si no está en
  ningún lado queda el string `"stockfish"`, para que el error de arranque sea explícito.
- `STOCKFISH_MOVETIME`: segundos por jugada sin nivel (`1.0`).
- `NIVELES_MAGNUS`: clave → `NivelMagnus(nombre, skill_level, segundos_por_jugada)`.

| Clave | `nombre` | `Skill Level` | Segundos por jugada |
|---|---|---|---|
| `facil` | fácil | 0 | 0,1 |
| `medio` | medio | 6 | 0,5 |
| `dificil` | difícil | 20 | 1,0 |

Son valores iniciales. `Skill Level 0` anda por los 1300 Elo según la calibración de
Stockfish; si para un principiante sigue siendo mucho, se puede agregar una dosis de
jugadas al azar más adelante.

## Fuera de alcance (todavía)

- Modo de análisis/hint para partidas humano-vs-humano.
- Jugadas al azar para un nivel más bajo que `Skill Level 0`.

## Tests

`tablero/tests/test_motor.py` — requiere el binario `stockfish` instalado; el módulo
entero se saltea (`pytest.mark.skipif`) si no está en PATH. Cubre: jugada legal desde
la posición inicial, resolución de un mate en 1, cierre del proceso sin excepciones,
cada nivel (configura `Skill Level` y devuelve una jugada legal), nivel desconocido y
que el proceso quede en otro grupo. Tiempos por jugada bajos (0.1-0.2s) salvo en los
niveles, que usan los suyos (el difícil, 1 s).

La búsqueda del binario (`config.buscar_stockfish`) se testea aparte, sin Stockfish, en
`tablero/tests/test_config.py`.

```bash
cd tablero && uv run pytest tests/test_motor.py -v
```
