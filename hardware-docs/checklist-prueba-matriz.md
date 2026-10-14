# Guía: prueba y mapeo de la matriz de casillas

Vas a verificar los dos chips que leen el tablero, probar que los imanes de las piezas activan
los sensores, calibrar qué sensor corresponde a cada casilla y verificar las 64 casillas.

## Cómo usar esta guía

Para cada ítem:

1. Copiá el comando y ejecutalo en la sesión SSH de la Raspberry.
2. Hacé la prueba que dice el ítem.
3. Anotá el resultado en la línea 📝.
4. Pasá al siguiente ítem.

Antes de empezar, hacé una copia de este archivo (por ejemplo `resultados-matriz.md`) y anotá
ahí; no edites este.

Si algo no da lo esperado (✅), anotá exactamente lo que viste. Si el ítem tiene ⛔, pará ahí y
avisale a Tino; si no, seguí con el siguiente. Si un comando muestra un error largo
(`Traceback ...`), copialo entero en el 📝 y pará.

**Qué necesitás:** la sesión SSH a la Pi, un multímetro, todas las piezas y cinta de papel.

---

## Parte 1 · Preparación

### 1. Conectarte y actualizar

```bash
cd ~/tablero-ajedrez-inteligente/tablero && git pull && uv sync
```

✅ Termina sin errores.
⛔ Si da error, pará.

📝 **Resultado:**

### 2. Preparar el tablero

- Elegí la orientación: **a1 es la casilla oscura en la esquina izquierda del lado de las
  blancas**. Marcala con cinta.
- Sacá todas las piezas del tablero y dejalas lejos (una caja con imanes al lado puede activar
  los sensores del borde). Quedate con una sola pieza a mano.

📝 **De qué lado del tablero quedaron las blancas** (por ejemplo "del lado de los cables"):

---

## Parte 2 · Los chips

### 3. Chip de las filas (74HC138)

```bash
uv run python -m tablero.io.sensores selector
```

El programa activa las salidas Y0 a Y7 de a una y espera Enter entre cada una. En cada paso:

1. Con el multímetro en voltaje continuo, punta negra en la pata 8 del 138 (GND).
2. Punta roja en la pata que indica el mensaje: tiene que dar **~0 V**.
3. Punta roja en cualquier otra salida Y (por ejemplo la del paso anterior): tiene que dar
   **~3,3 V**.
4. Apretá Enter.

Las patas del chip, mirándolo desde arriba con la muesca hacia arriba:

```
          ┌────╮╭────┐
   A    1 │    ╰╯    │ 16  Vcc
   B    2 │          │ 15  Y0
   C    3 │          │ 14  Y1
        4 │ 74HC138  │ 13  Y2
        5 │          │ 12  Y3
        6 │          │ 11  Y4
   Y7   7 │          │ 10  Y5
   GND  8 │          │  9  Y6
          └──────────┘
```

✅ En los 8 pasos, la pata indicada da ~0 V y las otras salidas ~3,3 V.
⛔ Si no, pará.

📝 **Resultado** (si algo no dio, en qué paso, qué pata y cuánto midió):

### 4. Chip de las columnas (74HC165)

Con el tablero vacío:

```bash
uv run python -m tablero.io.sensores lector
```

✅ Imprime dos líneas con todos `1` y al final una línea que empieza con `OK`.
⛔ Si la última línea empieza con `FALLA`, pará.

📝 **Resultado** (copiá las tres líneas que imprime):

---

## Parte 3 · Sensores e imanes

### 5. Tablero vacío

```bash
uv run python -m tablero.io.sensores matriz
```

El programa queda corriendo y redibuja la pantalla cada vez que cambia algo. Muestra dos
dibujos; **por ahora mirá solo el de arriba**, "Matriz cruda". El de abajo, "Tablero mapeado",
recién tiene sentido después de calibrar (Parte 4).

```
Matriz cruda (# = reed cerrado):
      D0 D1 D2 D3 D4 D5 D6 D7
  Y0   .  .  .  .  .  .  .  .
  Y1   .  .  .  .  .  .  .  .
  ...
```

✅ Con el tablero vacío, todo en `.`.
⛔ Si hay algún `#`, pará.

📝 **Resultado:**

Dejá el programa corriendo para los ítems 6 a 8.

### 6. Una pieza

Apoyá la pieza en cualquier casilla y después levantala.

✅ Al apoyarla aparece **un solo** `#`; al levantarla, desaparece.

📝 **Resultado:**

### 7. Centro y bordes de la casilla

En las casillas **a1, d4 y h8**, apoyá la pieza:

- centrada en la casilla;
- corrida hacia cada uno de los 4 bordes de la casilla.

✅ En todas las posiciones hay **exactamente un** `#`. Si no aparece ninguno, el sensor no la
detecta en esa posición. Si aparecen dos, el imán está activando también la casilla vecina.

📝 **Resultado** (casilla, posición y cuántos `#` aparecieron):

### 8. Todas las piezas

Apoyá cada una de las 32 piezas, de a una, en la misma casilla (por ejemplo d4).

✅ Todas encienden el `#`.

📝 **Piezas que no se detectan:**

Cuando termines, cortá el programa con `Ctrl+C`.

---

## Parte 4 · Calibración

### 9. Calibrar

Con el tablero vacío y una pieza a mano:

```bash
uv run python -m tablero.io.sensores calibrar
```

Te va a pedir 15 casillas de a una: a1, b1, … h1 y después a2, a3, … a8. Para cada una:

1. Poné la pieza en la casilla que pide (sacándola de la anterior).
2. **Después** apretá Enter.

Si dice `Se detectaron N celdas activas`, repetí la misma casilla: revisá que no haya otra pieza
en el tablero.

✅ Termina imprimiendo dos líneas que empiezan con `FILA_DE_SALIDA_138` y
`COLUMNA_DE_ENTRADA_165`, sin ningún `AVISO` en el medio.
⛔ Si aparece un `AVISO`, pará.

📝 **Resultado** (copiá las dos líneas finales y cualquier `AVISO`):

### 10. Guardar la calibración

```bash
nano src/tablero/config.py
```

1. Apretá `Ctrl+W`, escribí `FILA_DE_SALIDA_138` y Enter.
2. Borrá esa línea con `Ctrl+K` y pegá en su lugar la línea `FILA_DE_SALIDA_138: ...` que
   imprimió la calibración.
3. Lo mismo con `COLUMNA_DE_ENTRADA_165`.
4. Guardá con `Ctrl+O` y Enter; salí con `Ctrl+X`.

Para confirmar que quedó bien:

```bash
grep -nE "^(FILA_DE_SALIDA_138|COLUMNA_DE_ENTRADA_165)" src/tablero/config.py
```

✅ Muestra las dos líneas, iguales a las del ítem 9.
⛔ Si no, pará.

No hace falta commitear: Tino se encarga.

📝 **Resultado:**

---

## Parte 5 · Verificación de las 64 casillas

### 11. Recorrer las 64 casillas

```bash
uv run python -m tablero.io.sensores matriz
```

Ahora mirá el dibujo de abajo, "Tablero mapeado", y los mensajes `aparece pieza en ...`. Llevá una
pieza por las 64 casillas en orden: a1, b1, … h1, a2, … h8.

✅ En cada casilla, el mensaje dice exactamente la casilla donde está la pieza.

📝 **Casillas que fallaron** (dónde estaba la pieza y qué dijo el mensaje):

### 12. Posición inicial

Armá la posición inicial completa (32 piezas) y esperá unos segundos sin tocar nada.

✅ Dice `Tablero mapeado (32 piezas)`, el dibujo muestra llenas las filas 1, 2, 7 y 8, y no
cambia mientras no toques nada.

📝 **Resultado** (si no dio 32, cuántas y cuáles faltan o sobran):

### 13. Filas del medio

Mové las 32 piezas a las filas 3, 4, 5 y 6 y esperá unos segundos.

✅ Dice `(32 piezas)`, las filas 3 a 6 aparecen llenas y no cambia.
Si alguna pieza parpadea o desaparece, **no lo dejes corriendo así**: anotá cuál y cortá con
`Ctrl+C`.

📝 **Resultado:**

### 14. Mano y arrastre

Volvé a correr `matriz` si lo cortaste. Pasá la mano por encima del tablero y arrastrá algunas
piezas de una casilla a otra.

✅ No aparecen ni desaparecen piezas que no tocaste.

📝 **Resultado:**

Cortá el programa con `Ctrl+C`.

---

## Al terminar

Pasale a Tino tu copia con todas las líneas 📝 completas.

El detalle técnico de cada prueba y cómo interpretar las fallas está en
`software-docs/sensores.md` ("Cómo probarlo" → "Matriz").
