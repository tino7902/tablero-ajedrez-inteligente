# `logica/eventos.py`

Traduce lecturas de sensores (presencia/ausencia de pieza por casilla) a `chess.Move`,
comparando snapshots sucesivos de ocupación contra el estado de `EstadoTablero`
([`logica.md`](./logica.md)). Es lo que va a alimentar el bucle principal con eventos de
juego (pieza levantada, movimiento aplicado, movimiento ilegal rechazado, etc.).

## Por qué no depende de `io/sensores.py`

`io/sensores.py` todavía está vacío. En vez de esperar a que exista, `eventos.py` define
su propia entrada — `Ocupacion = frozenset[chess.Square]`, el conjunto de casillas
actualmente ocupadas — y una función pura `casillas_ocupadas(board)` para producirla a
partir de un `chess.Board`. Esto mantiene `logica/` sin dependencia de hardware (boundary
documentado en `CLAUDE.md`) y permite testear todo el módulo con `frozenset`s armados a
mano, sin sensores reales. El día que `io/sensores.py` exista, su trabajo es producir
`Ocupacion` a partir de una lectura real del 74HC138/74HC165 — `eventos.py` no necesita
cambiar.

## Flujo que resuelve

Basado en el ejemplo original: se levanta una pieza (`PIEZA_LEVANTADA`), se coloca en una
casilla candidata. Si el movimiento resultante (origen lógico → casilla candidata) es
ilegal, se rechaza (`MOVIMIENTO_ILEGAL_RECHAZADO`) y se espera a que se retome la misma
pieza — el **origen lógico nunca cambia** mientras el movimiento sigue en curso, aunque la
pieza haya pasado por una casilla intermedia incorrecta. Cuando finalmente se coloca en una
casilla donde el movimiento es legal, se aplica (`MOVIMIENTO_APLICADO`) y el turno pasa al
otro jugador. Si en cambio la pieza se repone en su casilla original, el movimiento se
cancela (`PIEZA_REPUESTA`) sin tocar el estado del juego.

Cada uno de estos cambios se loguea (`logging`, logger `tablero.logica.eventos`) con el
número de jugada y el color a quien le tocaba mover, ej.:

```
Jugada 1 (blancas): se levanta peón de e2
Jugada 1 (blancas): e2→d4 es ILEGAL, se rechaza y se espera corrección
Jugada 1 (blancas): se retoma la pieza en d4
Jugada 1 (blancas): e2→e4 aplicado. Turno pasa a negras.
```

## API

| Función/clase | Qué hace |
|---|---|
| `casillas_ocupadas(board)` | `frozenset[chess.Square]` con las casillas ocupadas de un `chess.Board` |
| `RastreadorMovimientos(estado)` | Envuelve un `EstadoTablero`; asume que la primera `Ocupacion` que se le pasa coincide con `estado.board.occupied` |
| `.procesar_ocupacion(ocupacion)` | Procesa una lectura de sensores; devuelve `EventoTablero \| None` |
| `EventoTablero` | `tipo`, `pieza`, `origen`, `destino`, `turno`, `numero_jugada` |
| `TipoEvento` | `PIEZA_LEVANTADA`, `PIEZA_REPUESTA`, `MOVIMIENTO_ILEGAL_RECHAZADO`, `MOVIMIENTO_APLICADO`, `MOVIMIENTO_NO_SOPORTADO` |

## Decisiones de diseño

- **Resolver el movimiento filtrando `board.legal_moves` en vez de construir `chess.Move` a
  mano**: filtrar por `from_square`/`to_square` sobre los movimientos legales reales evita
  reimplementar detección de promoción (un `chess.Move(e7, e8)` sin `promotion` nunca es
  legal — python-chess solo genera los 4 moves de promoción). La ambigüedad de promoción
  emerge naturalmente como "más de un candidato para el mismo origen/destino"; se resuelve
  eligiendo siempre `promotion == chess.QUEEN` (los sensores no distinguen identidad de
  pieza, mismo argumento que ya usa `estado_tablero.py` para dejar esto fuera de alcance).
- **`fullmove_number` se lee antes de aplicar el movimiento**: python-chess lo incrementa
  recién dentro de `Board.push`, y solo cuando mueve negro. Leerlo antes de
  `aplicar_movimiento` es necesario para loguear correctamente tanto la jugada de blancas
  como la de negras del mismo número.
- **Guard explícito de captura/enroque antes de aplicar**: sin este chequeo
  (`board.is_capture`/`board.is_castling` sobre el movimiento candidato), esos movimientos
  se aplicarían igual — el diff de "una casilla libera, otra ocupa" es indistinguible de un
  movimiento normal en el primer poll — y el tablero lógico quedaría desincronizado del
  físico en silencio. Con el guard se rechazan de forma explícita (`MOVIMIENTO_NO_SOPORTADO`)
  en vez de aplicarse mal.
- **Seguimiento de la "casilla extra vaciada" (`_extra_vacia`)**: una captura física real
  (se levanta la atacante, se retira la pieza capturada, se coloca la atacante) hace que una
  segunda casilla se vacíe mientras la primera pieza sigue en el aire. Sin recordar esa
  casilla, el paso final (colocar la atacante donde estaba la capturada) coincide por
  casualidad con la ocupación esperada del tablero lógico —que nunca se tocó— y el
  rastreador quedaría trabado en curso *sin loguear nada*. Restar `_extra_vacia` de la
  ocupación esperada asegura que ese paso también se detecte y se rechace explícitamente
  (ver `test_captura_fisica_completa_se_rechaza_sin_quedar_en_silencio`).

## Fuera de alcance (todavía)

- **Capturas, enroque y captura al paso**: se detectan y se rechazan explícitamente
  (`MOVIMIENTO_NO_SOPORTADO`), pero no se aplican. Es la limitación más importante de esta
  v1 — cubre poco más que empujes de peón y movimientos de pieza sin captura. Es el
  siguiente paso natural una vez validado este flujo.
- **Polling más lento que un lift+place humano**: la máquina de estados asume que cada lift
  y cada place se observan en snapshots separados. Si el jugador mueve más rápido que la
  frecuencia de escaneo, un solo diff puede traer una casilla que se libera y otra que se
  ocupa al mismo tiempo, lo cual hoy se trata como diff inesperado (no rompe el estado, pero
  exige repetir el movimiento más lento). Queda como precondición de `io/sensores.py`
  (escanear más rápido que un movimiento humano), no resuelta en este módulo.
- **Resincronización/timeout**: si el rastreador queda con un movimiento en curso sin
  resolver, no hay temporizador que lo resetee a reposo — solo warnings logueados en cada
  diff inesperado que llegue mientras tanto.
- **Reconciliación de posición inicial incorrecta**: se asume que el tablero arranca en
  posición correcta y que la primera `Ocupacion` procesada coincide con `estado.board.occupied`.

## Tests

`tablero/tests/test_eventos.py` — no requiere hardware ni binarios externos. Cubre: el
ejemplo original completo (movimiento ilegal → corrección → movimiento legal), un
movimiento legal directo, cancelación por pieza repuesta, enroque y captura rechazados
explícitamente (incluida la secuencia física completa de una captura, ver arriba),
promoción resuelta a dama, diffs inesperados (múltiples casillas, pieza del color
equivocado), y lecturas duplicadas sin evento. Correr con:

```bash
cd tablero && uv run pytest tests/test_eventos.py -v
```
