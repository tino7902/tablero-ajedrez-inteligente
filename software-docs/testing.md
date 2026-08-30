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
encuentra un mate en 1 conocido, el motor se puede cerrar sin excepciones. Los tiempos
por jugada se mantienen bajos (0.1-0.2s) porque ninguna de las posiciones usadas
necesita más tiempo para resolverse — importante para que la suite siga siendo rápida.

## `test_eventos.py`

Tests de `RastreadorMovimientos` ([`eventos.md`](./eventos.md)). No requieren hardware ni
binarios externos — las lecturas de sensores se simulan a mano como
`frozenset[chess.Square]`.

Casos cubiertos: el ejemplo original completo (pieza levantada → colocación ilegal
rechazada → corrección → movimiento legal aplicado), movimiento legal directo, cancelación
por pieza repuesta, enroque y captura rechazados explícitamente (incluida la secuencia
física completa de una captura, para no quedar colgado en silencio), promoción resuelta a
dama, diffs inesperados (múltiples casillas a la vez, pieza del color equivocado), y
lecturas duplicadas sin evento.

## `test_reloj.py`

Tests de `RelojAjedrez` ([`partida.md`](./partida.md#logicarelojpy)). No requieren
hardware: el paso del tiempo se controla con la fixture `tiempo` (`RelojFalso`, en
`tests/conftest.py`), una fuente de tiempo falsa que se avanza a mano — así los tests son
deterministas y no tienen que dormir.

Casos cubiertos: solo descuenta del lado activo, el turno cambia al pulsar, el botón del
jugador que no tiene el turno no hace nada, `avanzar()` no cobra dos veces el tiempo real,
al agotarse queda congelado en el perdedor y deja de descontar, el aviso de tiempo agotado
llega una sola vez, y el formato `MM:SS`.

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
esperar el botón; y arranque desde un FEN con el reloj en el color que mueve.

## `test_registro.py`

Tests de `RegistroPartida` ([`registro.md`](./registro.md)). Sin hardware: todo se escribe
en el `tmp_path` de pytest, nunca en el `registros/` real.

Casos cubiertos: se crean los dos archivos; el PGN releído con `chess.pgn.read_game` trae
los movimientos, el `Result` y el `Termination` correctos; el PGN se escribe de a poco (no
recién al final); la partida abandonada queda en `*`; el log detalla intentos, bloqueos,
botones ignorados, cambios de turno con el estado del reloj y el tiempo agotado; la
rotación deja 15 PGN y 5 logs borrando los más viejos; dos partidas del mismo segundo no se
pisan; y cerrar dos veces no duplica nada.

## Qué no está cubierto todavía

`test_sensores.py` sigue vacío: `io/sensores.py` necesita hardware real para probarse de
forma significativa (ver el boundary documentado en `CLAUDE.md`). Tampoco hay tests
automáticos de `tablero/simulacion.py` ni de `io/menus.py`: son capas de entrada/salida
(terminal y pygame) sobre lógica que ya está cubierta por `test_partida.py`,
`test_reloj.py` y `test_registro.py`; se prueban a mano corriéndolas (ver
[`simulacion.md`](./simulacion.md) y [`comandos.md`](./comandos.md)).
