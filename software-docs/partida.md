# `logica/partida.py`, `partida_fisica.py`, `partida_magnus.py`, `reloj.py` y `notacion.py` — la capa de partida

Los módulos que convierten "hay reglas de ajedrez" ([`logica.md`](./logica.md)) en "hay una
partida en curso": quién tiene el turno, cuánto tiempo le queda, qué pasa cuando alguien
intenta un movimiento y cuándo pasa el turno de verdad.

Ninguno depende de hardware. `Partida` la usan la simulación por terminal
([`simulacion.md`](./simulacion.md)) y el tablero real, a través de `PartidaFisica`
([`juego.md`](./juego.md)): la regla y el registro son los mismos en los dos casos. El modo
contra la máquina, `PartidaVsMagnus`, compone `PartidaFisica` (ver
[`vs-magnus.md`](./vs-magnus.md)).

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
| `Partida(*, segundos_por_jugador, idioma, fen, registro, fuente_tiempo)` | Arranca una partida; `segundos_por_jugador=None` es sin límite de tiempo (vs Magnus); `fuente_tiempo` se inyecta en los tests |
| `.intentar_movimiento(texto)` | Procesa un movimiento tipeado → `ResultadoJugada` |
| `.intentar_jugada(movimiento)` | Lo mismo con un `chess.Move` ya resuelto (el de los sensores); en el registro queda en UCI (`intenta 'e2e4'`) |
| `.pulsar_boton(color)` | Procesa el botón del reloj de `color` → `ResultadoBoton` |
| `.actualizar_tiempo()` / `.avanzar_tiempo(seg)` | Descuenta tiempo real / simulado; `True` si recién se agotó. Con la partida terminada, `actualizar_tiempo` no descuenta nada: el reloj queda congelado en el final |
| `.rendirse(color)` | `color` abandona: termina con motivo `"rendición"`, el resultado a favor del otro y el registro cerrado. Con la partida ya terminada no hace nada |
| `.finalizar(motivo)` | Cierra la partida y su registro; idempotente. Un `finalizar()` sin más deja el resultado en `*` |
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

- **El board cambia de turno antes que el reloj.** Un movimiento tipeado se aplica al
  `chess.Board` en el acto, porque el board es lo que valida la posición. El turno que
  percibe el jugador es el del reloj, que solo avanza con el botón: ese desfase *es* la
  condición 2 pendiente. Con el tablero físico ese desfase no existe, porque
  `PartidaFisica` aplica la jugada y aprieta el reloj juntos (ver más abajo).
- **Mate y tablas no esperan el botón.** Si el movimiento termina la partida, no tiene
  sentido dejarla trabada esperando una pulsación.
- **"Es del otro color" se distingue de "es ilegal"** probando el mismo texto sobre una
  copia del board con el turno invertido. Es solo para el mensaje: si el intento falla, se
  cae al mensaje genérico de ilegal.

## `logica/partida_fisica.py`

`PartidaFisica` es la partida en el tablero físico: compone `Partida` con el
`RastreadorMovimientos` de [`eventos.py`](./eventos.md) sobre el mismo tablero lógico. Las
jugadas no se tipean: las arma el jugador con las piezas, y **cuentan al apretar el botón
del reloj**.

- `procesar_ocupacion(ocupacion)` interpreta cada lectura de los sensores y la guarda. No
  aplica nada.
- `pulsar_boton(color)`: si es el botón de quien tiene el turno y la lectura es una `JUGADA`,
  llama a `Partida.intentar_jugada` y enseguida a `Partida.pulsar_boton`. Si no, llama solo a
  `Partida.pulsar_boton`, que lo ignora con su motivo, y el resultado agrega qué ve el
  tablero ("no es una jugada legal: falta pieza en e2; sobra pieza en d4").

| Método/propiedad | Qué hace |
|---|---|
| `PartidaFisica(*, segundos_por_jugador, fen, registro, fuente_tiempo)` | Arranca la partida; asume que las piezas ya están bien puestas |
| `.procesar_ocupacion(ocupacion)` | Interpreta una lectura → `Lectura` |
| `.pulsar_boton(color)` | Confirma la jugada armada, si hay una legal → `ResultadoConfirmacion` (`boton`, `lectura`, `jugada`, `motivo`, `paso_turno`) |
| `.lectura` / `.marcas()` / `.describir()` | Última lectura, sus marcas para los LEDs y su texto en castellano |
| `.partida` / `.board` / `.terminada` | La `Partida` de adentro y su tablero |
| `.actualizar_tiempo()` / `.finalizar(motivo)` | Delegan en `Partida` |
| `describir_lectura(lectura, board)`, `describir_jugada(board, jugada)`, `describir_diferencias(faltan, sobran)` | Textos para mostrar: "caballo g1→f3 (Nf3), falta apretar el reloj", "falta pieza en e2; sobra pieza en d4" |

Por qué la jugada se confirma recién con el botón:

- **El enroque y las capturas pasan por posiciones intermedias** (la torre ya en f1 con el
  rey en e1; el atacante en la mano con la pieza capturada ya afuera). Si la jugada se
  aplicara apenas se detecta, un enroque empezado por la torre quedaría registrado como una
  jugada de torre.
- **La regla de las dos condiciones se cumple sola:** `intentar_jugada` y `pulsar_boton` se
  llaman juntas, en ese orden. Por eso con el tablero físico nunca aparece
  `BLOQUEADO_FALTA_RELOJ`.
- **El tiempo le corre a quien mueve hasta que aprieta**, igual que con un reloj de verdad.
- **Si el rival toca una pieza antes de que el otro apriete**, la posición deja de ser una
  jugada legal y el botón se rechaza hasta que se reponga.

## `logica/partida_magnus.py`

`PartidaVsMagnus` es la partida contra Stockfish en el tablero físico, sin límite de tiempo.
Compone `PartidaFisica` y **no importa `motor/`**: `io/juego.py` le pide la jugada al motor
en otro hilo con `board_para_motor()` y se la pasa con `recibir_jugada_motor()`. La jugada
de Magnus se aplica con `Partida.intentar_jugada` y el botón que aprieta el jugador después
de moverla es `Partida.pulsar_boton(color_magnus)`: la regla y el registro no cambian.

Las fases (`Fase`: `TURNO_HUMANO`, `MAGNUS_PENSANDO`, `MOVER_MAGNUS`, `TERMINADA`) se deducen
de `Partida`, no se guardan aparte. La API completa, las marcas de los LEDs y los textos
están en [`vs-magnus.md`](./vs-magnus.md).
## `logica/reloj.py`

`RelojAjedrez` es el **único** reloj del proyecto: lo usan `Partida` y también la pantalla
PvP de `io/menus.py`, que antes descontaba el tiempo a mano en su loop de pygame (ver
[`menus.md`](./menus.md)).

| Método/propiedad | Qué hace |
|---|---|
| `RelojAjedrez(segundos_por_jugador, fuente_tiempo=time.monotonic)` | Arranca los dos temporizadores, turno en blancas. Con `None`, sin límite: nunca se agota |
| `.turno` | Color cuyo reloj corre; queda congelado en el perdedor al agotarse |
| `.restante(color)` / `.tiempo_agotado` / `.perdedor` | Estado del reloj; `restante` es `None` sin límite |
| `.usado(color)` / `.duracion` / `.sin_limite` | Segundos usados por cada lado (con límite o sin él), su suma y si el reloj no tiene límite |
| `.actualizar()` | Descuenta el tiempo real desde la última llamada; `True` solo la vez que se agota |
| `.avanzar(segundos)` | Descuenta tiempo simulado (el comando `esperar` de la simulación) |
| `.pulsar(color)` | Pasa el turno si `color` es quien tiene el reloj corriendo |
| `formatear_tiempo(segundos)` | `"MM:SS"`, redondeando hacia arriba (cuenta regresiva) |
| `formatear_duracion(segundos)` | `"MM:SS"`, truncando, y los minutos pasan de 59 (cronómetro de vs Magnus) |

Notas:

- **No conoce la regla de las dos condiciones**: solo mide tiempo y cambia de turno cuando
  se lo piden. Eso lo decide `Partida`. Así el mismo reloj le sirve a `io/menus.py`, que
  todavía no tiene sensores y pasa el turno con el botón solo.
- **La fuente de tiempo es inyectable**, que es lo que hace deterministas los tests (ver la
  fixture `tiempo` en `tests/conftest.py`).
- **`formatear_tiempo` redondea hacia arriba** para que una partida de 5 minutos muestre
  `05:00` al arrancar y `00:00` recién cuando el tiempo se acabó de verdad, como un reloj
  de ajedrez comercial. `formatear_duracion` hace lo contrario: un cronómetro que cuenta
  para arriba muestra `00:00` al arrancar.
- **Sin límite es el mismo reloj.** `Partida.turno` sale del reloj, así que un reloj que
  nunca se agota mantiene la misma API y de paso da el cronómetro de vs Magnus.

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

`tests/test_partida.py` (la regla de las dos condiciones, los mensajes de bloqueo, mate,
timeout, `intentar_jugada`, sin límite y rendición), `tests/test_partida_fisica.py` (la
jugada cuenta al apretar el botón), `tests/test_partida_magnus.py` (vs Magnus),
`tests/test_reloj.py` y `tests/test_notacion.py`. Sin hardware — ver
[`testing.md`](./testing.md).
