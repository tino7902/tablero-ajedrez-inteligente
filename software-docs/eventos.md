# `logica/eventos.py`

Interpreta las lecturas de los sensores (presencia o ausencia de pieza por casilla, sin
saber qué pieza es): para cada lectura responde qué jugada representa la posición física,
comparándola con el tablero lógico de un `EstadoTablero` ([`logica.md`](./logica.md)).
Además dice qué mostrar en cada casilla (las marcas que pinta `io/juego.py` en los LEDs).

**No aplica nada.** La jugada recién cuenta cuando el jugador aprieta su botón del reloj;
eso lo resuelve [`logica/partida_fisica.py`](./partida.md#logicapartida_fisicapy). Lo usa
`io/juego.py` ([`juego.md`](./juego.md)).

## Por qué no depende de `io/sensores.py`

`eventos.py` define su propia entrada: `Ocupacion = frozenset[chess.Square]`, el conjunto
de casillas ocupadas. `io/sensores.py` la produce a partir de la matriz que manda el Nano
(`sensores.ocupacion(matriz)`), y los tests la arman a mano. Así `logica/` sigue sin
depender del hardware (el boundary documentado en `CLAUDE.md`), y `eventos.py` no cambia si
cambian los sensores (la versión reed produce la misma `Ocupacion`).

## Cómo detecta la jugada

Para cada jugada legal, `ocupacion_tras(board, jugada)` calcula qué casillas quedarían
ocupadas (sobre una copia del tablero). La lectura es esa jugada si la ocupación física
coincide. Esto cubre todos los tipos de jugada sin casos especiales:

| Jugada | Ocupación resultante |
|---|---|
| Normal y promoción | `−origen +destino` |
| Captura | `−origen` (el destino sigue ocupado, ahora por la que capturó) |
| Al paso | `−origen −peón capturado +destino` |
| Enroque | `−rey −torre +rey' +torre'` |

El resultado es una `Lectura`:

| `TipoLectura` | Cuándo |
|---|---|
| `REPOSO` | La posición física coincide con el tablero lógico: no hay nada en curso |
| `JUGADA` | Coincide con una jugada legal. Si es una captura, además se vio vaciarse y volver a ocuparse la casilla capturada (ver abajo) |
| `AMBIGUA` | Coincide con capturas, pero no se vio vaciarse la casilla capturada: la pieza que captura está en la mano, o la captura fue tan rápida que el antirrebote no la vio |
| `INCOMPLETA` | No coincide con ninguna jugada legal: hay una jugada a medio hacer o mal hecha |

Siempre trae `faltan` (casillas que en el tablero lógico tienen pieza y en el físico están
vacías) y `sobran` (al revés); son lo que se le muestra al jugador para corregir.

### Por qué compara la posición final en vez de seguir paso a paso

La versión anterior era una máquina de estados que seguía cada pieza levantada y apoyada.
Funcionaba para movimientos simples, pero el enroque y las capturas pasan por posiciones
intermedias que esa máquina no podía resolver, así que las rechazaba
(`MOVIMIENTO_NO_SOPORTADO`). Además aplicaba la jugada por su cuenta, por fuera de `Partida`,
salteándose la regla del reloj.

Ahora la jugada se confirma con el botón del reloj, así que no hace falta adivinar cuándo
terminó: el jugador puede acomodar las piezas en cualquier orden, y en cada lectura se
reinterpreta todo desde cero. Por ejemplo, en un enroque empezado por la torre, con la torre
ya en f1 la lectura es `JUGADA` de torre (`Rf1`); cuando el rey llega a g1, pasa a ser `O-O`.
La que cuenta es la que está armada cuando se aprieta el botón.

### Capturas

Una captura deja la ocupación `−origen`: la casilla capturada sigue ocupada, ahora por la
pieza que captura. Es exactamente lo que se lee con la pieza que captura **levantada en la
mano**, con la rival todavía en su lugar. Además, las capturas de una misma pieza a casillas
distintas dejan todas la misma ocupación (por ejemplo, un caballo en f3 que puede tomar en
e5 o en g5). Es el único caso en que dos jugadas legales coinciden: dos piezas distintas
tienen distinto origen, y las promociones se juntan en una sola (ver abajo).

Por eso el rastreador recuerda qué casillas se vaciaron y se volvieron a ocupar desde la
última posición de reposo (la casilla capturada se vacía al sacar la pieza rival y se vuelve
a ocupar con la que captura):

- Una captura es `JUGADA` solo si su destino está en ese historial.
- Si hay más de una, gana la casilla que se ocupó más recientemente. Así, si el jugador toca
  una pieza rival, la vuelve a poner y después captura otra, gana la última.
- Si ninguna, la lectura es `AMBIGUA`. Casi siempre es la pieza levantada, y se muestran
  todos sus destinos, no solo las capturas. También pasa si la captura fue tan rápida que
  el antirrebote (`HALL_LECTURAS_ESTABLES`) no llegó a ver vacía la casilla: el botón se
  ignora con "falta pieza en e4 (si ya capturaste en d5, levantá y volvé a apoyar la pieza
  que capturó)", y eso lo resuelve.

Hasta el 2026-10-22, con una sola captura posible no se miraba el historial. Al levantar la
pieza se tomaba como la captura hecha, y los LEDs mostraban solo esa jugada, en verde, en
vez de todos los destinos. Se vio en la primera partida en el tablero.

El historial se borra cuando la ocupación vuelve a coincidir con el tablero lógico, y cuando
el tablero lógico cambia (después de cada jugada confirmada).

**Limitación conocida:** si el jugador captura en e5, se arrepiente, devuelve el peón a e5
con el caballo en la mano y no captura en otro lado, la posición física es la misma que
"capturó en e5" y gana e5 (es lo último que se ocupó). Por eso la jugada detectada se
muestra antes de apretar el botón, en la terminal y en los LEDs.

### Promoción

Las cuatro promociones dejan la misma ocupación y los sensores no ven qué pieza se apoyó,
así que siempre se asume **dama** (el mismo criterio de la versión anterior). Elegir otra
pieza queda para cuando haya pantalla táctil en la partida.

## Marcas para los LEDs

`marcas(lectura, board) -> dict[chess.Square, Marca]` dice qué mostrar en cada casilla; los
colores los elige `io/juego.py`. Es una función pura, testeada en `tests/test_eventos.py`.

| Situación | Marcas |
|---|---|
| `REPOSO` | Ninguna |
| `JUGADA` | `JUGADA` en todas las casillas que toca: origen y destino, más la torre en el enroque y el peón capturado al paso |
| `INCOMPLETA` y `AMBIGUA` | Las jugadas compatibles con lo que se movió (las que tocan todas las casillas cambiadas) muestran sus orígenes (`ORIGEN`) y el resto de sus casillas (`DESTINO`). Si no hay ninguna (por ejemplo, la pieza se apoyó en una casilla ilegal), se muestran las jugadas de las piezas propias levantadas. Lo que quede sin explicar es `FALTA` o `SOBRA` |

Ejemplos: al levantar el caballo de g1 se ven g1 (`ORIGEN`), f3 y h3 (`DESTINO`). Si se lo
apoya en g3, g3 aparece como `SOBRA`. Si se saca primero el peón rival que se va a capturar,
se ven el atacante (`ORIGEN`) y la casilla capturada (`DESTINO`). Con el rey en g1 y la torre
en la mano a mitad de un enroque se ven e1 y h1 (`ORIGEN`) y g1 y f1 (`DESTINO`).

## API

| Función/clase | Qué hace |
|---|---|
| `casillas_ocupadas(board)` | `Ocupacion` de un `chess.Board` |
| `ocupacion_tras(board, jugada)` | `Ocupacion` después de jugar `jugada` |
| `casillas_tocadas(board, jugada)` | `(todas, origenes)`: las casillas que cambian con la jugada, y cuáles de ellas se vacían de piezas del que mueve |
| `RastreadorMovimientos(estado)` | Interpreta lecturas contra `estado.board`, sin modificarlo |
| `.procesar_ocupacion(ocupacion)` | Devuelve la `Lectura` de esa ocupación (siempre, nunca `None`) |
| `.reiniciar()` | Olvida el historial de lecturas |
| `Lectura` | `tipo`, `ocupacion`, `movimiento`, `candidatos`, `faltan`, `sobran` |
| `marcas(lectura, board)` | `dict[chess.Square, Marca]` (`ORIGEN`, `DESTINO`, `JUGADA`, `FALTA`, `SOBRA`) |
| `Marca.MAGNUS_ORIGEN` / `Marca.MAGNUS_DESTINO` | No las devuelve `marcas()`: son de la jugada de Magnus, que hay que hacer a mano, y las calcula `PartidaVsMagnus` (ver [`vs-magnus.md`](./vs-magnus.md)) |

Cada pieza levantada y apoyada se loguea (logger `tablero.logica.eventos`, nivel `INFO`), con
el número de jugada y el color que tiene el turno:

```
Jugada 1 (blancas): se levanta peón de e2
Jugada 1 (blancas): aparece pieza en e4
Jugada 1 (blancas): posición de e4, falta el botón del reloj
```

## Fuera de alcance (todavía)

- **Posición inicial incorrecta:** el rastreador no la valida; si no coincide, la lectura es
  `INCOMPLETA` con lo que falta y sobra. `io/juego.py` espera a que esté bien antes de
  arrancar la partida.
- **Elegir la pieza de la promoción:** siempre dama (ver arriba).
- **La limitación del desempate de capturas** descrita arriba.

## Tests

`tablero/tests/test_eventos.py`: no requiere hardware ni binarios externos. Una "mano" levanta
y apoya piezas y le pasa cada ocupación al rastreador. Cubre:

- movimiento normal (sin aplicarse), pieza repuesta, casilla ilegal y corrección, cambio de
  idea antes del botón, pieza rival levantada;
- captura en los dos órdenes, desempate por historial, la ocupada más recientemente, y
  `AMBIGUA` resuelta al retocar la pieza;
- enroque corto (empezando por el rey o por la torre) y largo, al paso en los dos órdenes,
  promoción a dama con y sin captura;
- marcas de cada situación, y vuelta a `REPOSO` cuando se aplica la jugada.

```bash
cd tablero && uv run pytest tests/test_eventos.py -v
```
