# `config.py`

Configuración general del proyecto: pines GPIO (a futuro, cuando se implemente `io/`)
y, por ahora, la configuración del motor Stockfish.

## Valores actuales

| Nombre | Valor por default | Uso |
|---|---|---|
| `STOCKFISH_PATH` | `shutil.which("stockfish")`, o `"stockfish"` si no se encuentra | Ruta al binario que usa `motor/stockfish.py` para abrir el proceso UCI |
| `STOCKFISH_MOVETIME` | `1.0` (segundos) | Tiempo por jugada por default para `MotorStockfish.mejor_movimiento` |

## Por qué autodetectar `STOCKFISH_PATH`

Stockfish se instala distinto según el sistema (`apt`, `pacman`, `winget`, build manual)
y no siempre termina en la misma ruta. Autodetectarlo con `shutil.which` evita hardcodear
un path que no es portable entre Linux/Windows/Raspberry Pi. Si no se encuentra en PATH,
se deja el string `"stockfish"` en vez de lanzar una excepción acá: así el error real
(binario no encontrado) lo levanta `chess.engine.SimpleEngine.popen_uci` al intentar
abrir el proceso, con un mensaje más específico que si fallara en `config.py`.

Ambos valores se pueden overridear por llamada pasando `ruta_binario`/`tiempo_por_jugada`
a `MotorStockfish(...)` — ver [`docs/motor.md`](./motor.md).
