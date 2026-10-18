# `io/juego.py` — partida en el tablero físico

El programa que une todo en la Raspberry: lee la matriz Hall (vía el Nano), los botones del
reloj y pinta los LEDs, mientras [`logica/partida_fisica.py`](./partida.md#logicapartida_fisicapy)
decide qué pasa. Por ahora corre por terminal (SSH); la pantalla táctil se conecta después.

## La regla

Las jugadas se arman con las piezas y **cuentan al apretar el botón del reloj**. Hasta ese
momento se pueden acomodar en cualquier orden: el enroque empezando por el rey o por la
torre, la captura sacando primero cualquiera de las dos piezas, o cambiar de idea. Al
apretar:

- si la posición es una jugada legal de quien tiene el turno, se aplica y pasa el turno;
- si no, el botón no hace nada, y la terminal y los LEDs muestran qué corregir.

La promoción es siempre a dama: los sensores no ven qué pieza se apoya. Detalle de cómo se
detecta cada jugada en [`eventos.md`](./eventos.md).

## Uso

En la Pi, desde `tablero/`:

```bash
uv run python -m tablero.io.juego                     # 5 minutos por jugador, posición inicial
uv run python -m tablero.io.juego --minutos 3
uv run python -m tablero.io.juego --fen "<FEN>"       # arrancar desde otra posición (ver abajo)
uv run python -m tablero.io.juego --sin-leds          # sin LEDs (y sin sudo)
uv run python -m tablero.io.juego --sin-registro      # no escribe en registros/
uv run python -m tablero.io.juego -v                  # loguea cada pieza que se levanta o apoya
```

Usa los LEDs, así que necesita root: igual que `prueba_tablero`, se relanza solo con `sudo`
(con `--sin-leds` no hace falta). `--brillo` cambia el brillo (0-255; por defecto
`LED_BRILLO`).

1. **Arranque:** "Acomodá las piezas". Los LEDs marcan en rojo dónde falta una pieza y en
   amarillo dónde sobra. Cuando la posición coincide, se prende todo en verde y pide
   apretar cualquier botón del reloj. El reloj arranca recién ahí.
2. **Partida:** cada cambio en las piezas se muestra en la terminal ("blancas: caballo
   g1→f3 (Nf3), falta apretar el reloj") y en los LEDs. Cada botón muestra si pasó el turno
   o por qué no.
3. **Fin:** mate, tablas o tiempo agotado, o Ctrl+C (queda como abandonada). Se apagan los
   LEDs y se liberan el puerto del Nano y los botones.

`boton_1` es el de blancas y `boton_2` el de negras, igual que en `io/menus.py`.

## Posición de arranque (`--fen`)

Sin `--fen` se arranca desde la posición inicial. Con `--fen`, desde la posición que se le
pase en **FEN** (notación Forsyth-Edwards), el formato estándar para escribir una posición
en una línea. La lee python-chess (`chess.Board(fen)`), y vale lo mismo para
`tablero.simulacion --fen`. Hay que ponerla **entre comillas**, porque tiene espacios.

La posición inicial en FEN es:

```
rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
```

Son seis campos separados por espacios:

| Campo | En el ejemplo | Qué es |
|---|---|---|
| Piezas | `rnbqkbnr/…/RNBQKBNR` | Las 8 filas, **de la 8 a la 1**, separadas por `/`. Cada fila va de la columna a a la h |
| Turno | `w` | `w` = juegan blancas, `b` = juegan negras |
| Enroques | `KQkq` | Los que siguen disponibles: `K` corto y `Q` largo de blancas, `k` y `q` de negras. `-` si no queda ninguno |
| Al paso | `-` | La casilla donde se puede capturar al paso (por ejemplo `e3` justo después de e2-e4), o `-` |
| Medias jugadas | `0` | Para la regla de los 50 movimientos: medias jugadas desde la última captura o jugada de peón |
| Número de jugada | `1` | Desde qué número se cuentan las jugadas. Sube después de cada jugada de negras |

En el campo de piezas, cada pieza es una letra **en inglés**, aunque la simulación use
notación en castellano. Las mayúsculas son blancas y las minúsculas, negras:

| `K` / `k` | `Q` / `q` | `R` / `r` | `B` / `b` | `N` / `n` | `P` / `p` |
|---|---|---|---|---|---|
| rey | dama | torre | alfil | caballo | peón |

Un número es esa cantidad de casillas vacías seguidas, y cada fila tiene que sumar 8. Por
ejemplo, `8` es una fila vacía, y `4P3` son 4 vacías (a–d), un peón blanco en e y 3 vacías
(f–h). Así, `8/4p3/8/8/8/8/4P3/8 w - - 0 1` es un peón negro en e7 y uno blanco en e2, y
juegan blancas.

Detalles:

- **Solo el primer campo es obligatorio.** Lo que falte toma `w - - 0 1`:
  `--fen "8/4p3/8/8/8/8/4P3/8"` es lo mismo que el ejemplo anterior.
- **No hace falta que haya reyes.** python-chess genera las jugadas igual, y por eso
  alcanza con pocos imanes (ver abajo). Eso sí: el bando que no tiene rey no puede recibir
  jaque, así que a ese bando no se le puede dar mate.
- **Enroques y al paso imposibles se descartan sin aviso.** Por ejemplo, `K` sin el rey en
  e1 y la torre en h1.
- **Si el FEN está mal escrito, el programa no arranca**: `FEN inválido: …`, con el mensaje
  de python-chess en inglés. Por ejemplo, `expected 8 rows` si faltan filas, o `invalid
  character` si se usó una letra en castellano (`T` en vez de `R`).

Qué hace el programa con el FEN:

- **Antes de arrancar**, espera a que las piezas físicas ocupen exactamente las casillas
  del FEN (como siempre: rojo falta, amarillo sobra). Los sensores no distinguen piezas, así
  que cualquier imán sirve: el programa asume que en cada casilla está la pieza que dice el
  FEN.
- **El reloj** arranca con el turno del FEN: con `b`, corre primero el de negras.
- **El PGN del registro** guarda el FEN (`[FEN "…"]` y `[SetUp "1"]`) y numera las jugadas
  desde el número del FEN, así Lichess lo abre en esa posición.

Para armar un FEN sin escribirlo a mano:

- Con el editor de Lichess (lichess.org/editor): se ponen las piezas con el mouse y se
  copia el FEN que aparece abajo.
- Con la simulación: se juegan unas jugadas y el comando `fen` imprime el FEN de la
  posición actual, listo para pasárselo a `juego --fen`.

## LEDs

| Color | Marca | Significa |
|---|---|---|
| Azul | `ORIGEN` | La pieza que se está moviendo (o las dos del enroque) |
| Blanco tenue | `DESTINO` | Adónde puede ir, o qué pieza rival puede capturar |
| Verde | `JUGADA` | La jugada armada, lista para confirmar con el botón |
| Rojo | `FALTA` | Debería haber una pieza y no hay |
| Amarillo | `SOBRA` | Hay una pieza que no debería estar (por ejemplo, en una casilla ilegal) |

Las marcas las calcula `eventos.marcas()` (lógica pura, testeada); `io/juego.py` solo elige
los colores. Se recalculan solo cuando cambia la lectura.

## Registro

Cada partida queda en `tablero/registros/` (PGN + log detallado, ver
[`registro.md`](./registro.md)), con `modo=tablero`. Las jugadas aparecen en UCI en el log
(`intenta 'e1g1' → ACEPTADO O-O`). Como el programa corre con `sudo`, al terminar los
archivos (y las carpetas) se le devuelven al usuario que lo lanzó (`SUDO_UID`/`SUDO_GID`).
Si no, la simulación, que corre sin root, no podría escribir ni rotar los registros después.

## Cómo probarlo sin las 32 piezas

`--fen` arranca desde cualquier posición ([formato](#posición-de-arranque---fen)), y python-chess
genera jugadas aunque no haya reyes. Así alcanza con pocos imanes (con el polo sur hacia el sensor):

| Imanes | FEN | Qué probar |
|---|---|---|
| 2 (e2, e7) | `8/4p3/8/8/8/8/4P3/8 w - - 0 1` | Movimiento, botón sin mover, casilla ilegal, botón del rival |
| 3 (e1, h1, e8) | `4k3/8/8/8/8/8/8/4K2R w K - 0 1` | Enroque corto, empezando por el rey o por la torre |
| 2 (e4, d5) | `8/8/8/3p4/4P3/8/8/8 w - - 0 1` | Captura `exd5`, sacando primero cualquiera de las dos |

Con la FEN de 2 peones, una prueba completa:

1. `uv run python -m tablero.io.juego --fen "8/4p3/8/8/8/8/4P3/8 w - - 0 1"` con los imanes en
   e2 y e7; esperar "Posición lista" y apretar un botón.
2. Apretar `boton_1` sin mover: `⛔ ... no se movió ninguna pieza`.
3. Levantar e2: e2 en azul, e3 y e4 en blanco tenue.
4. Apoyarlo en d4: d4 en amarillo. Apretar `boton_1`: rechazado ("sobra pieza en d4").
5. Pasarlo a e4: e2 y e4 en verde. Apretar `boton_2`: no hace nada (no es su turno).
   Apretar `boton_1`: `✓ blancas: e4` y turno de negras.
6. Lo mismo con las negras (e7 → e5, `boton_2`).

Si algo no detecta, revisar primero con `prueba_tablero espejo` que los imanes se lean
([`prueba-tablero.md`](./prueba-tablero.md)).

## Pendiente

- Probarlo en la Pi (botones, matriz y LEDs juntos en un mismo programa es la primera vez).
- Una partida completa con las 32 piezas, después de `sensores calibrar`.
- Conectarlo a la pantalla PvP de `io/menus.py`: `PartidaFisica` ya tiene todo lo que hace
  falta; queda leer el Nano sin trabar el loop de pygame.
