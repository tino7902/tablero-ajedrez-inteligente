# `config.py`

Configuración general del proyecto: pines GPIO (a futuro, cuando se implemente `io/`)
y, por ahora, la configuración del motor Stockfish.

## Valores actuales

| Nombre | Valor por default | Uso |
|---|---|---|
| `STOCKFISH_PATH` | `shutil.which("stockfish")`, o `"stockfish"` si no se encuentra | Ruta al binario que usa `motor/stockfish.py` para abrir el proceso UCI |
| `STOCKFISH_MOVETIME` | `1.0` (segundos) | Tiempo por jugada por default para `MotorStockfish.mejor_movimiento` |
| `PANTALLA_ANCHO` | `480` | Ancho en píxeles de la pantalla, usado por `io/pantalla.py` para abrir la superficie de `pygame` |
| `PANTALLA_ALTO` | `320` | Alto en píxeles de la pantalla |
| `PANTALLA_TAMANO_FUENTE` | `48` | Tamaño de fuente por default para `mostrar_texto` |
| `NANO_PUERTO` | `None` (autodetectar: el único `/dev/ttyUSB*` o `/dev/ttyACM*`) | Puerto serie del Arduino Nano que barre la matriz, usado por `io/matriz.py`. Se fija a mano solo si hay varios puertos serie |

Las demás constantes de la matriz (`HALL_ESPERA_ENCENDIDO`, `HALL_LECTURAS_ESTABLES`,
`CASILLA_DE_CELDA_HALL`) las generan `calibrar` y `mapear`: ver "Configuración" en
[`sensores.md`](./sensores.md#configuración-configpy). Los pines `PIN_MATRIZ_*` del 74HC138 y
el 74HC165 se borraron cuando `io/matriz.py` pasó al puerto serie del Nano.

## Por qué autodetectar `STOCKFISH_PATH`

Stockfish se instala distinto según el sistema (`apt`, `pacman`, `winget`, build manual)
y no siempre termina en la misma ruta. Autodetectarlo con `shutil.which` evita hardcodear
un path que no es portable entre Linux/Windows/Raspberry Pi. Si no se encuentra en PATH,
se deja el string `"stockfish"` en vez de lanzar una excepción acá: así el error real
(binario no encontrado) lo levanta `chess.engine.SimpleEngine.popen_uci` al intentar
abrir el proceso, con un mensaje más específico que si fallara en `config.py`.

Ambos valores se pueden overridear por llamada pasando `ruta_binario`/`tiempo_por_jugada`
a `MotorStockfish(...)` — ver [`docs/motor.md`](./motor.md).

## Por qué no hay una constante de rotación de pantalla

La rotación física del panel se resuelve en el parámetro `rotate=` del overlay de
kernel `piscreen` (en `config.txt` de la Raspberry), no en la app: el driver ya
entrega el framebuffer con la orientación final. Una constante `PANTALLA_ROTACION`
acá no la leería ningún código — ver [`docs/pantalla.md`](./pantalla.md).
