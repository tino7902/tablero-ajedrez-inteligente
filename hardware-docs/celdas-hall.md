# Celdas con sensor Hall (A3144 / KY-003)

> **Versión anterior (v2), descartada.** Al probarla, la salida activa del 138 marcó 1,6 V: el
> riesgo 1 de abajo se confirmó. La versión actual es la v3, con Arduino Nano y un NPN por fila
> (`matriz-hall-nano.md`); historial y alternativas en `historial-deteccion.md`. El pinout, la
> polaridad y el diodo de cada celda siguen valiendo en la v3.


Cómo va conectado cada uno de los 64 sensores Hall en la matriz, qué puede fallar eléctricamente y
cómo medirlo. Los chips (74HC138 y 74HC165) no cambian respecto de la versión reed: sus conexiones
pata por pata siguen en `conexiones-matriz.md`. Software y diagnóstico en `software-docs/sensores.md`;
guía de prueba paso a paso en `checklist-prueba-hall.md`.

## Conexión de una celda

Un reed tiene dos patas y no necesita alimentación; un Hall tiene tres y sí la necesita. Para
seguir usando los mismos chips, el **GND de cada Hall va a la salida Y del 138 de su fila**:

```
                         ┌─────────┐
  3,3 V ──────────── Vcc ┤         │
                         │  A3144  ├─ OUT ──┤◄── columna (entrada D del 165, con su pull-up de 10 kΩ)
  salida Y del 138 ─ GND ┤         │
                         └─────────┘

  Diodo: la banda (cátodo) hacia OUT, el ánodo hacia la columna.
```

- **Fila elegida**: el 138 pone esa Y en LOW (~0 V), los 8 Hall de la fila reciben 3,3 V y quedan
  encendidos. Un Hall con el polo sur de un imán encima pone su salida en LOW: la columna baja a
  través del diodo y el 165 la lee como pieza.
- **Filas no elegidas**: su Y queda en HIGH (3,3 V), así que esos Hall tienen 3,3 V en Vcc y en GND:
  están apagados y no bajan la columna.
- **Para qué está el diodo**: cuando otro Hall baja la columna, un Hall apagado tiene la salida por
  debajo de su GND (que está en 3,3 V), y sus diodos de protección internos dejarían pasar corriente
  desde su fila hacia la columna. El diodo bloquea ese camino. Por eso va con la banda hacia la
  salida del Hall.
- **El software espera** en cada fila a que los Hall enciendan antes de leer
  (`HALL_ESPERA_ENCENDIDO`, se mide con `calibrar`).

## Pinout

**A3144 suelto (TO-92)**: mirando la cara plana con letras, con las patas hacia abajo, de izquierda
a derecha: **1 Vcc, 2 GND, 3 OUT**.

**Módulo KY-003**: tres pines rotulados `S` (señal = OUT), `+` (Vcc) y `-` (GND). El orden cambia
según el fabricante del módulo, así que hay que **leer la serigrafía**, no suponerlo. El módulo ya
trae una pull-up de 10 kΩ en `S` (no molesta: la columna ya tiene la suya) y un LED que se prende
cuando detecta un imán (ver el riesgo 1).

**Polaridad**: el A3144 es *unipolar*: solo reacciona al **polo sur** de un imán puesto contra su
**cara con letras**. Así que:

- la cara con letras de cada Hall tiene que mirar hacia arriba, hacia la pieza;
- **todos los imanes van con el polo sur hacia abajo**. Hay que marcar el polo en cada pieza. Con
  los reed daba igual.

Para encontrar el polo sur de un imán: acercarlo a un Hall ya conectado (con `matriz` corriendo).
La cara que lo activa es el sur.

## ⚠️ Riesgos eléctricos

Hay que revisarlos **con una fila armada, antes de soldar las 64**. Se miden con `medir` (ver "Con la
Pi encendida" más abajo).

1. **La salida del 138 no da abasto con 8 Hall.** Cada A3144 consume unos 4,4 mA encendido, así que
   la Y de una fila tiene que hundir unos 35 mA, más los LEDs de los KY-003 de las casillas con
   pieza. Eso supera el máximo absoluto del 74HC138 (±25 mA por pata). Su corriente garantizada es
   bastante menor, del orden de 4–5 mA. Con esa carga la Y no llega a 0 V: los Hall quedan con menos
   tensión y la columna no baja lo suficiente.
   - **Cómo se ve**: con `medir`, la Y activa da 0,3 V o más (medición 1). En `matriz`, nada se
     detecta, o se pierden detecciones cuando hay varias piezas en la misma fila.
   - **Arreglos posibles** (a decidir con quien arma el hardware): un transistor por fila que
     maneje la corriente, comandado por la Y del 138. Por ejemplo, un PNP o P-MOSFET que alimente
     el Vcc de la fila, con el GND de los Hall a GND común; o un 74HC238 con un ULN2803. Si el
     transistor cambia la lógica (por ejemplo, alimentar por Vcc en vez de cortar el GND), el
     software no cambia mientras "elegir la fila" siga encendiendo solo esa fila.
2. **El A3144 a 3,3 V está fuera de su hoja de datos.** El original de Allegro pide 4,5 V como
   mínimo; algunos clones declaran desde 2,5–3,5 V. Hay que probar uno suelto a 3,3 V.
   - **No alimentarlo a 5 V con este circuito**: con la fila apagada (Y en 3,3 V) quedaría
     corriente entrando desde los 5 V al riel de 3,3 V a través de las salidas del 138.
3. **Nivel bajo de la columna.** Con pieza, la columna queda en la suma de la Y del 138, la salida
   del Hall y el diodo, y tiene que quedar por debajo del umbral del 165, ~1 V con 3,3 V. Con un
   1N4148 (~0,6 V) queda justo; un diodo Schottky (BAT85, BAT43, 1N5819: ~0,3 V) da margen.
   - **Cómo se ve**: con `medir`, la columna con pieza da 0,8 V o más (medición 3); en `matriz`,
     celdas que parpadean.
4. **Diodo al revés**: la banda va hacia la salida del Hall. Al revés, esa casilla no se detecta
   nunca.

**Sensores que no sirven** con este circuito: los Hall de tipo *latch* (biestables), porque quedan
activos al sacar la pieza y se apagan solo con el polo contrario; y los analógicos (49E, KY-035),
porque en reposo dan ~Vcc/2 y el 165 solo lee 0 o 1.

## Mediciones

### Con la Pi apagada (multímetro en continuidad o diodo)

| Medición | Tiene que dar | Si no |
|---|---|---|
| GND de cada Hall ↔ la pata Y del 138 de su fila | Continuidad | Ese Hall no se apaga con su fila |
| GND de cada Hall ↔ GND de la Pi | **Sin** continuidad | Ese Hall está a GND común: una pieza en esa casilla enciende la columna entera en `matriz` |
| Vcc de cada Hall ↔ 3,3 V | Continuidad | El Hall no tiene alimentación |
| Modo diodo, punta roja en la columna (pata D del 165), negra en OUT del Hall | ~0,5–0,7 V (1N4148) o ~0,2–0,4 V (Schottky) | `OL`: el diodo está al revés o cortado. ~0 V: el diodo está en corto o falta |
| Modo diodo, puntas invertidas | `OL` | ~0,5 V: el diodo está al revés |

### Con la Pi encendida (`medir`)

Barriendo, cada fila está encendida 1/8 del tiempo y el multímetro marca un promedio que no sirve.
`medir` deja una fila fija:

```bash
cd tablero
uv run python -m tablero.io.sensores medir Y0     # o, ya hecho el mapeo, una casilla: medir e4
```

Multímetro en voltaje continuo, punta negra en GND (pata 8 del 138), salvo la medición 2:

| Medición | Tiene que dar | Si no |
|---|---|---|
| 1. La pata de la Y activa (Y0 = 15, Y1 = 14, Y2 = 13, Y3 = 12, Y4 = 11, Y5 = 10, Y6 = 9, Y7 = 7) | < 0,3 V | Riesgo 1 |
| 2. Entre GND (negra) y Vcc (roja) de un Hall de esa fila | ≥ 3 V | Riesgo 1, o Vcc mal conectado |
| 3. Con una pieza en una casilla de esa fila, la pata del 165 de su columna (D0..D7 = patas 11, 12, 13, 14, 3, 4, 5, 6) | < 0,8 V; sin pieza ~3,3 V | Riesgo 3 |

Repetir la 1 y la 3 **con la fila llena de piezas**: en los KY-003, cada pieza prende el LED del
módulo, y su corriente también pasa por la Y.
