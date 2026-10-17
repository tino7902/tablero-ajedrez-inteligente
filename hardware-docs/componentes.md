## 1. Lista de Componentes y Cantidades

- _1x Raspberry Pi 3 Model B (v1.2):_ Procesador principal.
- _1x Pantalla Táctil LCD 3.5” (320x480, V3):_ Interfaz principal. Selector de oponentes (2 Jugadores Humanos o Humano vs. Máquina). Configuración del reloj
- _2x Interruptores Fin de Carrera (Limit Switches):_ Utilizados como los botones físicos del reloj de ajedrez (Jugador 1 y Jugador 2). Al ser de pulsación corta y mecánica, ofrecen una respuesta táctil rápida.
- _2x Resistencias (ej. 10 kΩ):_ Configuradas como Pull-down (o Pull-up) a 3.3V para fijar el estado lógico de los botones del reloj y evitar falsos disparos.
- _64x Sensores Hall A3144 (módulos KY-003):_ Detectan la presencia física de las piezas en cada casilla. Digitales y unipolares: solo reaccionan al polo sur del imán. Alimentados a 5 V desde el Arduino Nano; el GND de cada Hall va al bus de su fila, que conecta a GND el NPN de esa fila. Armado en `matriz-hall-nano.md`. Reemplazaron a los 64 reed switches de la v1 (historial en `historial-deteccion.md`).
- _1x Arduino Nano (ATmega328P):_ Barre la matriz de sensores y le pasa el estado del tablero a la Raspberry Pi por USB (v3, decidida el 2026-10-17; ver `matriz-hall-nano.md`).
- _8x Transistores NPN (BC547, BC337, 2N3904, 2N2222 o S8050):_ Uno por fila; conectan a GND el bus de GND de la fila elegida y manejan su corriente (~35 mA, que el 74HC138 no podía dar).
- _8x Resistencias 1 kΩ:_ Base de cada NPN.
- _8x Resistencias 10 kΩ:_ Entre base y GND de cada NPN, para mantenerlo apagado.
- _64x Imanes de Neodimio:_ Instalados en la base de las piezas para activar los sensores Hall, **todos con el polo sur hacia abajo** (el A3144 no detecta el polo norte).
- _64x Diodos (ej. 1N4148, o mejor Schottky como BAT85 o 1N5819):_ En serie con la salida de cada Hall, con la banda hacia el Hall, para prevenir lecturas fantasma (ghosting). Un Schottky deja más margen en el nivel bajo de la columna.
- ~~_1x IC 74HC138, 1x IC 74HC165 y 8x pull-ups de 10 kΩ a 3,3 V:_~~ Selector de filas y lector de columnas de la v1 y la v2. **Ya no se usan**: el 138 no aguantaba la corriente de los Hall (ver `historial-deteccion.md`). Las columnas usan las pull-ups internas del Nano (opcional: 8 × 10 kΩ externas a 5 V).
- _65x LEDs WS2812B (Neopixels):_ 64 para la iluminación del tablero y 1 LED extra de "sacrificio".
- _1x Fuente de Alimentación Externa (5V, >4A):_ Alimentación exclusiva para la matriz de LEDs.
- _1x Diodo Rectificador (ej. 1N4007):_ Para bajar el voltaje del LED de sacrificio a ~4.3V.

---

## 2. Asignación de Pines GPIO

_Reloj de Ajedrez (Entradas Digitales):_

- _GPIO 13_ (Pin 33) → Botón de Reloj - Jugador 1
- _GPIO 19_ (Pin 35) → Botón de Reloj - Jugador 2

_Iluminación LED (Salida Hardware PWM):_

- _GPIO 12_ (Pin 32) → Datos de LEDs WS2812B (al LED de sacrificio)

_Detección de Tablero:_ desde la v3 la matriz la lee el Arduino Nano, conectado a la Pi por
**USB**, y no usa ningún pin GPIO de la Pi (pines del Nano en `matriz-hall-nano.md`). Los pines de
abajo eran los de la v1 y la v2; quedan libres cuando se desconecta la matriz, aunque
`config.py` y `io/matriz.py` todavía los usan hasta que se escriba el lector por USB.

_(v1/v2) Detección de Tablero - Lector 74HC165:_

- _GPIO 5_ (Pin 29) → Carga Paralela (SH/PL)
- _GPIO 6_ (Pin 31) → Reloj de datos (CLK)
- _GPIO 16_ (Pin 36) → Lectura de datos (Q7 / Serial Out)

_(v1/v2) Detección de Tablero - Selector 74HC138:_

- _GPIO 20_ (Pin 38) → Selección Bit A
- _GPIO 21_ (Pin 40) → Selección Bit B
- _GPIO 26_ (Pin 37) → Selección Bit C

Conexiones de los dos chips pata por pata (y cómo verificarlas con el multímetro) en
`conexiones-matriz.md`.
