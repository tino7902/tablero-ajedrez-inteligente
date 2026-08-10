# Tests: `logica/` y `motor/`

`pytest` se agregó como dev dependency (`uv add --dev pytest`, ver
[`docs/pyproject.md`](./pyproject.md)). Los tests viven en `tablero/tests/` y se
corren desde `tablero/`:

```bash
cd tablero
uv run pytest tests/test_logica.py tests/test_motor.py -v
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

## Qué no está cubierto todavía

`test_sensores.py` sigue vacío: `io/sensores.py` no está implementado (requiere
hardware real, fuera del alcance de estos módulos — ver el boundary documentado en
`CLAUDE.md`).
