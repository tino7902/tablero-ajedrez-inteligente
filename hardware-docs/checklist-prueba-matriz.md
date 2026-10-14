# Checklist: prueba de imanes y matriz de casillas

Pasos para probar los reed switches con los imanes de las piezas, calibrar el mapeo matriz →
casilla y verificar las 64 casillas. Detalle del código y de los comandos en
`software-docs/sensores.md`.

## 0. Antes de energizar (multímetro, con la Pi apagada)

- [ ] El pin 16 (Vcc) del 74HC138 y del 74HC165 va a **3,3 V, nunca a 5 V**. El pin 8 (GND) de
      los dos chips tiene que compartir tierra con la Pi.
- [ ] Las 8 resistencias pull-up de columna van a 3,3 V.
- [ ] En el 138: pin 6 a 3,3 V y pines 4 y 5 a GND. En el esquemático el pin 6 termina en un
      terminal sin nombre, así que confirmar que en el armado real llega a 3,3 V.
- [ ] En el 165: pin 15 (INH) y pin 10 (SER) a GND.
- [ ] La Pi lee desde el **pin 9 del 165 (QH)**, no desde el pin 7 (QH̄, que sale invertido). Va
      al pin 36 de la Pi.
- [ ] La banda de cada diodo (cátodo) mira hacia la línea de fila, la que va al 138.
- [ ] Ninguna columna está en corto con GND ni con otra columna.

## 1. Imanes contra reeds (un reed suelto, multímetro en continuidad y un pedazo del material del tablero)

- [ ] El imán cierra el reed a través del espesor real del tablero.
- [ ] **Punto muerto:** si el eje del imán queda perpendicular al reed y justo en el centro, a
      veces no cierra. Probar con la pieza centrada y corrida hacia cada borde de la casilla.
- [ ] El reed se abre al levantar la pieza, no queda pegado.
- [ ] Una pieza apoyada contra el borde de su casilla no cierra el reed de la casilla vecina.
- [ ] Probar todas las piezas, porque cada imán puede ser distinto.
- [ ] Opcional: todas las piezas con el mismo polo hacia abajo. Al reed le da igual, pero así las
      piezas vecinas se repelen en vez de atraerse.

## 2. Preparación en la Pi

- [ ] `git pull` y `uv sync` en `tablero/`.
- [ ] Decidir la orientación física: a1 es la casilla oscura a la izquierda de las blancas.
      Marcarla con cinta y usar **la misma** orientación al calibrar los LEDs
      (`software-docs/leds.md`).
- [ ] Alejar del tablero las piezas que no se estén usando. Una caja con 31 imanes al lado puede
      cerrar los reeds del borde.

## 3. Primera lectura

```bash
uv run python -m tablero.io.sensores matriz
```

Hasta calibrar, ignorar la parte de "Tablero mapeado" y mirar solo la matriz cruda.

| Qué se ve | Causa probable |
|---|---|
| Tablero vacío y todo en `.` | ✅ Bien |
| Todo en `#` | Q7 desconectado o tomado del pin 7, el 165 sin alimentación, o faltan las pull-ups |
| Nunca se enciende nada | El 138 está deshabilitado (pines 4, 5 o 6) o A/B/C están mal conectados |
| Una pieza enciende toda una fila Y | El CLK no llega (pin 31 de la Pi → pin 2 del 165) |
| Una columna D entera en `#` | Pull-up suelta en esa columna o columna en corto a GND |
| Celdas que parpadean sin tocar nada | Soldaduras. Si no es eso, subir `MATRIZ_LECTURAS_ESTABLES` en `config.py` |

## 4. Calibración (15 apoyadas: a1…h1, después a2…a8)

```bash
uv run python -m tablero.io.sensores calibrar
```

- [ ] Apoyar la pieza **y después** apretar Enter.
- [ ] Si sale algún `AVISO`, frenar: significa que el cableado no forma una grilla y el mapeo con
      dos permutaciones no alcanza.
- [ ] Copiar las dos líneas que imprime al final (`FILA_DE_SALIDA_138` y
      `COLUMNA_DE_ENTRADA_165`) en `tablero/src/tablero/config.py`.

## 5. Verificación casilla por casilla

Con el mapeo ya pegado, de nuevo `matriz`. La calibración mide 15 casillas y deduce las demás,
así que este paso es el que confirma las 64.

- [ ] Recorrer las 64 casillas con una sola pieza. El log `aparece pieza en X` tiene que coincidir
      con la casilla real.
- [ ] Armar la posición inicial: tienen que verse 32 `#` estables, con las filas 1, 2, 7 y 8
      llenas.
- [ ] Poner las 32 piezas en las filas 3 a 6: de nuevo 32 `#` estables.
- [ ] Pasar la mano por encima y arrastrar una pieza: no tienen que aparecer cambios fantasma.

Los dos pasos de 32 piezas prueban los diodos. Si una pieza parpadea o desaparece cuando hay otra
en su misma columna, hay un diodo faltante, en corto o invertido en esa columna. No dejarlo
corriendo así, porque deja dos salidas del 138 en corto (ver "Cómo probarlo" en
`software-docs/sensores.md`).

## Qué anotar

- La salida de `calibrar`, incluido cualquier `AVISO`.
- Las casillas que fallen en el paso 5 y cómo fallan (no se encienden, encienden otra casilla,
  parpadean).
- Si aparecieron cambios fantasma.
