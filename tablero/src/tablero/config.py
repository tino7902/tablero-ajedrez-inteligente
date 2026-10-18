"""Configuración general del proyecto (pines GPIO, motor, etc.)."""

import shutil
from pathlib import Path

# Ruta al binario de stockfish: se autodetecta en PATH; si no se encuentra,
# se deja el nombre solo para que el error de arranque sea explícito.
STOCKFISH_PATH: str = shutil.which("stockfish") or "stockfish"
STOCKFISH_MOVETIME: float = 1.0  # segundos por jugada, ver motor/stockfish.py

# Pantalla táctil RPI LCD V3 (480x320, ILI9486 + touch XPT2046), ver io/pantalla.py.
# Requiere el overlay de kernel `piscreen` activado en config.txt de la Raspberry; la
# rotación física se configura ahí (parámetro `rotate=`), no acá, porque el driver ya
# entrega el framebuffer con la orientación final.
PANTALLA_ANCHO: int = 480
PANTALLA_ALTO: int = 320
PANTALLA_TAMANO_FUENTE: int = 48

# Coeficientes de calibración táctil generados por io/calibracion_touch.py (ver
# "Precisión táctil" en software-docs/pantalla.md). No se trackea en git: depende
# del panel físico específico, igual que el rotate= del overlay piscreen.
CALIBRACION_TOUCH_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent / "calibracion_touch.json"
)

# Reloj de ajedrez: botones físicos (2x interruptores fin de carrera / limit
# switches), ver io/sensores.py. Cada uno conecta el pin a GND al presionarse
# (activo en bajo); numeración BOARD (física), igual que en
# hardware-docs/componentes.md, sección "Asignación de Pines GPIO"; equivalente
# BCM entre paréntesis.
PIN_BOTON_RELOJ_JUGADOR_1: int = 33  # GPIO 13 (BCM)
PIN_BOTON_RELOJ_JUGADOR_2: int = 35  # GPIO 19 (BCM)

# -- Matriz de detección de casillas: Arduino Nano (v3) ------------------------------
# Un Arduino Nano barre la matriz (un NPN por fila) y la Pi le pide cada lectura por USB
# serie, ver io/matriz.py, firmware/matriz-nano/ y hardware-docs/matriz-hall-nano.md.
# Puerto serie del Nano. None = autodetectar: se usa el único /dev/ttyUSB* o /dev/ttyACM*
# que haya; si hay varios, poner acá el del Nano (mejor el de /dev/serial/by-id/, que no
# cambia entre reinicios).
NANO_PUERTO: str | None = None

# -- Matriz: versión Hall (la actual, io/sensores.py) --------------------------------
# 64 sensores Hall A3144 / KY-003, con el GND de cada uno en el bus de su fila: el NPN de
# la fila elegida lo conecta a GND y enciende solo esos 8 Hall (ver
# hardware-docs/matriz-hall-nano.md).
#
# Segundos que espera el Nano en cada fila, después de encenderla, antes de leer las
# columnas: lo que tardan los Hall en arrancar. Se le manda en microsegundos con `L <µs>`
# (máximo 50 ms). 1 ms es un placeholder generoso; el valor real lo mide
# `uv run python -m tablero.io.sensores calibrar` (ver software-docs/sensores.md).
HALL_ESPERA_ENCENDIDO: float = 0.001
# Lecturas iguales seguidas que tiene que dar la matriz antes de reportar un cambio
# (antirrebote del paso de la mano y de los Hall que dudan en el borde de la casilla).
# También lo recomienda `calibrar`.
HALL_LECTURAS_ESTABLES: int = 3
# Mapeo celda → casilla, uno por sensor: CASILLA_DE_CELDA_HALL[fila Fk][columna Ck] =
# nombre de la casilla, con Fk y Ck los números de cable de hardware-docs/matriz-hall-nano.md
# (los mismos que eran Yk del 74HC138 y Dk del 74HC165 en la v2). Sirve aunque el cableado
# no sea una grilla. El valor de abajo es un placeholder (identidad); se genera el real con
# `uv run python -m tablero.io.sensores mapear` (ver software-docs/sensores.md).
CASILLA_DE_CELDA_HALL: tuple[tuple[str, ...], ...] = (
    ("a8", "b8", "c8", "d8", "e8", "f8", "g8", "h8"),  # F0: C0..C7
    ("a7", "b7", "c7", "d7", "e7", "f7", "g7", "h7"),  # F1: C0..C7
    ("a6", "b6", "c6", "d6", "e6", "f6", "g6", "h6"),  # F2: C0..C7
    ("a5", "b5", "c5", "d5", "e5", "f5", "g5", "h5"),  # F3: C0..C7
    ("a4", "b4", "c4", "d4", "e4", "f4", "g4", "h4"),  # F4: C0..C7
    ("a3", "b3", "c3", "d3", "e3", "f3", "g3", "h3"),  # F5: C0..C7
    ("a2", "b2", "c2", "d2", "e2", "f2", "g2", "h2"),  # F6: C0..C7
    ("a1", "b1", "c1", "d1", "e1", "f1", "g1", "h1"),  # F7: C0..C7
)

# -- Matriz: versión reed (la anterior, io/sensores_reed.py) -------------------------
# Se conserva por si se vuelve a los reed switches (ver software-docs/sensores-reed.md).
#
# Lecturas iguales seguidas que tiene que dar la matriz antes de reportar un cambio
# (antirrebote de los reed switches y del paso de la mano sobre el tablero).
REED_LECTURAS_ESTABLES: int = 3

# Mapeo matriz cruda → casilla de ajedrez. La matriz se lee como
# [salida Y0..Y7 del 74HC138][entrada D0..D7 del 74HC165]; cada salida es una fila
# física y cada entrada una columna física, así que alcanza con dos permutaciones:
#   FILA_DE_SALIDA_138[y]  = fila de ajedrez (0 = fila 1, 7 = fila 8)
#   COLUMNA_DE_ENTRADA_165[d] = columna de ajedrez (0 = columna a, 7 = columna h)
# Los valores de abajo son un placeholder (identidad): en el esquemático las columnas
# no entran en orden al 74HC165. Se generan con
# `uv run python -m tablero.io.sensores_reed calibrar` (ver software-docs/sensores-reed.md).
FILA_DE_SALIDA_138: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)
COLUMNA_DE_ENTRADA_165: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)

# LEDs WS2812B, ver io/leds.py. rpi-ws281x usa numeración BCM (no BOARD): GPIO 12
# es el pin físico 32, canal PWM0. El LED 0 es el de sacrificio (adapta el nivel
# de la señal de datos, ver hardware-docs/componentes.md) y siempre queda apagado.
LED_GPIO_BCM: int = 12
LED_CANAL_PWM: int = 0
LED_CANTIDAD: int = 65
LED_INDICE_SACRIFICIO: int = 0
LED_BRILLO: int = 32  # 0-255; bajo por defecto: 64 LEDs en blanco al máximo son ~3,8 A
# Mapeo casilla → índice en la tira: LED_DE_CASILLA[chess.Square] (0 = a1, 1 = b1, ...,
# 63 = h8). El valor por defecto es un placeholder que supone la tira en serpentina
# desde a1 (fila 1 a→h, fila 2 h→a, ...) justo después del LED de sacrificio. Se
# genera el real con `uv run python -m tablero.io.leds calibrar`
# (ver software-docs/leds.md).
LED_DE_CASILLA: tuple[int, ...] = tuple(
    1 + fila * 8 + (7 - columna if fila % 2 else columna)
    for fila in range(8)
    for columna in range(8)
)

# Registro de partidas (ver logica/registro.py y software-docs/registro.md). No se
# trackea en git: son datos de ejecución, igual que la calibración táctil.
DIRECTORIO_REGISTROS: Path = Path(__file__).resolve().parent.parent.parent / "registros"
MAX_PARTIDAS_REGISTRADAS: int = 15  # PGN (movimientos legales + resultado)
MAX_DETALLES_REGISTRADOS: int = 5  # log detallado de eventos
