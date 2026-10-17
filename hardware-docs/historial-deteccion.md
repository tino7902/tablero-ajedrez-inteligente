# Historial de la detección de casillas

Cómo fue cambiando el circuito que detecta las piezas, por qué se cambió cada vez y qué se
descartó. La versión actual es la **v3 (Arduino Nano)**, documentada en `matriz-hall-nano.md`.

| Versión | Sensores | Quién barre la matriz | Estado |
|---|---|---|---|
| v1 | 64 reed switches + diodo | Raspberry Pi → 74HC138 + 74HC165, a 3,3 V | Reemplazada |
| v2 | 64 Hall A3144 / KY-003 + diodo | Raspberry Pi → 74HC138 + 74HC165, a 3,3 V | Descartada: el 138 no aguanta la corriente |
| **v3** | 64 Hall A3144 / KY-003 + diodo | **Arduino Nano** → 8 NPN, Hall a 5 V, USB a la Pi | **Actual** (decidida el 2026-10-17, sin armar todavía) |

## v1: reed switches con 74HC138 + 74HC165

Cada casilla tenía un reed switch en serie con un diodo: **columna → reed → diodo → fila**. La
Pi elegía la fila con el 74HC138 (salida activa en LOW) y leía las 8 columnas con el 74HC165.
Los reed no necesitan alimentación, así que el 138 solo tenía que hundir la corriente de las
pull-ups de las columnas.

- Documentación: `conexiones-matriz.md` ("Celdas reed + diodo"), `checklist-prueba-matriz-reed.md`,
  `software-docs/sensores-reed.md`.
- Código: `io/sensores_reed.py` (se conserva) sobre `io/matriz.py`.
- Por qué se dejó: se cambió a sensores Hall a último momento. El mapeo reed nunca se llegó a
  calibrar en el prototipo.

## v2: Hall con los mismos chips

Para no cambiar los chips, el **GND de cada Hall se conectó a la salida Y del 138 de su fila**:
la fila elegida queda en LOW y sus 8 Hall reciben alimentación; las demás quedan con 3,3 V en
Vcc y en GND, apagadas. Detalle en `celdas-hall.md`.

Ese documento ya marcaba dos riesgos eléctricos: que una salida del 138 no alcanzara para 8 Hall
(riesgo 1) y que el A3144 a 3,3 V estuviera por debajo de su mínimo de 4,5 V (riesgo 2).

**Qué pasó:** al probar el 138, la salida activa marcó **1,6 V en vez de 0 V**, y se confirmó
que el problema era la corriente:

- 8 Hall × ~4,4 mA ≈ **35 mA** por fila, más los LEDs de los KY-003 de las casillas con pieza.
- El 74HC138 tiene un máximo absoluto de 25 mA por pata y garantiza solo 4–5 mA a 3,3 V.
- Con 1,6 V en el GND, a los Hall les quedaban ~1,7 V: no funcionan.

No tiene arreglo por software: es un límite físico de la salida del chip.

## Alternativas evaluadas (2026-10-17)

Todas apuntan a lo mismo: que algo con capacidad de corriente maneje cada fila, o que la fila
consuma menos.

| Alternativa | Resultado | Por qué |
|---|---|---|
| 74HC238 + un NPN por fila | Descartada | Funciona (mismo pinout que el 138, salidas activas en HIGH), pero el 238 no se consigue. Sacarlo de equipos viejos es una lotería. |
| Hall de bajo consumo (DRV5032, AH1806, A3213…) | Descartada | Resolvería todo sin tocar el circuito, pero no se consiguen. |
| 74LVC138A / 74AC138 en el mismo zócalo | Descartada | Garantizan ~24 mA: no alcanza para 35 mA más los LEDs. |
| PNP solo, alimentando el Vcc de la fila | Descartada | En una fila apagada, la columna alimenta el Vcc flotante a través de la pull-up de 10 kΩ del KY-003. La columna queda en ~1,5 V, en la zona indefinida del 165. |
| PNP como seguidor de emisor en el GND de la fila | Descartada | Agrega ~0,7 V al GND de los Hall: la columna no baja del umbral del 165. |
| ULN2803 | Descartada | Es un Darlington: ~0,9 V de caída en conducción. A 3,3 V los Hall quedan con ~2,4 V. |
| 2N7000 como llave | Descartada | Su umbral puede llegar a 3 V: a 3,3 V no conduce de forma confiable. |
| 138 + PNP + NPN por fila | Viable, no elegida | El PNP invierte la Y y el NPN maneja la corriente. Funciona con transistores comunes, pero los Hall siguen a 3,3 V (riesgo 2 sin resolver). |
| 138 + compuerta inversora + NPN por fila | Viable, no elegida | Cualquier NOT/NAND/NOR/XOR reemplaza al PNP. Mismo problema: los Hall siguen a 3,3 V. Además, las familias de 5 V (HCT, LS) que había a mano obligaban a alimentar las compuertas aparte. |
| Arduino Nano + 165 (opción B) | Viable, no elegida | Reusa la placa de columnas, pero suma un chip que hace lo mismo que 8 pines del Nano. |
| Arduino Nano + 138 + compuertas + 165, todo a 5 V (opción C) | Viable, no elegida | Reusa toda la placa, pero tiene más piezas y más soldaduras que A para hacer lo mismo. |
| **Arduino Nano directo + un NPN por fila (opción A)** | **Elegida** | Ver abajo. |

ESP32 y Raspberry Pi Pico también estaban a mano. Se descartaron porque trabajan a 3,3 V: los Hall
quedarían otra vez por debajo de su mínimo.

## v3 (actual): Arduino Nano + un NPN por fila

El Nano reemplaza al 138 y al 165. 8 pines (D2–D9) encienden las filas a través de un NPN cada
uno, y 8 pines (D10, D11, D12, A0–A4) leen las columnas con pull-up. Los Hall pasan a 5 V. El
Nano se conecta a la Pi por USB, que lo alimenta y transmite los datos.

Por qué esta:

- **Resuelve los dos riesgos a la vez:** el NPN maneja los ~35 mA de la fila (un pin del Nano
  solo le da ~4 mA a la base) y los Hall trabajan a 5 V, dentro de la hoja de datos del A3144.
- **Menos piezas:** no hay chips intermedios. Por fila, un NPN y dos resistencias.
- **Sin problemas de niveles:** el Nano y la matriz trabajan a 5 V, y la Pi lo ve solo por USB.
  Ningún pin de la Pi queda conectado a la matriz.
- **Usa lo que había a mano:** NPN y un Arduino Nano.

Lo que cuesta:

- **Cambia un principio del proyecto.** Hasta la v2, todo corría en la Raspberry, "sin hardware
  ni proceso adicional". Ahora el Nano es un periférico con su propio firmware. La lógica del
  juego, el motor y la interfaz siguen en la Pi.
- **Hay que escribir firmware** para el Nano y cambiar el lado Pi: `io/matriz.py` deja de manejar
  GPIO y pasa a leer el puerto serie. Las herramientas `medir`, `calibrar` y `mapear` de
  `io/sensores.py` hay que adaptarlas. **Nada de esto está hecho todavía.**
- **Libera 6 pines de la Pi** (29, 31, 36, 37, 38, 40), que ya no se usan para la matriz.

Cada fila y columna conserva el número que tenía con el 138 y el 165 (fila Fk = cable que iba a
Yk, columna Ck = cable que iba a Dk), para que el mapeo celda → casilla
(`CASILLA_DE_CELDA_HALL`) no cambie.

Guía de armado: `matriz-hall-nano.md`. Versión web, para el equipo de hardware:
https://claude.ai/artifact/Y4zNzHhxoWoaWzvcRwRLkU
