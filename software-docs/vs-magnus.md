# Modo Jugador vs Magnus — diseño

Spec del modo vs-máquina en el tablero físico: el jugador contra Stockfish ("Magnus"), con
sensores, LEDs, botones y registro, igual que el PvP de [`juego.md`](./juego.md), y **sin
límite de tiempo**. Acordado e implementado el 2026-10-18, salvo la pantalla táctil (F).

## Estado

- **Hecho (A–E):** reloj sin límite, rendición y registro sin límite; niveles del motor y
  `STOCKFISH_PATH` con `/usr/games`; `logica/partida_magnus.py` con sus tests;
  `simulacion.py --magnus`, probada en la notebook contra Stockfish; e
  `io/juego.py --magnus`.
- **Falta probar en la Pi** `juego.py --magnus` ([`juego.md`](./juego.md#contra-magnus---magnus)).
- **Pendiente (F):** la pantalla táctil. `io/menus.py` tiene las pantallas de dificultad y
  color, pero la dificultad elegida no se guarda y la pantalla de juego es estática. Va
  junto con la integración de sensores de la pantalla PvP, que tampoco existe todavía.

## Decisiones

| Decisión | Por qué |
|---|---|
| Sin límite de tiempo. El reloj cuenta para arriba el tiempo de cada lado | Lo pidió Tino. `Partida.turno` sale del reloj: un reloj sin límite mantiene la misma API y da el cronómetro gratis |
| Tu jugada se confirma con el botón, como en PvP | Sin botón, una posición intermedia (la torre ya en f1 en un enroque, el atacante levantado en una captura) contaría como jugada |
| La jugada de Magnus también se confirma con el botón, después de moverla en el tablero | Es el mismo gesto que para la propia: nada pasa solo |
| Cualquiera de los dos botones confirma, sea la jugada propia o la de Magnus | No hay reloj que parar y juega una sola persona |
| En pantalla: un recuadro grande con el estado y un cronómetro chico. Al final, un mensaje con la duración | El recuadro es donde se lee la jugada de Magnus |
| Niveles: `Skill Level` de Stockfish más tiempo por jugada, en una tabla de `config.py` | Se afinan jugando, sin tocar código |
| La lógica no importa Stockfish: `io/` corre el motor en un hilo y le pasa la jugada | `logica/` sigue testeable sin el binario, y los LEDs y el Nano no se congelan mientras Magnus piensa |

## Cómo se juega

1. Se elige dificultad y color, y se acomodan las piezas (rojo: falta, amarillo: sobra),
   igual que en PvP. Un botón arranca la partida y el cronómetro.
2. La partida pasa por cuatro fases. Las fases no se guardan aparte: se deducen del estado
   de `Partida` (`turno` y `esperando_boton`).

| Fase | Cuándo | Botón | LEDs | Texto del recuadro |
|---|---|---|---|---|
| `TURNO_HUMANO` | `turno == humano` | Confirma la jugada armada, como en PvP | Las marcas de PvP | "Tu turno" |
| `MAGNUS_PENSANDO` | `turno == magnus` y no hay jugada pendiente | Se ignora | Solo falta/sobra respecto del tablero lógico | "Magnus está pensando…" |
| `MOVER_MAGNUS` | `esperando_boton == magnus` | Confirma si la posición física coincide | La jugada de Magnus (ver abajo) | "Magnus: caballo g8→f6" y "Movelo y apretá un botón" |
| `TERMINADA` | `partida.terminada` | Se ignora | Apagados, salvo una jugada final de Magnus | Mensaje final |

### La jugada de Magnus usa la regla de las dos condiciones

Cuando el motor contesta, la jugada se aplica con `Partida.intentar_jugada`. Desde ahí
`Partida` queda con `esperando_boton == color_magnus`, el mismo estado que deja una jugada
tipeada en la simulación. El botón que aprieta el jugador después de mover la pieza es
`Partida.pulsar_boton(color_magnus)`: lo aprieta "en nombre de Magnus". Así el registro y
la regla no cambian: el log muestra `negras intenta 'g8f6' → ACEPTADO Nf6` y después
`botón negras → TURNO PASADO`.

- **Cuándo cuenta.** El botón confirma solo si la lectura es `REPOSO` contra el tablero
  lógico, que ya incluye la jugada de Magnus (es decir, si la posición física coincide) y,
  si Magnus captura, ya se vio vacía la casilla de la pieza capturada (ver "Capturas").
  - Si no coincide, se ignora con lo que falta: "la jugada de Magnus no está terminada:
    falta pieza en f6; sobra pieza en g8".
  - Si el jugador ya armó su propia jugada encima, también se ignora: "primero hay que
    confirmar la de Magnus".
- **Al recibir la jugada se reinterpreta la última ocupación.** `LectorMatriz.leer()` solo
  devuelve algo cuando la matriz cambia. Sin reinterpretar, la última lectura seguiría
  siendo el `REPOSO` de antes de la jugada, y un botón apretado sin tocar nada la
  confirmaría.
- **Capturas.** Levantar la pieza de Magnus con la capturada todavía en su casilla deja la
  misma ocupación que la captura terminada. Al principio no tenía protección (había botón,
  como en PvP), pero en la primera partida en el tablero (2026-10-22) se vio que con la
  pieza en la mano los LEDs ya mostraban la jugada en verde, como terminada. Por eso
  `PartidaVsMagnus` recuerda la casilla capturada hasta que una lectura la ve vacía: hasta
  entonces siguen el violeta y el cian, y el botón se ignora con "sacá la pieza de e4 y
  apoyá ahí la de Magnus (si ya lo hiciste, levantala y volvé a apoyarla)". El paréntesis es
  para cuando la captura fue tan rápida que el antirrebote no vio la casilla vacía. El
  mismo problema en PvP se resuelve en `logica/eventos.py` (ver [`eventos.md`](./eventos.md)).
- **Si la jugada de Magnus termina la partida** (mate o tablas), `Partida` la cierra sin
  esperar el botón. Los LEDs siguen mostrando esa jugada para que se vea el mate.

### LEDs de la jugada de Magnus

Se calculan con `casillas_tocadas(board_antes, jugada)` de `eventos.py`. Son marcas nuevas
de `Marca`, y los colores los elige `io/`:

| Marca | Casillas | Color propuesto |
|---|---|---|
| `MAGNUS_ORIGEN` | Las que tienen que quedar vacías: origen, torre en el enroque, peón capturado al paso | Violeta |
| `MAGNUS_DESTINO` | Adonde va una pieza de Magnus, incluida la casilla de una captura | Cian |
| `JUGADA` | Las mismas casillas, cuando la posición física ya coincide: "apretá el botón" | Verde, como en PvP |
| `FALTA` / `SOBRA` | Cualquier otra diferencia con el tablero lógico | Rojo / amarillo, como en PvP |

Textos:

- Enroque: "Magnus enroca corto: rey e8→g8 y torre h8→f8".
- Captura: "Magnus: alfil b4→c3, captura el caballo". Al paso: "Magnus: peón d4→e3,
  captura al paso el peón de e4".
- Promoción: Magnus puede subpromover y los sensores no ven la pieza, así que el texto dice
  qué poner: "Magnus: peón a2→a1, poné un caballo" (con captura, "…, captura el caballo y
  poné una dama").
- Si la partida terminó con la jugada de Magnus, el texto final la incluye antes del
  mensaje: "Magnus: dama d8→h4" y "Aguantaste 01:23 contra Magnus".

### Mensaje final y cronómetro

La duración es el tiempo total de la partida, desde el botón que la arranca hasta el final
(`usado(blancas) + usado(negras)`). El cronómetro trunca (`00:00` al arrancar), al revés
que la cuenta regresiva de PvP, y se congela cuando la partida termina.

| Final | Mensaje |
|---|---|
| Ganaste (le diste mate) | "¡Derrotaste a Magnus en MM:SS!" |
| Perdiste (mate de Magnus o te rendiste) | "Aguantaste MM:SS contra Magnus" |
| Tablas | "Tablas con Magnus en MM:SS" (propuesta) |
| Abandonada (Ctrl+C, error) | Sin mensaje; queda en el registro |

## Componentes

### A. `motor/stockfish.py`: niveles

- `MotorStockfish(ruta_binario=None, tiempo_por_jugada=None, nivel=None)`. `nivel` es una
  clave de `config.NIVELES_MAGNUS` (`NivelMagnus(nombre, skill_level, segundos_por_jugada)`).
  Al abrir el motor se configura `Skill Level`, y `mejor_movimiento` usa `Limit(time=...)`
  del nivel. El proceso corre en su propio grupo (`setpgrp=True`), así un Ctrl+C no lo mata
  antes de que Python lo cierre.
- Sin `nivel`, se comporta como hoy (fuerza máxima y `STOCKFISH_MOVETIME`), así que
  `test_motor.py` sigue valiendo.
- `config.NIVELES_MAGNUS`, con las claves ASCII porque son flags de la terminal:

| Clave | `Skill Level` | Segundos por jugada |
|---|---|---|
| `facil` | 0 | 0,1 |
| `medio` | 6 | 0,5 |
| `dificil` | 20 | 1,0 |

  Son valores iniciales. `Skill Level 0` anda por los 1300 Elo según la calibración de
  Stockfish; si para un principiante sigue siendo mucho, se puede agregar una dosis de
  jugadas al azar más adelante.
- `config.STOCKFISH_PATH` busca primero en el `PATH` y, si no lo encuentra, prueba
  `/usr/games/stockfish`. Ahí lo instala `apt`, y el `PATH` de `sudo` (`secure_path`)
  normalmente no lo incluye. `io/juego.py` se relanza con `sudo` por los LEDs.

### B. Reloj sin límite, `Partida` y registro

- `RelojAjedrez(segundos_por_jugador=None)`:
  - Nunca se agota.
  - `usado(color)`: segundos usados por cada lado, con límite o sin él.
  - `duracion`: la suma de los dos.
  - `sin_limite`: si el reloj no tiene límite.
  - `restante(color)`: igual que hoy con límite; `None` sin límite.
- `formatear_duracion(segundos)`: `MM:SS` truncado, para el cronómetro. Los minutos pueden
  pasar de 59.
- `Partida` y `PartidaFisica` aceptan `segundos_por_jugador=None`.
- `Partida.actualizar_tiempo()` no descuenta nada si la partida terminó, así el cronómetro
  se congela en el final. En PvP no cambia nada: el loop de `juego.py` ya sale al terminar.
- `Partida.rendirse(color)`: termina con `Termination "rendición"` y el resultado a favor
  del otro color. Hoy `finalizar()` deja `*`. El "¿Rendirse?" de PvP puede usarlo también.
- `RegistroPartida`:
  - Con `segundos_por_jugador=None`, `TimeControl "-"` (el valor del estándar PGN para "sin
    control de tiempo") y `tiempo=sin límite` en el log. El estado del reloj en el log muestra
    el tiempo usado.
  - Nombres de jugador opcionales (`blancas=`, `negras=`), para que `White` y `Black` digan
    "Jugador" y "Magnus (fácil)".
  - `modo="vs_magnus"` ya está en `EVENTOS_POR_MODO`. Nivel y color van en
    `extras_cabecera`.

### C. `logica/partida_magnus.py`: `PartidaVsMagnus`

Es lógica pura: compone `PartidaFisica` y no importa `motor/`.

| Método/propiedad | Qué hace |
|---|---|
| `PartidaVsMagnus(*, color_humano, fen=None, registro=None, fuente_tiempo=...)` | Partida siempre sin límite. Con un `fen` que Stockfish no acepta, `ValueError` (ver `validar_posicion_magnus`) |
| `.fase` | `Fase` (`TURNO_HUMANO`, `MAGNUS_PENSANDO`, `MOVER_MAGNUS`, `TERMINADA`), deducida de `Partida` |
| `.procesar_ocupacion(ocupacion)` / `.lectura` / `.describir()` | Como en `PartidaFisica` |
| `.pulsar_boton()` | Sin color, porque sirve cualquier botón. Según la fase confirma tu jugada, confirma la de Magnus o se ignora con el motivo → `ResultadoPulsacion(fase, confirmado, motivo, jugada)` |
| `.board_para_motor()` | Copia del tablero para que `io/` se la pase al motor en otro hilo |
| `.recibir_jugada_motor(movimiento)` | Aplica la jugada de Magnus y reinterpreta la última ocupación. Si no es la fase `MAGNUS_PENSANDO` o la jugada es ilegal, `ValueError`: sería un bug de quien llama |
| `.marcas()` / `.texto_estado()` | LEDs y recuadro según la fase |
| `.duracion` / `.mensaje_final()` | Cronómetro y mensaje del final |
| `.rendirse()` / `.actualizar_tiempo()` / `.finalizar(motivo)` | Delegan en `Partida` |
| `.partida` / `.board` / `.color_humano` / `.color_magnus` / `.terminada` | Lecturas |

Funciones puras del módulo, que la simulación (E) reutiliza:

- `mensaje_final_magnus(resultado, color_humano, duracion)`: el mensaje final.
- `describir_jugada_magnus(board_antes, jugada)`: la primera línea del texto de
  `MOVER_MAGNUS`.
- `nombres_pgn(color_humano, nombre_nivel)`: `("Jugador", "Magnus (fácil)")` o al revés.
- `validar_posicion_magnus(board)`: `ValueError` si falta un rey o la posición no es legal.
  El PvP acepta posiciones sin reyes para probar con pocos imanes, pero Stockfish no.

### D. `io/juego.py --magnus`

```bash
uv run python -m tablero.io.juego --magnus facil --color negras
```

- `--magnus {facil,medio,dificil}` y `--color {blancas,negras,aleatorio}` (por defecto
  `blancas`). `--minutos` no se puede combinar con `--magnus`. `--fen`, `--sin-leds` y
  `--sin-registro` funcionan igual; con `--fen`, si le toca a Magnus, arranca pensando.
- Reutiliza la espera de la posición inicial, `_Leds`, los botones y el registro. El loop
  de vs-Magnus es una función aparte de la de PvP.
- El motor se abre **antes** de esperar la posición: si falta el binario, falla al arrancar
  y no a mitad de partida.
- El motor corre en un `ThreadPoolExecutor(max_workers=1)`:
  - En `MAGNUS_PENSANDO`, si no hay un pedido en curso, se lanza
    `motor.mejor_movimiento(board_para_motor())`.
  - Cuando `future.done()`, se llama a `recibir_jugada_motor`. El loop nunca se bloquea.
  - Si el motor falla ("Magnus dejó de responder"), la partida termina como abandonada.
- Cualquier botón llama a `pulsar_boton()`.
- Con `--fen`, la posición se valida con `validar_posicion_magnus` antes de abrir el motor.
- Si la partida terminó con la jugada de Magnus, el programa no sale enseguida: los LEDs la
  siguen mostrando (verde cuando ya está hecha) hasta que se apriete un botón. Si no, se
  apagarían al salir y no se vería el mate.
- La terminal muestra cada cambio de texto, el cronómetro en cada cambio de turno y el
  mensaje final.
- Al cerrar, primero se espera la jugada en curso (como mucho, el tiempo del nivel) y
  después se cierra el motor.

### E. `simulacion.py --magnus` (opcional)

Para jugar contra Magnus tipeando, en la notebook, y afinar `NIVELES_MAGNUS` sin armar el
tablero. Usa `Partida` con tu jugada tipeada y Enter, más la jugada de Magnus aplicada y
confirmada directamente: no hay tablero físico que actualizar. Muestra el mismo mensaje
final. Agrega el comando `rendirse`, y el registro queda con `modo=simulacion_magnus`
(ver [`simulacion.md`](./simulacion.md#contra-magnus---magnus)).

### F. Pantalla táctil

Va después, y en buena parte es compartida con PvP: las dos necesitan leer el Nano en un
hilo que publique eventos de pygame (como `menus_gpio.py` con los botones) y una pantalla
de "acomodá las piezas". Lo propio de vs-Magnus:

- Guardar la dificultad: `Boton.dificultad` → `EstadoPartida.dificultad`.
- Pantalla de juego:
  - Arriba, "¡Sos blancas!" y el cronómetro chico donde hoy está "¡Es tu turno!".
  - El recuadro grande con el texto de la fase, en una o dos líneas, y al final el mensaje
    final.
  - Se saca "¡Te quedaste sin tiempo!".
- Sin "Volver" durante la partida: con el touch impreciso
  ([`consideracion-sobre-diseño.md`](./consideracion-sobre-diseño.md)) es fácil abandonar
  sin querer.
- Redibujar cuando cambia el estado y una vez por segundo por el cronómetro, no en cada
  vuelta del loop (por la limitación de KMSDRM de [`menus.md`](./menus.md)).

## Tests

Todos sin hardware ni Stockfish, salvo `test_motor.py`, que se saltea solo si no está el
binario.

- `test_reloj.py`:
  - Sin límite: nunca se agota, `usado` por lado y `duracion`.
  - `formatear_duracion` trunca.
- `test_partida.py`:
  - `segundos_por_jugador=None`.
  - `rendirse` da el resultado correcto.
  - El reloj se congela al terminar.
- `test_registro.py`: `TimeControl "-"` y los nombres en `White`/`Black`.
- `test_partida_magnus.py` (nuevo). Las jugadas de Magnus las pasa el test con
  `recibir_jugada_motor`:
  - Humano con blancas: confirma, pasa a `MAGNUS_PENSANDO` y ahí el botón se ignora.
  - Humano con negras: arranca en `MAGNUS_PENSANDO`.
  - Botón apretado justo después de recibir la jugada, sin tocar nada: se ignora (la
    reinterpretación de la última ocupación).
  - Jugada de Magnus a medio mover: se ignora con lo que falta. Terminada: se confirma.
  - Tu jugada armada encima de la de Magnus sin confirmar: se ignora.
  - Captura, enroque, al paso y subpromoción de Magnus: marcas, texto y confirmación.
  - Mate de Magnus: `TERMINADA` sin botón, "Aguantaste…".
  - Mate tuyo: `TERMINADA` sin pedir jugada al motor, "¡Derrotaste…!".
  - Tablas y rendición.
  - `recibir_jugada_motor` fuera de fase o con una jugada ilegal da `ValueError`.
  - Posiciones que Stockfish no acepta: sin reyes, el bando que no mueve en jaque.
- `test_motor.py`: cada nivel configura `Skill Level` y devuelve una jugada legal, un nivel
  desconocido da `ValueError`, y el proceso corre en su propio grupo.
- `test_config.py` (nuevo): `buscar_stockfish` prueba el PATH y después `/usr/games`.
- `test_simulacion.py` (nuevo): el loop de `simulacion.py --magnus` con un motor falso.

## Fuera de alcance

- Deshacer jugadas, pistas, que Magnus ofrezca tablas o abandone.
- Elegir la pieza de tu promoción: sigue siendo siempre dama.
- Guardar y reanudar partidas, sonido.
- Reloj con límite contra Magnus: si algún día se quiere, `RelojAjedrez` ya lo soporta.

## Orden

1. ✅ B: reloj sin límite, `Partida`, registro.
2. ✅ A: niveles del motor y `STOCKFISH_PATH`.
3. ✅ C: `PartidaVsMagnus` con sus tests.
4. ✅ E: simulación, para afinar los niveles.
5. ✅ D: `juego.py --magnus`. Falta que lo pruebe Tino en la Pi, después de comprobar ahí
   que Stockfish está instalado (`which stockfish || ls -l /usr/games/stockfish`).
6. F: pantalla, junto con la integración de sensores de PvP.

Al implementar cada parte se actualizan sus docs (`partida.md`, `motor.md`, `config.md`,
`registro.md`, `juego.md`, `testing.md`) y `CLAUDE.md`.
