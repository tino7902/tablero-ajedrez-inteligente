# `io/prueba_tablero.py`

Pruebas del tablero completo: los sensores Hall ([`sensores.md`](./sensores.md)) y los LEDs
([`leds.md`](./leds.md)) juntos. Sirve para asociar cada LED a su casilla sin tipear nada y para
verificar, de punta a punta, que lo que detectan los sensores, lo que muestran los LEDs y el
tablero real coincidan. **Probado en el prototipo** (2026-10-18): `leds` generó
`LED_DE_CASILLA`, y `recorrido` y `espejo` funcionan. Faltan `inicial` y `calibrar`, que
necesitan las 32 piezas.

## Requisitos

- **El mapeo de los Hall hecho** (`CASILLA_DE_CELDA_HALL`, con `sensores mapear`): todas estas
  pruebas leen la casilla de cada pieza a través de él. Si sigue en la identidad (el placeholder),
  `leds` y `recorrido` lo avisan al arrancar.
- **El mapeo de los LEDs** (`LED_DE_CASILLA`) para `recorrido`, `espejo` e `inicial`. `leds` es
  justamente lo que lo genera.
- **Root**, por los LEDs, con los mismos requisitos que `io/leds.py` (`dtparam=audio=off`, GND
  común). Igual que `io/leds.py`, si no se corre como root se relanza solo con
  `sudo <python del .venv>`. Como root, el puerto del Nano se abre sin necesitar `dialout`.

## Cómo probarlo

Desde `tablero/`, por SSH en la Raspberry, con el Nano enchufado. `Ctrl+C` corta cualquiera de
las pruebas: apaga los LEDs y cierra el puerto del Nano.

```bash
uv run python -m tablero.io.prueba_tablero leds        # genera LED_DE_CASILLA con una pieza
uv run python -m tablero.io.prueba_tablero recorrido   # verificación guiada de a1 a h8
uv run python -m tablero.io.prueba_tablero espejo      # los LEDs muestran las casillas ocupadas
uv run python -m tablero.io.prueba_tablero inicial     # compara con la posición inicial
uv run python -m tablero.io.prueba_tablero calibrar    # calibra los Hall con los LEDs en vivo
```

Todas aceptan `--brillo 0-191` (tope `LED_BRILLO_MAX`, por defecto `LED_BRILLO`).

### `leds`

Lo mismo que `leds calibrar`, pero la casilla la dicen los Hall en vez de tipearla. Con una sola
pieza en el tablero, prende en blanco un LED por vez (salteando el de sacrificio). Para cada LED,
se pone la pieza en la casilla iluminada y se aprieta Enter:

- `-` si ese LED no ilumina ninguna casilla;
- `r` para volver al LED anterior.

Si se detectan cero piezas o más de una, o si la casilla ya tiene un LED asignado, lo avisa y
repite. Al final imprime `LED_DE_CASILLA` para pegar en `config.py`, en el mismo formato que
`leds calibrar` (`formatear_led_de_casilla()` de `io/leds.py`).

### `recorrido`

Es la prueba de todo junto. Recorre a1, b1, …, h8 con una sola pieza:

1. Prende la casilla objetivo en **azul** y espera la pieza ahí. Mientras la pieza esté levantada
   o todavía en la casilla anterior, solo espera.
2. Si la detecta en la casilla objetivo, la prende en **verde** y pasa a la siguiente.
3. Si la detecta en otra casilla, esa se prende en **rojo**, se loguea `FALLA` y queda anotada.
   Con más de una pieza, las prende en **amarillo** y pide dejar una sola.
4. **Enter** saltea la casilla (por ejemplo, si la pieza no se detecta nunca) y queda anotada.

Al final imprime `OK` si las 64 se detectaron donde se prendieron, o la lista de fallas y
salteadas. Cómo leer una falla en la casilla X que se detectó en Y:

| Qué se ve | Causa probable |
|---|---|
| La luz azul de X se prende físicamente en la casilla Y | El LED de X está mal en `LED_DE_CASILLA` (`leds verificar` lo confirma) |
| La luz está bien en X, la pieza está en X, pero se detecta en Y | El Hall de X está mal en `CASILLA_DE_CELDA_HALL` (`sensores matriz` lo confirma) |
| La pieza en X no se detecta nunca (hay que saltearla) | Hall dañado o imán al revés: ver la tabla de "Matriz en vivo" en [`sensores.md`](./sensores.md) |

### `espejo`

Cada casilla con pieza se prende en verde, en vivo, y se loguea `aparece pieza en e4` /
`se levanta pieza de e2`. Sirve para probar libremente: pasar la mano, arrastrar piezas o armar
posiciones.

### `inicial`

Compara en vivo contra la posición inicial (filas 1, 2, 7 y 8 ocupadas): **verde** donde hay
pieza y tiene que haber, **rojo** donde falta, **amarillo** donde sobra. Loguea cuántas faltan y
sobran en cada cambio, y `Posición inicial completa (32 piezas).` cuando coincide. Es la
comprobación antes de arrancar una partida.

### `calibrar`

Es la calibración de los Hall (ver [`sensores.md`](./sensores.md#calibrar)), con los mismos
tres pasos y el mismo resultado, pero mientras se espera el Enter de cada paso los LEDs muestran en vivo lo
que detectan los Hall, comparado con lo que tiene que haber. Los colores son los de `inicial`:
**verde** donde hay pieza y tiene que haber, **rojo** donde falta, **amarillo** donde sobra.

- Paso 1 (reposo): se compara con el tablero vacío. Cualquier casilla que se prenda en
  amarillo es una pieza o un imán que quedó cerca, o un Hall que marca solo.
- Pasos 2 y 3: se compara con la posición inicial.

Existe porque los Hall solo ven la pieza si está justo encima del sensor. Con la pieza un poco
corrida, la casilla queda en rojo, y se la acomoda hasta que se prenda en verde antes de medir.
Si al apretar Enter algo no coincide, imprime qué falta y qué sobra y espera otro Enter: o se
acomoda la pieza, o se sigue igual (por ejemplo, con un Hall que no anda).

Durante las mediciones los LEDs quedan prendidos como estaban (hasta 32 en verde). Como los LEDs
y el Nano comparten cargador, se mide con algo de carga, que es lo conservador. Si el paso 2 da
`FALLA` acá y no con `sensores calibrar --sin-leds`, la culpa es de la caída de tensión de los LEDs y no de
la matriz.

Necesita los dos mapeos hechos, porque pinta por casilla. Si alguno está mal, se usa
`sensores calibrar --sin-leds`, que no prende LEDs.

`uv run python -m tablero.io.sensores calibrar` (sin `--sin-leds`) termina acá: se reemplaza
por `prueba_tablero calibrar`, que se relanza con `sudo`.

## Decisiones de diseño

- **Módulo aparte, no dentro de `io/leds.py` ni de `io/sensores.py`**: es lo único que usa los
  dos a la vez. Así `io/sensores.py` sigue sin depender de `rpi-ws281x` ni de root, y los botones
  del reloj no lo necesitan.
- **`leds` y `mapear` con Enter; `recorrido` sin Enter**: para asociar, la persona confirma cada
  paso, igual que en `leds calibrar`. En `recorrido` los LEDs muestran a dónde ir y el chequeo es
  automático, así que avanza solo; el Enter para saltear se lee sin bloquear (`select` sobre
  stdin), para que el sondeo de la matriz siga corriendo mientras tanto.
- **Se ignora la casilla anterior en `recorrido`**: al pasar de una casilla a la siguiente, la
  primera lectura estable todavía tiene la pieza en la anterior; eso no es una falla.
