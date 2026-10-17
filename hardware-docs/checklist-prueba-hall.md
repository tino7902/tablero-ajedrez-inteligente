# Guía: prueba y mapeo de la matriz con sensores Hall

Vas a verificar los dos chips que leen el tablero, medir que los sensores Hall reciban bien la
alimentación, probar que los imanes de las piezas los activen, calibrar los tiempos, mapear qué
sensor corresponde a cada casilla, asociar cada LED a su casilla y verificar todo junto.

(La guía de la versión anterior, con reed switches, es `checklist-prueba-matriz-reed.md`.)

## Cómo usar esta guía

Para cada ítem:

1. Copiá el comando y ejecutalo en la sesión SSH de la Raspberry.
2. Hacé la prueba que dice el ítem.
3. Anotá el resultado en la línea 📝.
4. Pasá al siguiente ítem.

Antes de empezar, hacé una copia de este archivo (por ejemplo `resultados-hall.md`) y anotá ahí;
no edites este.

Si algo no da lo esperado (✅), anotá exactamente lo que viste. Si el ítem tiene ⛔, pará ahí y
avisale a Tino; si no, seguí con el siguiente. Si un comando muestra un error largo
(`Traceback ...`), copialo entero en el 📝 y pará.

**Qué necesitás:** la sesión SSH a la Pi, un multímetro, todas las piezas, cinta de papel y un
marcador.

> **Si todavía no están soldados los 64 Hall**: hacé primero la Parte 2 y la Parte 3 con **una
> sola fila armada**. La Parte 3 dice si el 138 aguanta la corriente de los Hall; si no la
> aguanta, hay que cambiar el circuito antes de soldar el resto (ver
> `hardware-docs/celdas-hall.md`, "Riesgos eléctricos").

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
2. Punta roja en la pata que indica el mensaje: tiene que dar **menos de 0,3 V**.
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

✅ En los 8 pasos, la pata indicada da menos de 0,3 V y las otras salidas ~3,3 V.
⛔ Si la pata indicada da 0,3 V o más, pará: el 138 no da abasto con los Hall de esa fila.
⛔ Si no, por cualquier otro motivo, también pará.

📝 **Resultado** (si algo no dio, en qué paso, qué pata y cuánto midió):

### 4. Chip de las columnas (74HC165)

Con el tablero vacío:

```bash
uv run python -m tablero.io.sensores lector
```

✅ La última línea empieza con `OK`.
⛔ Si la última línea empieza con `FALLA`, pará.

📝 **Resultado** (copiá las cuatro líneas que imprime):

---

## Parte 3 · Tensiones de los Hall

### 5. Una fila fija

```bash
uv run python -m tablero.io.sensores medir Y0
```

El programa deja la fila Y0 encendida y muestra, en una línea que se actualiza sola, qué columnas
`D0`…`D7` detectan pieza (`#`). Imprime las tres mediciones; hacelas en orden, con el multímetro
en voltaje continuo:

1. Punta negra en la pata 8 del 138 y roja en la pata 15 (Y0): **menos de 0,3 V**.
2. Punta negra en el GND de un Hall de esa fila y roja en su Vcc: **3 V o más**.
3. Mové la pieza por el tablero hasta que aparezca un `#` en la línea (esa casilla es de la fila
   Y0). Dejala ahí, y con la punta negra en la pata 8 del 138, medí con la roja la pata del 165
   de esa columna (el mensaje dice qué pata es cada D): **menos de 0,8 V**. Sacá la pieza: tiene
   que subir a **~3,3 V**.

Después llená de piezas las 8 casillas de esa fila y repetí la medición 1 y la 3.

Cortá con `Ctrl+C`.

✅ Las tres mediciones dan lo esperado, también con la fila llena.
⛔ Si la 1 da 0,3 V o más, la 2 menos de 3 V o la 3 da 0,8 V o más, pará: es un problema del
circuito, no del software (ver `hardware-docs/celdas-hall.md`).

📝 **Resultado** (las tres mediciones, con una pieza y con la fila llena):

---

## Parte 4 · Sensores e imanes

### 6. Tablero vacío

```bash
uv run python -m tablero.io.sensores matriz
```

El programa queda corriendo y redibuja la pantalla cada vez que cambia algo. Muestra dos
dibujos; **por ahora mirá solo el de arriba**, "Matriz cruda". El de abajo, "Tablero mapeado",
recién tiene sentido después de mapear (Parte 6).

```
Matriz cruda (# = Hall activo):
      D0 D1 D2 D3 D4 D5 D6 D7
  Y0   .  .  .  .  .  .  .  .
  Y1   .  .  .  .  .  .  .  .
  ...
```

✅ Con el tablero vacío, todo en `.`.
⛔ Si hay algún `#`, pará.

📝 **Resultado:**

Dejá el programa corriendo para los ítems 7 a 9.

### 7. Una pieza

Apoyá la pieza en cualquier casilla y después levantala. Si no aparece nada, dala vuelta (el
imán puede estar al revés) y probá de nuevo.

✅ Al apoyarla aparece **un solo** `#`; al levantarla, desaparece.
⛔ Si aparece una **columna entera** de `#` (la misma D en todas las Y), pará: el GND de ese Hall
no está conectado a su fila.
⛔ Si el `#` queda después de levantar la pieza, pará: el sensor no es del tipo correcto.

📝 **Resultado:**

### 8. Centro y bordes de la casilla

En las casillas **a1, d4 y h8**, apoyá la pieza:

- centrada en la casilla;
- corrida hacia cada uno de los 4 bordes de la casilla.

✅ En todas las posiciones hay **exactamente un** `#`. Si no aparece ninguno, el sensor no la
detecta en esa posición. Si aparecen dos, el imán está activando también la casilla vecina.

📝 **Resultado** (casilla, posición y cuántos `#` aparecieron):

### 9. Todas las piezas (polaridad)

Los sensores Hall solo detectan **un polo** del imán: el sur. Apoyá cada una de las 32 piezas, de
a una, en la misma casilla (por ejemplo d4).

- Si la pieza enciende el `#`: marcala como lista.
- Si no lo enciende: el imán de esa pieza está al revés. Hay que darlo vuelta dentro de la pieza
  (o anotarla para que Tino lo arregle).

✅ Al final, las 32 piezas encienden el `#`.

📝 **Piezas que hubo que dar vuelta y piezas que no se detectan ni dadas vuelta:**

Cuando termines, cortá el programa con `Ctrl+C`.

---

## Parte 5 · Calibración de los tiempos

### 10. Calibrar

```bash
uv run python -m tablero.io.sensores calibrar
```

Tiene tres pasos y te va guiando:

1. **Reposo**: te pide el tablero vacío. Apretá Enter y esperá 3 segundos.
2. **Tiempo de encendido**: te pide la posición inicial completa (32 piezas). Armala, apretá
   Enter y esperá: imprime una tabla con distintos tiempos.
3. **Estabilidad**: dejá las piezas como están, apretá Enter y **no toques el tablero** durante
   10 segundos.

✅ Termina imprimiendo dos líneas que empiezan con `HALL_ESPERA_ENCENDIDO` y
`HALL_LECTURAS_ESTABLES`.
⛔ Si aparece `FALLA` o un `AVISO`, pará.

📝 **Resultado** (copiá todo lo que imprimió desde el paso 2):

### 11. Guardar la calibración

```bash
nano src/tablero/config.py
```

1. Apretá `Ctrl+W`, escribí `HALL_ESPERA_ENCENDIDO:` y Enter.
2. Borrá esa línea con `Ctrl+K` y pegá en su lugar la línea `HALL_ESPERA_ENCENDIDO: ...` que
   imprimió la calibración.
3. Lo mismo con `HALL_LECTURAS_ESTABLES:`.
4. Guardá con `Ctrl+O` y Enter; salí con `Ctrl+X`.

Para confirmar que quedó bien:

```bash
grep -nE "^HALL_(ESPERA_ENCENDIDO|LECTURAS_ESTABLES)" src/tablero/config.py
```

✅ Muestra las dos líneas, iguales a las del ítem 10.
⛔ Si no, pará.

No hace falta commitear: Tino se encarga.

📝 **Resultado:**

---

## Parte 6 · Mapeo de los Hall

### 12. Mapear

Con el tablero vacío y una sola pieza a mano:

```bash
uv run python -m tablero.io.sensores mapear
```

Te va a pedir las 64 casillas en orden: a1, b1, … h1, a2, … h8. Para cada una:

1. Poné la pieza en la casilla que pide (sacándola de la anterior).
2. **Después** apretá Enter.

Si te equivocaste de casilla, escribí `r` y Enter: vuelve a la casilla anterior. Si dice
`Se detectaron N celdas`, `No se detectó la pieza` o `ya quedó como`, se repite la misma casilla:
revisá que no haya otra pieza en el tablero y que la pieza esté en la casilla que pide.

✅ Termina imprimiendo un bloque de 10 líneas que empieza con `CASILLA_DE_CELDA_HALL` y termina
con `)`.

📝 **Resultado** (copiá el bloque, y la última línea, la que dice si el cableado es una grilla):

### 13. Guardar el mapeo

```bash
nano src/tablero/config.py
```

1. Apretá `Ctrl+W`, escribí `CASILLA_DE_CELDA_HALL:` y Enter. El cursor queda en esa línea.
2. Apretá `Ctrl+K` **10 veces**: borra la línea del nombre, las 8 líneas de `Y0` a `Y7` y la del
   `)` de cierre.
3. Pegá en su lugar el bloque que imprimió el mapeo (clic derecho o `Ctrl+Shift+V` en la terminal).
4. Guardá con `Ctrl+O` y Enter; salí con `Ctrl+X`.

Para confirmar que quedó bien:

```bash
grep -n -A9 "^CASILLA_DE_CELDA_HALL" src/tablero/config.py
uv run pytest tests/test_matriz.py -q
```

✅ El `grep` muestra el bloque igual al del ítem 12, y `pytest` termina con `passed`, sin
`failed` (uno de esos tests revisa que la tabla tenga las 64 casillas sin repetir).
⛔ Si no, pará.

📝 **Resultado:**

---

## Parte 7 · LEDs

### 14. Todos los LEDs

```bash
uv run python -m tablero.io.leds todos
```

Las 64 casillas se prenden en rojo, verde, azul y blanco, 2 segundos cada color. Puede pedir la
contraseña de `sudo`.

✅ Se prenden las 64, con los colores en ese orden.
⛔ Si no prende ninguno, pará.

📝 **Resultado** (si hay LEDs apagados, o si el rojo y el verde salen cambiados):

### 15. Asociar cada LED a su casilla

Con una sola pieza a mano:

```bash
uv run python -m tablero.io.prueba_tablero leds
```

Se prende un LED por vez, en blanco. Para cada uno:

1. Poné la pieza en la casilla que se iluminó (sacándola de la anterior).
2. **Después** apretá Enter.

Si el LED no ilumina ninguna casilla, escribí `-` y Enter. Si te equivocaste, `r` y Enter.

✅ Termina imprimiendo un bloque de 10 líneas que empieza con `LED_DE_CASILLA` y termina con `)`.

📝 **Resultado** (copiá el bloque):

### 16. Guardar la asociación

```bash
nano src/tablero/config.py
```

1. Apretá `Ctrl+W`, escribí `LED_DE_CASILLA:` y Enter.
2. Borrá con `Ctrl+K` todas las líneas desde la de `LED_DE_CASILLA` hasta la del `)` de cierre,
   inclusive: son **3** si es la primera vez y 10 si ya se había guardado antes.
3. Pegá el bloque del ítem 15.
4. Guardá con `Ctrl+O` y Enter; salí con `Ctrl+X`.

Para confirmar que quedó bien:

```bash
uv run python -c "from tablero import config; t = config.LED_DE_CASILLA; print(len(t), len(set(t)))"
```

✅ Imprime `64 64`.
⛔ Si no, pará.

📝 **Resultado:**

---

## Parte 8 · Verificación del tablero completo

### 17. Recorrido de las 64 casillas

Con una sola pieza:

```bash
uv run python -m tablero.io.prueba_tablero recorrido
```

Se prende una casilla en azul: llevá la pieza ahí. Si la detecta bien, se pone verde y pasa sola
a la siguiente (a1, b1, … h8). Si se prende una casilla en rojo, la pieza se está detectando en
otra casilla: anotala. Si una casilla no avanza nunca, apretá Enter para saltearla.

✅ Termina con `OK: las 64 casillas se detectaron donde se prendieron.`

📝 **Resultado** (copiá las líneas de `FALLA` y `Salteadas` del final, si hay):

### 18. Posición inicial

```bash
uv run python -m tablero.io.prueba_tablero inicial
```

Armá la posición inicial completa (32 piezas). Verde = bien, rojo = falta pieza, amarillo = sobra.
Esperá unos segundos sin tocar nada.

✅ Las 32 casillas quedan en verde, aparece `Posición inicial completa (32 piezas).` y no cambia
mientras no toques nada.

📝 **Resultado** (si no se completa, qué casillas quedan en rojo o amarillo):

Cortá con `Ctrl+C`.

### 19. Filas del medio

```bash
uv run python -m tablero.io.prueba_tablero espejo
```

Mové las 32 piezas a las filas 3, 4, 5 y 6 y esperá unos segundos. Cada casilla con pieza se
prende en verde.

✅ Las filas 3 a 6 quedan enteras en verde, y no cambia.
Si alguna pieza parpadea o desaparece, **no lo dejes corriendo así**: anotá cuál y cortá con
`Ctrl+C`.

📝 **Resultado:**

### 20. Mano y arrastre

Con `espejo` corriendo (volvé a correrlo si lo cortaste), pasá la mano por encima del tablero y
arrastrá algunas piezas de una casilla a otra.

✅ No se prenden ni se apagan casillas que no tocaste, y la luz sigue a las piezas que movés.

📝 **Resultado:**

Cortá el programa con `Ctrl+C`.

---

## Al terminar

Pasale a Tino tu copia con todas las líneas 📝 completas.

El detalle técnico de cada prueba y cómo interpretar las fallas está en
`software-docs/sensores.md` ("Cómo probarlo" → "Matriz") y `software-docs/prueba-tablero.md`. La
conexión de cada Hall, sus riesgos eléctricos y qué medir están en `hardware-docs/celdas-hall.md`;
las conexiones de los chips pata por pata, en `hardware-docs/conexiones-matriz.md`.
