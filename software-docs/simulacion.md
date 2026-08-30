# `simulacion.py` — modo de prueba de la lógica por terminal

Simulación de una partida completa en la terminal, sin Raspberry y sin ningún tipo de
hardware: se tipea un movimiento y el programa contesta **cómo respondería el tablero
físico** (lo acepta, o lo bloquea diciendo por qué), con el reloj de ajedrez corriendo
de verdad.

```bash
cd tablero
uv run python -m tablero.simulacion       # pregunta notación y minutos
uv run simulacion --notacion es --minutos 3   # o sin preguntas
```

Corre en notebook o en Raspberry por igual: no importa `io/`, así que no necesita GPIO,
DRM ni pantalla.

## Qué se está probando

La lógica de la simulación **no** es una copia de la del tablero: es la misma. Todo pasa
por `logica/partida.py`, que es lo que va a usar el tablero real cuando `io/sensores.py`
reporte movimientos. Por eso vale como prueba de la regla del reloj y de la validación de
movimientos, no solo como demo.

La regla central, la que motivó este modo, es la de las **dos condiciones**:

> el turno pasa al otro jugador solo si (1) el jugador correcto hizo un movimiento legal
> **y** (2) presionó su botón del reloj **después** de moverlo.

Mientras falta la condición 2, ningún movimiento se acepta —ni el del rival ni otro del
mismo jugador— y el tiempo le sigue corriendo a quien movió, igual que en una mesa real
si te olvidás de apretar el reloj.

## Preguntas de arranque

1. **Notación**: española (`Cf3`, `Ad3`, `Dh5`, `Th1`, `Re2`) o inglesa (`Nf3`, `Bd3`,
   `Qh5`). Se pregunta en vez de autodetectarse porque `R` es ambigua —rey en español,
   *rook* en inglés— y adivinar daría movimientos silenciosamente equivocados. Se puede
   fijar con `--notacion es|en`.
2. **Tiempo por jugador**: 3, 5 o 10 minutos (las mismas opciones que el selector de la
   pantalla, ver [`menus.md`](./menus.md)) o un valor libre. Se puede fijar con
   `--minutos N`.

Otras opciones: `--fen` para arrancar en una posición dada y `--sin-registro` para no
escribir nada en `registros/` (ver [`registro.md`](./registro.md)).

## Comandos

| Comando | Qué hace |
|---|---|
| `e4`, `Cf3`, `e8=D`, `O-O` | Movimiento en la notación elegida |
| `e2e4`, `e7e8d` | Movimiento en UCI (siempre aceptado, en los dos idiomas) |
| `<Enter>` | Presiona el botón del reloj del jugador que tiene el turno |
| `b1` / `b2` | Presiona el botón de blancas / de negras (para probar el equivocado) |
| `esperar N` | Corre N segundos de reloj sin esperarlos de verdad (para probar el timeout) |
| `tablero` | Muestra la posición actual |
| `reloj` / `fen` / `ayuda` | Estado del reloj, FEN de la posición, lista de comandos |
| `salir` | Termina la partida (queda registrada como abandonada); `Ctrl+C`/`Ctrl+D` también |

El reloj corre en tiempo real: los segundos que pasan mientras se piensa y se tipea se
le descuentan a quien tiene el turno. `esperar` existe para no tener que esperar cinco
minutos reales cada vez que se quiere probar qué pasa cuando se acaba el tiempo.

## Ejemplo de sesión

```
⏱  blancas 05:00  ·  negras 05:00
blancas> e4
✓  ACEPTADO  e4  (peón e2→e4)

⏳  blancas tienen que presionar su botón del reloj
blancas> Cc6
⛔  BLOQUEADO: blancas todavía no presionaron su botón del reloj

blancas> b2
·  el botón de negras no hace nada: el turno es de blancas

blancas>
🔔  botón blancas → turno de negras

negras> Cf6
✓  ACEPTADO  Nf6  (caballo g8→f6)
```

Movimientos bloqueados y su mensaje:

| Entrada | Respuesta |
|---|---|
| `a3a4` | `no hay ninguna pieza en a3` |
| `Dh5` (de salida) | `la dama de d1 no puede ir a h5` |
| `Th4` | `ninguna torre de blancas puede ir a h4` |
| `Cf6` en turno de blancas | `'Cf6' es un movimiento de negras, pero el turno es de blancas` |
| `Nf3` con notación española | `'Nf3' no es un movimiento válido en notación española` |
| cualquier cosa tras mover y no apretar | `blancas todavía no presionaron su botón del reloj` |

## Decisiones de diseño

- **Vive en la raíz del paquete, no en `io/`.** `io/` es el código que necesita hardware
  y que, por regla del proyecto, no se ejecuta fuera de la Raspberry; este módulo tiene
  que correr justamente en la notebook. Acá solo hay entrada/salida de terminal: la
  lógica está toda en `logica/`.
- **Valida contra `EstadoTablero` y no contra `logica/eventos.py`.** El rastreador de
  ocupación es la v1 y rechaza capturas, enroque y al paso a propósito (ver
  [`eventos.md`](./eventos.md)), así que no permitiría jugar una partida completa. La
  simulación prueba la capa de reglas + reloj; la traducción de sensores a movimientos se
  prueba aparte en `test_eventos.py`.
- **El board cambia de turno antes que el reloj.** `Partida` aplica el movimiento al
  `chess.Board` en el acto (igual que hace `eventos.py` cuando lo detecta por sensores),
  porque el board es lo que valida la posición y tiene que estar sincronizado con las
  piezas físicas. El turno que percibe el jugador es el del **reloj**, que solo avanza con
  el botón: ese desfase entre `board.turn` y `reloj.turno` *es* la condición 2 pendiente.

## Módulos que usa

| Módulo | Qué aporta |
|---|---|
| [`logica/partida.py`](./partida.md) | La regla de las dos condiciones y los mensajes de bloqueo |
| [`logica/reloj.py`](./partida.md#logicarelojpy) | El reloj (compartido con la pantalla, ver [`menus.md`](./menus.md)) |
| [`logica/notacion.py`](./partida.md#logicanotacionpy) | Parseo de SAN español/inglés y UCI |
| [`logica/registro.py`](./registro.md) | PGN y log detallado de cada partida |
| [`logica/estado_tablero.py`](./logica.md) | Reglas de ajedrez (python-chess) |

## Tests

`tablero/tests/test_partida.py`, `test_reloj.py` y `test_notacion.py` cubren esta lógica
sin pasar por la terminal — ver [`testing.md`](./testing.md).
