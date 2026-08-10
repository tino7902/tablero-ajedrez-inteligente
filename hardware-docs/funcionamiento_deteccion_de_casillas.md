## El 74HC138 (Escaneo de Filas)

Este chip es un _decodificador_. Su función principal es recibir un número binario de 3 bits (del 0 al 7) en sus pines de entrada (A, B, C) y activar una sola de sus 8 salidas (Y0 a Y7).

- _Lógica activa en BAJA:_ Cuando una salida se activa, su voltaje cae a 0V (LOW o GND). Las otras 7 salidas permanecen en 5V/3.3V (HIGH).
- _Rol en el tablero:_ Actúa como el "selector". La Raspberry Pi le dice a este chip: "Conecta la fila 'a' a tierra". Solo los sensores de esa fila tendrán el potencial de cerrar un circuito hacia tierra.

## El 74HC165 (Lectura de Columnas)

Este chip es un _registro de desplazamiento (Shift Register)_. Tiene 8 pines de entrada paralela (D0 a D7) que leen el estado de las 8 columnas de forma simultánea.

- _Pin SH/PL (Shift/Load):_ Cuando este pin recibe un pulso bajo (LOW), el chip "toma una fotografía" del estado actual de los 8 pines paralelos y la guarda en su memoria interna.
- _Pin CLK (Clock):_ Con cada pulso de reloj (transición de LOW a HIGH), el chip empuja los datos guardados en fila india hacia el exterior.
- _Pin Q7 (Serial Out):_ Por aquí sale la información en serie, bit por bit, hacia la Raspberry Pi.
- _Rol en el tablero:_ Actúa como el "recolector". Toma el estado de las 8 columnas al mismo tiempo y se lo envía a la Raspberry Pi usando solo un pin de datos.
