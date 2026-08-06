# `motor/stockfish.py`

Integración con el motor Stockfish para el modo vs-máquina: dada una posición, pide la
mejor jugada según Stockfish.

## Por qué existe este módulo

Aísla al resto del proyecto del protocolo UCI y del manejo del proceso externo de
Stockfish. Cualquier código que quiera "la jugada del motor" solo necesita un
`chess.Board` y una instancia de `MotorStockfish`, sin conocer detalles de
`chess.engine` ni del ciclo de vida del subproceso.

## API

| Método | Qué hace |
|---|---|
| `MotorStockfish(ruta_binario=None, tiempo_por_jugada=None)` | Abre el proceso de Stockfish. Usa `config.STOCKFISH_PATH`/`config.STOCKFISH_MOVETIME` si no se pasan |
| `.mejor_movimiento(tablero)` | `chess.Move` — mejor jugada de Stockfish para `tablero`, limitada por `tiempo_por_jugada` segundos |
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
- **Fuerza fija, sin Skill Level**: en esta primera etapa Stockfish juega a máxima
  fuerza, limitado solo por tiempo (`chess.engine.Limit(time=...)`). No hay modo de
  análisis/hint ni dificultad configurable — quedó fuera de alcance deliberadamente
  para mantener el MVP simple; se puede agregar después seteando la opción UCI
  `Skill Level` (0-20) sin cambiar la forma de la API pública.
- **Requiere `cerrar()` explícito**: `SimpleEngine.popen_uci` levanta un proceso del
  sistema operativo. Si no se llama a `cerrar()` (o no se usa como context manager)
  el proceso de Stockfish queda huérfano. Por eso `mejor_movimiento` no lo cierra
  solo — se puede pedir más de una jugada con la misma instancia sin reabrir el
  proceso cada vez.

## Configuración relacionada (`config.py`)

- `STOCKFISH_PATH`: se autodetecta con `shutil.which("stockfish")`; si no está en
  PATH, queda el string `"stockfish"` para que el error de arranque sea explícito en
  vez de fallar en silencio.
- `STOCKFISH_MOVETIME`: segundos por jugada por default (`1.0`).

## Fuera de alcance (todavía)

- Dificultad configurable (Skill Level / profundidad).
- Modo de análisis/hint para partidas humano-vs-humano.

## Tests

`tablero/tests/test_motor.py` — requiere el binario `stockfish` instalado; el módulo
entero se saltea (`pytest.mark.skipif`) si no está en PATH. Cubre: jugada legal desde
la posición inicial, resolución de un mate en 1, cierre del proceso sin excepciones.
Tiempos por jugada bajos (0.1-0.2s) porque las posiciones de test no necesitan más.

```bash
cd tablero && uv run pytest tests/test_motor.py -v
```
