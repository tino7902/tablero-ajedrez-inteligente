# Tests: `logica/` y `motor/`

`pytest` se agregó como dev dependency (`uv add --dev pytest`, ver
[`docs/pyproject.md`](./pyproject.md)). Los tests viven en `tablero/tests/` y se
corren desde `tablero/`:

```bash
cd tablero
uv run pytest -v            # todo (test_motor.py se saltea solo si falta stockfish)
```

## `test_logica.py`

Tests de `EstadoTablero` ([`docs/logica.md`](./logica.md)). No requieren hardware ni
binarios externos — corren en cualquier máquina, siempre. Las posiciones no triviales
(ahogado, al paso, enroque, promoción) se arman directo por FEN en vez de jugarlas
desde la posición inicial, para no depender de secuencias largas de movimientos.

Casos cubiertos: movimientos legales/ilegales, mate del pastor (jaque mate real vía una
partida jugada), ahogado, captura al paso, enroque corto, promoción a dama,
deshacer/reiniciar.

## `test_motor.py`

Tests de `MotorStockfish` ([`docs/motor.md`](./motor.md)). Requieren el binario
`stockfish` instalado en el sistema — el módulo completo se saltea con
`pytest.mark.skipif(shutil.which("stockfish") is None, ...)` para no romper en
máquinas o entornos de CI que no lo tengan instalado.

Casos cubiertos: la jugada devuelta desde la posición inicial es legal, el motor
encuentra un mate en 1 conocido, el motor se puede cerrar sin excepciones, cada nivel de
`config.NIVELES_MAGNUS` configura `Skill Level` y devuelve una jugada legal, un nivel
desconocido da `ValueError`, y el proceso corre en su propio grupo (para que un Ctrl+C no
lo mate). Los tiempos por jugada se mantienen bajos (0.1-0.2s) porque ninguna de las
posiciones usadas necesita más tiempo para resolverse — importante para que la suite siga
siendo rápida. Los niveles usan los suyos (el difícil, 1 s).

## `test_config.py`

Tests de `config.buscar_stockfish` ([`config.md`](./config.md)). Sin Stockfish: se
reemplazan `shutil.which` y `os.access`. Casos cubiertos: primero el PATH, después
`/usr/games/stockfish` (el de `apt`, que el PATH de `sudo` no incluye), y si no hay
ninguno, el nombre solo.

## `test_eventos.py`

Tests de `RastreadorMovimientos` y `marcas` ([`eventos.md`](./eventos.md)). No requieren
hardware ni binarios externos: una "mano" levanta y apoya piezas y le pasa cada ocupación
(`frozenset[chess.Square]`) al rastreador.

Casos cubiertos: movimiento normal detectado sin aplicarse, pieza repuesta, casilla ilegal
y corrección, cambio de idea antes del botón, pieza rival levantada; captura en los dos
órdenes, desempate de capturas de una misma pieza (por historial, la ocupada más
recientemente, y `AMBIGUA` resuelta al retocar la pieza); enroque corto empezando por el
rey o por la torre y enroque largo; al paso en los dos órdenes; promoción a dama con y sin
captura; las marcas de cada situación; y vuelta a `REPOSO` cuando se aplica la jugada.

## `test_reloj.py`

Tests de `RelojAjedrez` ([`partida.md`](./partida.md#logicarelojpy)). No requieren
hardware: el paso del tiempo se controla con la fixture `tiempo` (`RelojFalso`, en
`tests/conftest.py`), una fuente de tiempo falsa que se avanza a mano — así los tests son
deterministas y no tienen que dormir.

Casos cubiertos: solo descuenta del lado activo, el turno cambia al pulsar, el botón del
jugador que no tiene el turno no hace nada, `avanzar()` no cobra dos veces el tiempo real,
al agotarse queda congelado en el perdedor y deja de descontar, el aviso de tiempo agotado
llega una sola vez, y el formato `MM:SS`. Sin límite: nunca se agota, `usado` por lado y
`duracion`, y `formatear_duracion` trunca y deja pasar los minutos de 59.

## `test_notacion.py`

Tests de `parsear_movimiento` ([`partida.md`](./partida.md#logicanotacionpy)). Sin
hardware.

Casos cubiertos: SAN español e inglés, UCI, mayúsculas y espacios, enroque en sus tres
escrituras, promoción en SAN y en UCI con letras de cada idioma, la ambigüedad de `R`
(rey en español, torre en inglés), movimientos ambiguos que piden desambiguar, y la
distinción entre "no se entiende" e "ilegal".

## `test_partida.py`

Tests de `Partida` ([`partida.md`](./partida.md)) — el corazón de la regla de las dos
condiciones. Sin hardware, con la fixture `tiempo`.

Casos cubiertos: un movimiento legal se acepta pero **no** pasa el turno; sin apretar el
botón ni el rival ni el mismo jugador pueden mover; apretar sin haber movido no pasa el
turno; el botón del otro jugador se ignora; las dos condiciones juntas sí pasan el turno;
secuencia completa de varias jugadas; movimiento del color equivocado, pieza ausente en el
origen y movimiento imposible, cada uno con su mensaje; el tiempo le corre a quien movió y
no apretó; timeout que termina la partida y bloquea todo; mate del pastor que termina sin
esperar el botón; arranque desde un FEN con el reloj en el color que mueve; e
`intentar_jugada` (un `chess.Move` ya resuelto, el de los sensores) aceptada, ilegal con su
motivo y bloqueada mientras falta el botón. Para vs Magnus: partida sin límite, el reloj
que se congela al terminar, y `rendirse` (resultado a favor del otro, y nada si la partida
ya había terminado).

## `test_partida_fisica.py`

Tests de `PartidaFisica` ([`partida.md`](./partida.md#logicapartida_fisicapy)): la partida
con el tablero físico, donde la jugada cuenta al apretar el reloj. Sin hardware, con una
"mano" que mueve piezas y la fixture `tiempo`.

Casos cubiertos: jugada + botón pasan el turno y la posición física queda como nuevo
reposo; la jugada no se aplica antes del botón; botón sin mover; botón con la pieza en una
casilla ilegal (con el motivo) y después de corregirla; botón del rival; el rival toca una
pieza antes de que el otro apriete; el tiempo corre mientras se acomodan las piezas; mate
del pastor; y una partida corta con captura y enroque, revisando el PGN y el log en un
`tmp_path`.

## `test_partida_magnus.py`

Tests de `PartidaVsMagnus` ([`vs-magnus.md`](./vs-magnus.md)). Sin hardware ni Stockfish:
las jugadas de Magnus las pasa el test con `recibir_jugada_motor`, con la misma "mano" de
`test_partida_fisica.py` y la fixture `tiempo`.

Casos cubiertos: las cuatro fases (con blancas confirma y pasa a `MAGNUS_PENSANDO`, donde
el botón se ignora; con negras arranca pensando); las marcas de cada fase; el botón
apretado justo después de recibir la jugada sin tocar nada (la reinterpretación de la
última lectura); la jugada de Magnus a medio mover, terminada y con otra diferencia aparte;
tu jugada armada encima de la de Magnus sin confirmar; captura, enroque corto y largo, al
paso, subpromoción y promoción con captura de Magnus (marcas, texto y confirmación); el
registro; mate de Magnus (termina sin botón y sigue en los LEDs), mate tuyo, cronómetro
congelado, ahogado, rendición y abandono; `recibir_jugada_motor` fuera de fase o ilegal; los
mensajes finales; los nombres del PGN; y las posiciones que Stockfish no acepta (sin reyes,
el bando que no mueve en jaque).

## `test_simulacion.py`

Tests del modo vs Magnus de `simulacion.py` ([`simulacion.md`](./simulacion.md)), con un
motor falso que devuelve jugadas fijas y lo tipeado reemplazado por `monkeypatch`. Casos
cubiertos: Magnus contesta después de tu Enter y te podés rendir, con negras juega primero
y su jugada se confirma sola, y el mensaje final con un mate tuyo.

## `test_registro.py`

Tests de `RegistroPartida` ([`registro.md`](./registro.md)). Sin hardware: todo se escribe
en el `tmp_path` de pytest, nunca en el `registros/` real.

Casos cubiertos: se crean los dos archivos; el PGN releído con `chess.pgn.read_game` trae
los movimientos, el `Result` y el `Termination` correctos; el PGN se escribe de a poco (no
recién al final); la partida abandonada queda en `*`; el log detalla intentos, bloqueos,
botones ignorados, cambios de turno con el estado del reloj y el tiempo agotado; la
rotación deja 15 PGN y 5 logs borrando los más viejos; dos partidas del mismo segundo no se
pisan; cerrar dos veces no duplica nada; y una partida sin límite (vs Magnus) con
`TimeControl "-"`, los nombres de los jugadores, el tiempo usado en el log y la rendición.

## `test_matriz.py`

Tests de `logica/matriz.py` ([`sensores.md`](./sensores.md#matriz-de-casillas-sensores-hall)), lo
que se hace con las lecturas de la matriz de sensores Hall sin tocar el hardware. Sin hardware:
las lecturas crudas se arman a mano como `MatrizCruda` (8 × 8, `matriz[fila Fk][columna Ck]`), y
las respuestas del Arduino Nano se escriben como el texto que mandaría por el puerto serie.

Casos cubiertos: la validación de `CASILLA_DE_CELDA_HALL` (cantidad de filas, fila corta, nombre
inválido, casilla repetida, mayúsculas y espacios) y que la tabla de `config.py` sea válida, la
conversión de matriz cruda a ocupación con una tabla no identidad, que el bloque que imprime
`mapear` se pueda releer y dé la misma tabla, la detección de cableado en grilla, la elección de
la espera de encendido (incluido ignorar un acierto por debajo de una espera que falló) y la
recomendación de antirrebote a partir de la racha más larga de lecturas falsas.

Del protocolo del Nano ([`firmware-nano.md`](./firmware-nano.md)): reconocer el `LISTO` y su
versión (y no confundirlo con la basura del reset); armar `L <µs>` redondeando la espera al
microsegundo y rechazar esperas fuera de 0–50 ms; decodificar `M …` con los ejemplos del
protocolo (tablero vacío, posición inicial, una pieza en F2/C3), los bits extremos y el hex en
minúscula; rechazar respuestas mal formadas (`ERR …`, 7 o 9 bytes, hex inválido, prefijo
equivocado, basura del reset); y decodificar `C bb` y `A …` (con `-` en las columnas no
analógicas y valores fuera de 0–1023 rechazados). La parte que habla con el puerto
(`io/matriz.py`: plazos, reintentos, errores) no tiene tests automáticos: se prueba en la Pi.

El test de la tabla de `config.py` sirve también en la Raspberry: después de pegar el resultado
de `mapear`, `uv run pytest tests/test_matriz.py -q` confirma que no quedó mal pegada.

## Qué no está cubierto todavía

`test_sensores.py` sigue vacío: `io/sensores.py` (y `io/matriz.py`, `io/sensores_reed.py`,
`io/prueba_tablero.py`) necesitan hardware real para probarse de forma significativa (ver el
boundary documentado en `CLAUDE.md`); lo que no necesita el hardware de la matriz (incluido el
texto del protocolo del Nano) vive en `logica/matriz.py` y está cubierto por `test_matriz.py`. Tampoco hay tests
automáticos del modo normal de `tablero/simulacion.py` (el vs Magnus sí, en
`test_simulacion.py`) ni de `io/menus.py` e `io/juego.py`: son capas de entrada/salida
(terminal, pygame y hardware) sobre lógica que ya está cubierta por `test_partida.py`,
`test_partida_magnus.py`, `test_reloj.py` y `test_registro.py`; se prueban a mano
corriéndolas (ver [`simulacion.md`](./simulacion.md) y [`comandos.md`](./comandos.md)).
