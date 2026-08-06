# `logica/estado_tablero.py`

Estado de la partida y validación de movimientos. Es la única fuente de verdad sobre
la posición actual del juego: quién mueve, qué movimientos son legales, si hay jaque,
jaque mate o tablas.

## Por qué existe este módulo

En vez de que el resto del proyecto (motor, io, web) use `chess.Board` directamente,
`EstadoTablero` lo envuelve con una API en español, consistente con el resto del
proyecto, y centraliza en un solo lugar las reglas de "qué es un movimiento válido para
esta app" — por ahora eso es simplemente "legal según python-chess", pero da un punto
único para agregar reglas propias más adelante (por ejemplo, validaciones específicas
del hardware) sin tocar a los consumidores del módulo.

No reimplementa reglas de ajedrez: enroque, captura al paso, promoción, jaque, tablas
por ahogado/material insuficiente/repetición/50 movimientos — todo lo resuelve
`chess.Board` (paquete `chess`, instalado en este proyecto como `python-chess==1.999`,
que es un shim de compatibilidad sobre el paquete real `chess`).

## API

| Método/propiedad | Qué hace |
|---|---|
| `EstadoTablero(fen=None)` | Arranca en la posición inicial, o en `fen` si se pasa |
| `.board` | `chess.Board` interno, de solo lectura por convención (no mutar directo) |
| `.turno` | `chess.WHITE` o `chess.BLACK`, a quién le toca mover |
| `.fen()` | Posición actual en notación FEN |
| `.movimientos_legales()` | Lista de todos los `chess.Move` legales en la posición actual |
| `.es_legal(movimiento)` | `bool` |
| `.aplicar_movimiento(movimiento)` | Aplica el movimiento; levanta `MovimientoIlegalError` si no es legal |
| `.deshacer()` | Deshace el último movimiento y lo devuelve |
| `.reiniciar()` | Vuelve a la posición inicial |
| `.esta_en_jaque()` | `bool` |
| `.es_jaque_mate()` | `bool` |
| `.es_tablas()` | Ahogado, material insuficiente, o 50 movimientos/repetición reclamables |
| `.terminada()` | La partida terminó, por cualquier motivo |
| `.resultado()` | `"1-0"` / `"0-1"` / `"1/2-1/2"` / `None` si sigue en curso |

## Decisiones de diseño

- **`board` como propiedad pública**: `motor/stockfish.py` necesita un `chess.Board`
  para pedirle una jugada a Stockfish. En vez de que `motor/` dependa de la clase
  `EstadoTablero` (o duplique lógica de conversión), simplemente recibe el `chess.Board`
  interno vía `estado.board`. Es de solo lectura por convención — nada impide mutarlo
  desde afuera, pero el contrato es que los cambios de estado pasan siempre por
  `aplicar_movimiento`.
- **`MovimientoIlegalError` en vez de devolver `bool`**: `aplicar_movimiento` levanta
  una excepción en vez de devolver `False` en movimientos inválidos, para que un
  caller nunca pueda ignorar silenciosamente un movimiento que no se aplicó.
- **Promoción sin lógica especial**: los sensores físicos no pueden detectar a qué
  pieza promociona un peón (no sensan identidad de pieza, solo ocupación). Por ahora
  eso queda completamente fuera de este módulo: quien construye el `chess.Move` decide
  la pieza de promoción (`chess.Move.from_uci("e7e8q")`). La resolución real (vía UI,
  botones, LEDs, etc.) es una decisión pendiente para cuando se implemente
  `logica/eventos.py`.

## Fuera de alcance (todavía)

- `logica/eventos.py`: traducir eventos de sensores (casilla ocupada/vacía) a un
  `chess.Move`. Los sensores 74HC165 solo detectan presencia/ausencia de pieza por
  casilla, no identidad — inferir el movimiento requiere comparar el diff de ocupación
  contra `movimientos_legales()` en el estado actual.
- Resolución interactiva de la pieza de promoción.

## Tests

`tablero/tests/test_logica.py` — no requiere hardware ni binarios externos. Cubre:
movimientos legales/ilegales, mate del pastor (jaque mate real), ahogado (tablas),
captura al paso, enroque corto, promoción a dama, deshacer/reiniciar. Correr con:

```bash
cd tablero && uv run pytest tests/test_logica.py -v
```
