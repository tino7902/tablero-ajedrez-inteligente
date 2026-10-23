# Lo que falta probar en la Pi

Lista de lo que está escrito pero no se probó en la Raspberry, con cómo probarlo. Está en
orden: primero lo que se puede hacer ya con pocos imanes, después lo que necesita las 32
piezas, y al final la pantalla. Cuando algo pasa, se tacha acá y se actualiza el doc del
módulo (y `CLAUDE.md`, donde dice "not yet tested on the Pi").

Estado al 2026-10-23: **todo lo de las secciones 0 a 3 pasó en la Pi** (confirmado por Tino),
incluida la interfaz de la pantalla con el tablero real. Falta el mapeo final, ahora que se
está pegando la estructura definitiva (sección 4), y el arranque automático (sección 5).

Lo que ya estaba probado antes: los botones del reloj, los LEDs (`LED_DE_CASILLA`), el mapeo
de los Hall (`CASILLA_DE_CELDA_HALL`; los dos mapeos se rehicieron el 2026-10-22 con el
tablero girado 90°, y se espejaron a mano porque habían quedado a↔h) y `prueba_tablero
recorrido` y `espejo`.

## 0. Preparación

- [x] **Código en la Pi.** Desde la notebook, con todo commiteado: `pushpi` (hace `git push`
  y `git pull --ff-only` en la Pi; falla si la Pi tiene cambios locales en archivos del repo).
- [x] **Dependencias.** En la Pi, desde `tablero/`: `uv sync`.
- [x] **Stockfish** (solo para lo de Magnus):

  ```bash
  which stockfish || ls -l /usr/games/stockfish    # alguno de los dos tiene que aparecer
  sudo apt install stockfish                       # si no aparece ninguno
  ```

  `apt` lo deja en `/usr/games/stockfish`. `juego.py` corre con `sudo`, y el PATH de `sudo`
  no incluye `/usr/games`, por eso `config.buscar_stockfish` también busca ahí.

Todo lo que sigue se corre por SSH en la Pi, desde `tablero/`, con el Nano enchufado.
`juego.py` se relanza solo con `sudo` por los LEDs.

## 1. Con pocos imanes

### 1.1 `juego.py` PvP: botones, matriz y LEDs juntos

Es la primera vez que los tres andan en un mismo programa. Imanes en e2 y e7:

```bash
uv run python -m tablero.io.juego --fen "8/4p3/8/8/8/8/4P3/8 w - - 0 1"
```

- [x] Arranca, pide acomodar las piezas y con las dos puestas dice "Posición lista". Un botón
  arranca la partida.
- [x] `boton_1` sin mover: `⛔ ... no se movió ninguna pieza`.
- [x] Levantar e2: e2 en azul, e3 y e4 en blanco tenue.
- [x] Apoyarlo en d4: d4 en amarillo. `boton_1`: rechazado ("sobra pieza en d4").
- [x] Pasarlo a e4: e2 y e4 en verde. `boton_2` no hace nada (no es su turno). `boton_1`:
  `✓ blancas: e4` y turno de negras, con el reloj.
- [x] Lo mismo con negras (e7 → e5, `boton_2`).
- [x] Ctrl+C: "Partida abandonada", se apagan los LEDs e imprime dónde quedó el registro.
- [x] El registro es del usuario y no de root:
  `ls -l registros/partidas registros/detalle | tail`.

Si algo no detecta, primero `uv run python -m tablero.io.prueba_tablero espejo` para ver que
los imanes se lean. Detalle en [`juego.md`](./juego.md#cómo-probarlo-sin-las-32-piezas).

### 1.2 `juego.py` PvP: enroque y captura

| Imanes | Comando | Qué probar |
|---|---|---|
| e1, h1, e8 | `uv run python -m tablero.io.juego --fen "4k3/8/8/8/8/8/8/4K2R w K - 0 1"` | Enroque corto, una vez empezando por el rey y otra por la torre: tiene que quedar `O-O` |
| e4, d5 | `uv run python -m tablero.io.juego --fen "8/8/8/3p4/4P3/8/8/8 w - - 0 1"` | Captura `exd5`, sacando primero cualquiera de las dos piezas |

- [x] Enroque empezando por el rey.
- [x] Enroque empezando por la torre.
- [x] Captura sacando primero el peón capturado.
- [x] Captura levantando primero el que captura.

### 1.3 `juego.py --magnus`: el flujo contra la máquina

Con `--magnus` el FEN tiene que tener **los dos reyes** (Stockfish no acepta otra cosa).
Imanes en e1, e2 y e8; Magnus juega con blancas, así que arranca él:

```bash
uv run python -m tablero.io.juego --magnus facil --color negras --fen "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
```

- [x] Arranca sin error de Stockfish (si dice "No se encontró Stockfish", volver al paso 0).
- [x] Con las piezas puestas y un botón: "Magnus está pensando…" y enseguida
  "Magnus: … / Movelo y apretá un botón".
- [x] La jugada de Magnus en violeta (lo que tiene que quedar vacío) y cian (adonde va), y que
  esos colores se distingan bien del azul y del blanco tenue de PvP. Si no se distinguen,
  cambiar `VIOLETA`/`CIAN` en `io/leds.py`.
- [x] Un botón sin mover nada: se ignora con "la jugada de Magnus no está terminada: …".
- [x] Hacerla a medias: el botón sigue ignorándose con lo que falta.
- [x] Hacerla completa: las casillas en verde y un botón la confirma (`✓ Magnus: …`), con el
  cronómetro.
- [x] Tu jugada con **cualquiera** de los dos botones.
- [x] Mientras dice "pensando", el botón se ignora ("Magnus está pensando").
- [x] Tu jugada armada encima de la de Magnus sin confirmar: el botón se ignora con "primero
  hay que confirmar la jugada de Magnus".
- [x] Con `--magnus dificil` (1 s por jugada): mientras piensa, levantar una pieza tiene que
  prenderla en rojo enseguida. Así se ve que el motor no traba el loop.
- [x] Ctrl+C mientras piensa: sale limpio y no queda Stockfish colgado:
  `pgrep -a stockfish` no muestra nada.
- [x] El PGN del registro tiene `TimeControl "-"`, `White "Magnus (fácil)"` y
  `Black "Jugador"`, y la cabecera del log dice `modo=vs_magnus tiempo=sin límite`.

### 1.4 `juego.py --magnus`: mate de Magnus

Si la jugada de Magnus termina la partida, el programa no sale hasta que se apriete un botón,
para que se pueda hacer el mate en el tablero. Imanes en b1, g6 y h8 (Magnus tiene dama y rey
y da mate con `Qb8#`; con `dificil` lo encuentra siempre):

```bash
uv run python -m tablero.io.juego --magnus dificil --color negras --fen "7k/8/6K1/8/8/8/8/1Q6 w - - 0 1"
```

- [x] Imprime "Magnus: dama b1→b8", "Aguantaste 00:0X contra Magnus", "¡Jaque mate! Ganan
  blancas" y "Hacé la jugada de Magnus en el tablero para verla; apretá un botón para salir".
- [x] b1 en violeta y b8 en cian. Al mover el imán de b1 a b8, las dos en verde.
- [x] Un botón termina el programa y apaga los LEDs.

### 1.5 Velocidad de los niveles en la Pi 3B

Los tiempos por jugada se eligieron en la notebook. En la Pi, Stockfish calcula menos en el
mismo tiempo, así que juega más flojo. Lo más cómodo es probarlo con la simulación, sin
tablero:

```bash
uv run simulacion --magnus facil --sin-registro
uv run simulacion --magnus dificil --sin-registro
```

- [x] Cada jugada tarda más o menos el tiempo del nivel (0,1 s, 0,5 s, 1 s).
- [x] Si algún nivel queda demasiado fácil o difícil, ajustar `NIVELES_MAGNUS` en
  `config.py` ([`motor.md`](./motor.md)).

## 2. Con las 32 piezas

### 2.1 Calibrar los Hall

Hecho el 2026-10-22: `HALL_ESPERA_ENCENDIDO = 0.0001` (0,1 ms) y `HALL_LECTURAS_ESTABLES = 3`.

```bash
uv run python -m tablero.io.sensores calibrar     # o directo: prueba_tablero calibrar
```

Se relanza con `sudo` y calibra con los LEDs mostrando en vivo lo que detectan los Hall: verde, bien;
rojo, falta o la pieza no está justo encima del sensor; amarillo, sobra. Tiene tres pasos:
tablero vacío, posición inicial armada y 10 s sin tocar nada.

- [x] Mientras se arma la posición inicial, cada pieza bien puesta pasa a verde.
- [x] Ningún Hall marca pieza con el tablero vacío.
- [x] El paso 2 no da `FALLA` (si da, es eléctrico: `medir`).
- [x] Pegar las dos líneas que imprime en `config.py` y actualizar la tabla de configuración
  de [`sensores.md`](./sensores.md).

Detalle en [`prueba-tablero.md`](./prueba-tablero.md#calibrar) y
[`sensores.md`](./sensores.md#calibrar).

### 2.2 `prueba_tablero inicial`

```bash
uv run python -m tablero.io.prueba_tablero inicial
```

- [x] Con las 32 piezas puestas: "Posición inicial completa (32 piezas)." y todo en verde.
- [x] Sacar una pieza la marca en rojo, y ponerla en una casilla vacía la marca en amarillo.

### 2.3 Partida completa PvP

```bash
uv run python -m tablero.io.juego --minutos 10
```

- [x] Una partida entera, con capturas, enroque y, si se puede, al paso y promoción
  (2026-10-22, después de espejar el mapeo).
- [x] Al levantar una pieza que puede capturar, se ven **todos** sus destinos (en blanco
  tenue, con la captura entre ellos) y no la captura sola en verde. Arreglado el 2026-10-22
  después de la primera partida.
- [x] Ver que ninguna lectura salte sola: piezas que parpadean, jugadas que aparecen sin
  tocar nada. Si pasa, subir `HALL_LECTURAS_ESTABLES`.
- [x] El PGN del registro se abre bien en Lichess.

### 2.4 Partida completa contra Magnus

```bash
uv run python -m tablero.io.juego --magnus facil
uv run python -m tablero.io.juego --magnus medio --color negras
```

- [x] Una partida entera en cada color.
- [x] En una captura de Magnus, con su pieza en la mano y la tuya todavía en el destino,
  siguen el violeta y el cian (no el verde), y el botón dice qué falta.
- [x] Una captura y un enroque de Magnus: los LEDs y el texto ("Magnus enroca corto: rey
  e8→g8 y torre h8→f8") alcanzan para entender qué mover.
- [x] El mensaje final con la duración.

## 3. Pantalla táctil

### 3.1 Calibración del touch

`io/calibracion_touch.py` nunca corrió en el panel. Con el overlay `piscreen` activado:

```bash
uv run python -m tablero.io.calibracion_touch
```

- [x] Aparecen las 5 cruces y se pueden tocar todas.
- [x] Queda `tablero/calibracion_touch.json`.
- [x] `uv run python -m tablero.io.pantalla`: los toques dentro del botón "Tocame" suman siempre,
  también cerca de los bordes del botón. Antes de calibrar, algunos caían afuera.

Detalle en [`pantalla.md`](./pantalla.md#calibración-del-touch).

### 3.2 Jugar desde la pantalla

La interfaz completa con el tablero real (2026-10-22, [`menus.md`](./menus.md)). Antes,
conviene probarla en la notebook con el tablero simulado (ver ahí).

```bash
uv run python -m tablero.io.menus_gpio          # se relanza con sudo por los LEDs
```

- [x] Arranca y muestra el menú; los toques caen en los botones.
- [x] Contra un amigo → 5 minutos → "Acomodá las piezas": cuenta faltan/sobran y los LEDs
  marcan rojo/amarillo. Con todo en su lugar, "¡Posición lista!".
- [x] Un botón del reloj: 3, 2, 1 y la partida. El reloj de blancas corre y se redibuja cada
  segundo sin que la pantalla se ponga en blanco.
- [x] Jugadas con los LEDs de siempre; una jugada ilegal + botón muestra el motivo abajo.
- [x] Tablas: ofrecer de un lado, aceptar del otro → "Tablas por acuerdo". Otra vez:
  ofrecer y jugar sin contestar → la oferta desaparece.
- [x] ¿Rendirse? pide confirmación; "No" vuelve a la partida, "Sí" muestra el final.
- [x] Menú principal desde el final, y una segunda partida arranca reconociendo las piezas.
- [x] Contra Magnus → Fácil → Blancas: "Tu turno", "Magnus está pensando…", su jugada en
  violeta/cian y en el recuadro; el tiempo arriba a la derecha.
- [x] Desenchufar el USB del Nano en una partida: pantalla "Problema con el tablero" y
  Menú principal; al volver a enchufarlo, la partida siguiente anda.
- [x] Ctrl+C: apaga los LEDs, y `ls -l registros/partidas` muestra los PGN del usuario.

## 4. Mapeo final, con la estructura pegada

Al pegar la estructura definitiva cambia dónde queda cada Hall y cada LED respecto de las
casillas, así que se rehacen los dos mapeos (con el servicio parado, si ya está instalado:
`sudo systemctl stop tablero`).

- [ ] `uv run python -m tablero.io.sensores mapear`, con a1 en la esquina oscura a la izquierda
  de las blancas ([`sensores.md`](./sensores.md#mapear)). Pegar `CASILLA_DE_CELDA_HALL` en
  `config.py` desde la notebook (commit + `pushpi`), no en la Pi.
- [ ] `uv run python -m tablero.io.prueba_tablero leds`, con el mapeo nuevo de los Hall ya en la
  Pi. Pegar `LED_DE_CASILLA` igual.
- [ ] `prueba_tablero espejo`: una pieza en la esquina oscura de la izquierda de las blancas
  dice `aparece pieza en a1` (lo único que detecta un mapeo espejado).
- [ ] `prueba_tablero recorrido` termina en `OK` y `prueba_tablero inicial` da
  "Posición inicial completa (32 piezas).".
- [ ] Si cambió la distancia entre imanes y sensores: `prueba_tablero calibrar` de nuevo.

## 5. Arranque automático

Que la Pi prenda directo en el menú, con un servicio de systemd.
Paso a paso en [`arranque-automatico.md`](./arranque-automatico.md).

- [ ] `sudo systemctl start tablero` muestra el menú y `stop` apaga los LEDs en pocos segundos.
- [ ] Después de `sudo reboot`, el menú aparece solo, sin entrar por SSH.
- [ ] Una partida desde el arranque, y los PGN de `registros/partidas` son de magnus.
