## 1. Lista de Componentes y Cantidades

- _1x Raspberry Pi 3 Model B (v1.2):_ Procesador principal.
- _1x Pantalla Táctil LCD 3.5” (320x480, V3):_ Interfaz principal. Selector de oponentes (2 Jugadores Humanos o Humano vs. Máquina). Configuración del reloj
- _2x Interruptores Fin de Carrera (Limit Switches):_ Utilizados como los botones físicos del reloj de ajedrez (Jugador 1 y Jugador 2). Al ser de pulsación corta y mecánica, ofrecen una respuesta táctil rápida.
- _2x Resistencias (ej. 10 kΩ):_ Configuradas como Pull-down (o Pull-up) a 3.3V para fijar el estado lógico de los botones del reloj y evitar falsos disparos.
- _64x Sensores Hall A3144 (módulos KY-003):_ Detectan la presencia física de las piezas en cada casilla. Digitales y unipolares: solo reaccionan al polo sur del imán. Cada fila se alimenta desde su salida del 74HC138 (GND de cada Hall a la salida Y de su fila); conexión y riesgos eléctricos en `celdas-hall.md`. Reemplazaron a los 64 reed switches de la versión anterior (ver `conexiones-matriz.md`, "Celdas reed + diodo").
- _64x Imanes de Neodimio:_ Instalados en la base de las piezas para activar los sensores Hall, **todos con el polo sur hacia abajo** (el A3144 no detecta el polo norte).
- _64x Diodos (ej. 1N4148, o mejor Schottky como BAT85 o 1N5819):_ En serie con la salida de cada Hall, con la banda hacia el Hall, para prevenir lecturas fantasma (ghosting). Un Schottky deja más margen en el nivel bajo de la columna.
- _1x IC 74HC138 (Demultiplexor de 3 a 8):_ Selector de filas para el barrido del tablero (Alimentado a 3.3V).
- _1x IC 74HC165 (Registro de Desplazamiento):_ Lector paralelo/serie de columnas (Alimentado a 3.3V).
- _8x Resistencias Pull-up (10 kΩ):_ Para mantener las columnas del tablero en 3.3V en estado de reposo.
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

_Detección de Tablero - Lector 74HC165:_

- _GPIO 5_ (Pin 29) → Carga Paralela (SH/PL)
- _GPIO 6_ (Pin 31) → Reloj de datos (CLK)
- _GPIO 16_ (Pin 36) → Lectura de datos (Q7 / Serial Out)

_Detección de Tablero - Selector 74HC138:_

- _GPIO 20_ (Pin 38) → Selección Bit A
- _GPIO 21_ (Pin 40) → Selección Bit B
- _GPIO 26_ (Pin 37) → Selección Bit C

Conexiones de los dos chips pata por pata (y cómo verificarlas con el multímetro) en
`conexiones-matriz.md`.
