# Comandos: referencia rápida

Todos los comandos corren desde `tablero/` (ahí vive `pyproject.toml`), salvo que se
indique lo contrario. "Raspberry" significa por SSH, con el overlay `piscreen` activado
(ver [`pantalla.md`](./pantalla.md)); "notebook" significa cualquier máquina de
escritorio, sin hardware del tablero.

## Setup

```bash
cd tablero
uv sync              # instala/sincroniza dependencias en .venv
uv add <paquete>      # agrega una dependencia de runtime
uv add --dev <paquete> # agrega una dependencia de desarrollo (ej. pytest)
```

Corre en Raspberry o notebook por igual. Detalle de por qué `pygame` necesita
`uv sync --reinstall-package pygame` la primera vez en la Raspberry (compila desde fuente
contra el SDL2 del sistema): ver [`pantalla.md`](./pantalla.md#instalación-de-pygame).

## Tests

```bash
uv run pytest -v      # toda la suite
```

Corre en notebook o Raspberry. Solo `test_motor.py` necesita algo especial (el binario
`stockfish` en el `PATH`, y se saltea solo si no está); el resto —`test_logica.py`,
`test_eventos.py`, `test_reloj.py`, `test_notacion.py`, `test_partida.py`,
`test_registro.py`— no requiere nada. `test_sensores.py` está vacío todavía. Detalle
completo: [`testing.md`](./testing.md).

## Simulación de partida (terminal, sin hardware)

```bash
uv run python -m tablero.simulacion              # pregunta notación y minutos
uv run simulacion --notacion es --minutos 3      # sin preguntas
uv run simulacion --sin-registro                 # sin escribir en registros/
```

Corre en notebook o Raspberry, no toca `io/`. Se tipea un movimiento y el programa responde
si el tablero lo aceptaría o lo bloquearía, con el reloj corriendo y la regla de las dos
condiciones (movimiento legal + botón del reloj). Comandos completos y ejemplos:
[`simulacion.md`](./simulacion.md).

Cada partida queda registrada en `tablero/registros/` (PGN de las últimas 15, log detallado
de las últimas 5, ver [`registro.md`](./registro.md)):

```bash
cat tablero/registros/partidas/*.pgn      # PGN multi-partida, se abre en cualquier visor
cat tablero/registros/detalle/*.log       # qué intentó cada jugador, cuándo y con qué reloj
```

## Entry point del proyecto

```bash
uv run tablero               # ejecuta tablero:main
uv run python -m tablero     # forma alternativa, mismo resultado
```

## Scripts de `io/` (pantalla táctil)

Estos sí dependen de hardware o de un modo específico — ver la columna "Dónde corre".
**Regla del proyecto**: Claude Code nunca ejecuta nada de esto por su cuenta (ni siquiera
como "chequeo de sintaxis"), siempre le da a Tino el comando exacto para que lo corra él
(por SSH en la Raspberry, o localmente en su notebook para el modo ventana de `menus.py`).

| Comando | Qué hace | Dónde corre | Variables de entorno relevantes |
|---|---|---|---|
| `uv run python -m tablero.io.pantalla` | Corre `probar_boton()`: dibuja un botón de prueba y loguea cada evento de touch (`FINGERDOWN`/`MOUSEBUTTONDOWN`), aplicando calibración si existe. `Ctrl+C` para salir. | Pensado para Raspberry, pero también corre en notebook con la variable de abajo (útil para revisar el layout del botón con mouse). | `TABLERO_PANTALLA_VENTANA=1` — ver más abajo. |
| `uv run python -m tablero.io.calibracion_touch` | Corre `ejecutar_calibracion()`: muestra 5 cruces, pide tocarlas en orden, ajusta una transformación afín por mínimos cuadrados y la guarda en `calibracion_touch.json`. | Solo tiene sentido en la Raspberry — calibrar con mouse en una ventana da una transformación inútil (no hay touch real que corregir). | `TABLERO_PANTALLA_VENTANA=1` evita el crash de `kmsdrm not available` si se corre en notebook, pero no lo hace útil. |
| `uv run python -m tablero.io.menus` | Corre `ejecutar_menus()`: navega las 6 pantallas de menú/juego de los bocetos (ver [`menus.md`](./menus.md)), logueando cada botón tocado. `Ctrl+C` para salir. | Raspberry (comportamiento default) **o** notebook, con la variable de abajo — este es el caso de uso principal del modo ventana. | `TABLERO_PANTALLA_VENTANA=1` — ver más abajo. |

`TABLERO_PANTALLA_VENTANA=1`: evita que `io/_sdl.py` fuerce `SDL_VIDEODRIVER=kmsdrm` +
`SDL_NOMOUSE=1` (el backend que busca el panel físico vía DRM/KMS). Con la variable seteada,
`pygame` abre una ventana normal de escritorio de 480×320 y el mouse queda habilitado, en
vez de fallar con `pygame.error: kmsdrm not available` al no encontrar el dispositivo DRM
del panel. Sin la variable, los tres scripts se comportan como si corrieran en la
Raspberry. Detalle de por qué esto vive centralizado en `io/_sdl.py` y no repetido en cada
archivo: [`menus.md`](./menus.md#modo-ventana-testear-sin-la-raspberry).

Ejemplos completos:

```bash
# Por SSH, en la Raspberry:
cd tablero && uv run python -m tablero.io.menus

# En el notebook, sin la Raspberry, para iterar el diseño visual:
cd tablero && env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus
```

## Ver también

- [`pantalla.md`](./pantalla.md) — overlay `piscreen`, instalación de `pygame`, calibración
  táctil.
- [`menus.md`](./menus.md) — grafo de navegación de `io/menus.py` y el modo ventana.
- [`testing.md`](./testing.md) — qué cubre cada archivo de test.
- [`simulacion.md`](./simulacion.md) — modo de prueba de la lógica por terminal.
- [`registro.md`](./registro.md) — dónde y cómo quedan registradas las partidas.
