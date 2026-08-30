# `logica/partida.py`, `reloj.py` y `notacion.py` — la capa de partida

Los tres módulos que convierten "hay reglas de ajedrez" ([`logica.md`](./logica.md)) en
"hay una partida en curso": quién tiene el turno, cuánto tiempo le queda, qué pasa cuando
alguien intenta un movimiento y cuándo pasa el turno de verdad.

Ninguno depende de hardware. Los usa hoy la simulación por terminal
([`simulacion.md`](./simulacion.md)) y los va a usar el tablero real cuando
`io/sensores.py` reporte movimientos, sin cambiar nada de esta capa.

## `logica/partida.py`

`Partida` compone `EstadoTablero` (reglas), `RelojAjedrez` (tiempo) y, opcionalmente,
`RegistroPartida` ([`registro.md`](./registro.md)), y agrega la regla que define el turno
en el tablero físico:

> el turno pasa al otro jugador solo si (1) el jugador correcto hizo un movimiento legal
> **y** (2) presionó su botón del reloj **después** de moverlo.

Mientras falta la condición 2 (`esperando_boton`), ningún movimiento se acepta: ni el del
rival ni un segundo del mismo jugador. Y el tiempo le sigue corriendo a quien movió, igual
que un reloj físico si te olvidás de apretarlo.

### API

| Método/propiedad | Qué hace |
|---|---|
| `Partida(*, segundos_por_jugador, idioma, fen, registro, fuente_tiempo)` | Arranca una partida; `fuente_tiempo` se inyecta en los tests |
| `.intentar_movimiento(texto)` | Procesa un movimiento tipeado → `ResultadoJugada` |
| `.pulsar_boton(color)` | Procesa el botón del reloj de `color` → `ResultadoBoton` |
| `.actualizar_tiempo()` / `.avanzar_tiempo(seg)` | Descuenta tiempo real / simulado; `True` si recién se agotó |
| `.finalizar(motivo)` | Cierra la partida y su registro; idempotente |
| `.turno` | Color al que le toca según el **reloj** (el turno que percibe el jugador) |
| `.esperando_boton` | Color que ya movió y no pulsó, o `None` |
| `.terminada` / `.motivo_fin` / `.resultado()` | Fin de partida y resultado PGN (`1-0`, `0-1`, `1/2-1/2`, `*`) |

`ResultadoJugada.tipo` (`TipoJugada`):

| Valor | Cuándo |
|---|---|
| `ACEPTADO` | Movimiento legal aplicado; queda pendiente el botón |
| `BLOQUEADO_FALTA_RELOJ` | Hay un movimiento sin confirmar con el botón |
| `BLOQUEADO_ILEGAL` | La pieza no está en el origen, o no puede hacer ese movimiento |
| `BLOQUEADO_TURNO` | El movimiento es del color que no tiene el turno |
| `BLOQUEADO_NOTACION` | No se entiende lo que se escribió |
| `BLOQUEADO_TIEMPO` / `BLOQUEADO_TERMINADA` | La partida ya terminó |

`ResultadoBoton.tipo` (`TipoBoton`): `TURNO_PASADO`, `IGNORADO_SIN_MOVIMIENTO` (pulsó sin
haber movido: condición 1 incumplida), `IGNORADO_COLOR` (botón del otro jugador),
`IGNORADO_TIEMPO`, `IGNORADO_TERMINADA`.

Cada resultado trae un `motivo` en castellano listo para mostrar, armado con la posición
real: `la dama de d1 no puede ir a h5`, `no hay ninguna pieza en a3`, `ninguna torre de
blancas puede ir a h4`, `'Cf6' es un movimiento de negras, pero el turno es de blancas`.

### Decisiones de diseño

- **El board cambia de turno antes que el reloj.** El movimiento se aplica al
  `chess.Board` en el acto (igual que hace [`eventos.py`](./eventos.md) al detectarlo por
  sensores), porque el board es lo que valida la posición y tiene que estar sincronizado
  con las piezas físicas. El turno que percibe el jugador es el del reloj, que solo avanza
  con el botón: ese desfase *es* la condición 2 pendiente.
- **Mate y tablas no esperan el botón.** Si el movimiento termina la partida, no tiene
  sentido dejarla trabada esperando una pulsación.
- **"Es del otro color" se distingue de "es ilegal"** probando el mismo texto sobre una
  copia del board con el turno invertido. Es solo para el mensaje: si el intento falla, se
  cae al mensaje genérico de ilegal.

## `logica/reloj.py`

`RelojAjedrez` es el **único** reloj del proyecto: lo usan `Partida` y también la pantalla
PvP de `io/menus.py`, que antes descontaba el tiempo a mano en su loop de pygame (ver
[`menus.md`](./menus.md)).

| Método/propiedad | Qué hace |
|---|---|
| `RelojAjedrez(segundos_por_jugador, fuente_tiempo=time.monotonic)` | Arranca los dos temporizadores, turno en blancas |
| `.turno` | Color cuyo reloj corre; queda congelado en el perdedor al agotarse |
| `.restante(color)` / `.tiempo_agotado` / `.perdedor` | Estado del reloj |
| `.actualizar()` | Descuenta el tiempo real desde la última llamada; `True` solo la vez que se agota |
| `.avanzar(segundos)` | Descuenta tiempo simulado (el comando `esperar` de la simulación) |
| `.pulsar(color)` | Pasa el turno si `color` es quien tiene el reloj corriendo |
| `formatear_tiempo(segundos)` | `"MM:SS"`, redondeando hacia arriba |

Notas:

- **No conoce la regla de las dos condiciones**: solo mide tiempo y cambia de turno cuando
  se lo piden. Eso lo decide `Partida`. Así el mismo reloj le sirve a `io/menus.py`, que
  todavía no tiene sensores y pasa el turno con el botón solo.
- **La fuente de tiempo es inyectable**, que es lo que hace deterministas los tests (ver la
  fixture `tiempo` en `tests/conftest.py`).
- **`formatear_tiempo` redondea hacia arriba** para que una partida de 5 minutos muestre
  `05:00` al arrancar y `00:00` recién cuando el tiempo se acabó de verdad, como un reloj
  de ajedrez comercial.

## `logica/notacion.py`

Traduce lo que tipea el jugador a un `chess.Move`. Función pura sobre un `chess.Board`.

| Elemento | Qué hace |
|---|---|
| `Idioma.ESPANOL` / `Idioma.INGLES` | Idioma de la notación algebraica |
| `parsear_movimiento(texto, board, idioma)` | `chess.Move` legal, o excepción |
| `NotacionInvalidaError` | No se entiende lo que se escribió |
| `MovimientoIlegalError` | Se entiende, pero no es legal (el "movimiento bloqueado") |
| `NOMBRES_COLOR`, `NOMBRES_PIEZA`, `describir_pieza`, `ninguna_pieza` | Nombres en español, compartidos con `eventos.py` y `registro.py` |

Acepta UCI (`e2e4`, `e7e8d`) siempre, y SAN en el idioma elegido: `Cf3`/`Nf3`, `e8=D`,
`O-O`, `0-0`. La traducción español→inglés (`R→K`, `D→Q`, `T→R`, `A→B`, `C→N`) se aplica
solo a la letra inicial y a la de promoción tras `=`, nunca al string entero: un reemplazo
global se pisaría a sí mismo (`T→R` y después `R→K`).

**Por qué el idioma se elige y no se detecta**: `R` es rey en español y torre en inglés, y
las dos lecturas pueden ser legales en la misma posición. Adivinar daría movimientos
silenciosamente equivocados, así que la simulación lo pregunta al arrancar.

## Tests

`tests/test_partida.py` (la regla de las dos condiciones, los mensajes de bloqueo, mate y
timeout), `tests/test_reloj.py` y `tests/test_notacion.py`. Sin hardware — ver
[`testing.md`](./testing.md).
