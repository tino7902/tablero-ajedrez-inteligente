# `io/sensores_reed.py` (versión anterior, con reed switches)

> **Versión anterior.** El tablero ahora usa sensores Hall (`io/sensores.py`, ver
> [`sensores.md`](./sensores.md)). Esta versión se conserva por si se vuelve a los reed: los
> chips son los mismos, así que comparte con la versión Hall el driver del 74HC138 + 74HC165
> (`io/matriz.py`) y sus pruebas por chip.

Matriz de ocupación con 64 reed switches, cada uno en serie con un diodo:
**columna → reed → diodo → fila** (ver "Celdas (reed + diodo)" en
`hardware-docs/conexiones-matriz.md`). Guía paso a paso de prueba y mapeo:
`hardware-docs/checklist-prueba-matriz-reed.md`. En el repo, el mapeo reed de `config.py` sigue
siendo el placeholder: no se llegó a pegar el resultado de `calibrar` antes del cambio a Hall.

## API

| Función/clase | Qué hace |
|---|---|
| `LectorMatriz(lecturas_estables)` | El `LectorMatriz` de `io/matriz.py` con la espera de los reed (0,1 ms por fila) y `REED_LECTURAS_ESTABLES`. `.leer()` devuelve la matriz solo cuando se repitió N veces seguidas **y** cambió; si no, `None` |
| `configurar_matriz()` / `liberar_matriz()` | Los de `io/matriz.py`, reexportados |
| `casilla_de(salida, entrada)` | Celda cruda → `chess.Square`, según las dos permutaciones de `config.py` |
| `ocupacion(matriz)` | Matriz cruda → `frozenset[chess.Square]`, la `Ocupacion` que espera `logica/eventos.py` |
| `probar_matriz()` / `calibrar_matriz()` | CLI `matriz` / `calibrar`, ver "Cómo probarlo" |

Con la misma API que la versión Hall: para volver a los reed en un futuro loop de juego alcanza
con importar `sensores_reed` en vez de `sensores`.

## Configuración (`config.py`, sección "versión reed")

| Constante | Valor | Nota |
|---|---|---|
| `REED_LECTURAS_ESTABLES` | 3 | Antes se llamaba `MATRIZ_LECTURAS_ESTABLES` |
| `FILA_DE_SALIDA_138` | identidad | `[y]` = fila de ajedrez de la salida Y del 138. Lo genera `calibrar` |
| `COLUMNA_DE_ENTRADA_165` | identidad | `[d]` = columna de ajedrez de la entrada D del 165. Lo genera `calibrar` |

## Decisiones de diseño

- **Espera fija de 0,1 ms por fila**: el 138 tarda nanosegundos, pero cubre la capacidad de los
  cables largos de la matriz. El reed no necesita encender, a diferencia del Hall.
- **Antirrebote por repetición** (`REED_LECTURAS_ESTABLES = 3`) en vez de por tiempo: la mano
  pasando sobre el tablero y el cierre de un reed generan parpadeos de pocos ms. Si con el
  prototipo se ven cambios fantasma, es el primer parámetro a subir.
- **Mapeo con dos permutaciones, no una tabla de 64**: cada salida del 138 es una fila física y
  cada entrada del 165 una columna física, así que `FILA_DE_SALIDA_138` y
  `COLUMNA_DE_ENTRADA_165` alcanzan, y la calibración pide 15 casillas en vez de 64. En el
  esquemático las columnas no entran en orden al 165, así que los valores por defecto
  (identidad) son solo un placeholder hasta correr `calibrar`.

## Imanes y reeds

- **Punto muerto**: si el eje del imán queda perpendicular al reed y justo sobre su centro, las
  dos láminas reciben el mismo polo y el reed puede no cerrar. Por eso la guía de prueba pide
  probar cada casilla con la pieza centrada y corrida hacia los bordes.
- **Polaridad**: al reed le da igual qué polo tenga cerca. Conviene igual poner todas las piezas
  con el mismo polo hacia abajo: así dos piezas vecinas se repelen en vez de atraerse.

## Cómo probarlo

Desde `tablero/`, por SSH en la Raspberry. Las pruebas de cada chip (`selector`, `lector`) son
las mismas que en la versión Hall: ver "Pruebas por chip" en [`sensores.md`](./sensores.md).

```bash
uv run python -m tablero.io.sensores_reed selector
uv run python -m tablero.io.sensores_reed lector
uv run python -m tablero.io.sensores_reed matriz
uv run python -m tablero.io.sensores_reed calibrar
```

### Matriz en vivo

`matriz` limpia la terminal y dibuja la matriz cruda (Y0–Y7 × D0–D7) y el tablero ya mapeado cada
vez que cambia algo, y loguea `aparece pieza en e4` / `se levanta pieza de e2`.

Qué mirar: con el tablero vacío no tiene que haber ninguna celda `#`; al apoyar una pieza tiene
que encenderse **una sola** celda. Si con una sola pieza se encienden varias, el imán está cerrando
reeds vecinos o hay un puente de estaño: con una pieza sola los diodos no influyen. Hasta correr
`calibrar`, el tablero mapeado no significa nada.

| Qué se ve | Causa probable |
|---|---|
| Todo en `#` | El pin 36 está flotando (`lector`), el 165 sin alimentación, o faltan las pull-ups |
| Nunca se enciende nada | El 138 está deshabilitado o A/B/C mal conectados (`selector`) |
| Solo reacciona la columna de D7 y marca la fila Y entera | El 165 no desplaza: CLK (pin 31 → pata 2) o INH (pata 15) sin GND (`lector`) |
| Una columna D entera en `#` | Pull-up suelta en esa columna o columna en corto a GND |
| Celdas sueltas fijas en `#` con el tablero vacío | El reed de esa celda está cerrado: pegado, con el vidrio rajado o con un imán cerca (uno suelto debajo del tablero). También puede ser un puente de estaño sobre el reed. Si son dos celdas de la misma fila en columnas vecinas, puede ser una sola celda cerrada más esas dos entradas D en corto entre sí. Hay que arreglarlo antes de `calibrar`, que pide una sola celda activa |
| Celdas que parpadean sin tocar nada | Soldaduras. Si no es eso, subir `REED_LECTURAS_ESTABLES` |

Los diodos se notan recién con **varias piezas en la misma columna física**. Como el 74HC138
mantiene en HIGH (push-pull) las filas no seleccionadas, un diodo faltante, en corto o invertido no
genera la casilla fantasma clásica del ghosting. Lo que pasa es que esa fila HIGH pelea contra la
fila LOW por la columna, y las *otras* piezas de esa columna parpadean o desaparecen. Un diodo
invertido, además, hace que su casilla no se encienda nunca. La prueba es poner piezas en todas
las casillas de una columna (o las 32 en la posición inicial y después las 32 en las filas 3–6):
tienen que verse todas, estables. Si falla, no dejarlo corriendo así, porque son dos salidas del
138 en corto a través del reed.

### Calibración

Pide una pieza sola en a1, b1, … h1 y después en a2, … a8, verifica que el cableado sea una
grilla y al final imprime las dos líneas para pegar en `config.py`. Después de pegarlas, volver a
correr `matriz` y confirmar que el tablero mapeado coincide con las piezas reales.
