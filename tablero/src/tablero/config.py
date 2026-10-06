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
CALIBRACION_TOUCH_PATH: Path = Path(__file__).resolve().parent.parent.parent / "calibracion_touch.json"

# Reloj de ajedrez: botones físicos (2x interruptores fin de carrera / limit
# switches), ver io/sensores.py. Cada uno conecta el pin a GND al presionarse
# (activo en bajo); numeración BOARD (física), igual que en
# hardware-docs/componentes.md, sección "Asignación de Pines GPIO"; equivalente
# BCM entre paréntesis.
PIN_BOTON_RELOJ_JUGADOR_1: int = 33  # GPIO 13 (BCM)
PIN_BOTON_RELOJ_JUGADOR_2: int = 35  # GPIO 19 (BCM)

# Matriz de detección de casillas (64 reed switches), ver io/sensores.py y
# hardware-docs/funcionamiento_deteccion_de_casillas.md. El 74HC138 elige qué fila
# se pone en LOW y el 74HC165 lee las 8 columnas; numeración BOARD, igual que los
# botones.
PIN_MATRIZ_SELECTOR_A: int = 38  # GPIO 20 (BCM) → 74HC138 A
PIN_MATRIZ_SELECTOR_B: int = 40  # GPIO 21 (BCM) → 74HC138 B
PIN_MATRIZ_SELECTOR_C: int = 37  # GPIO 26 (BCM) → 74HC138 C
PIN_MATRIZ_CARGA: int = 29  # GPIO 5 (BCM) → 74HC165 SH/LD
PIN_MATRIZ_RELOJ: int = 31  # GPIO 6 (BCM) → 74HC165 CLK
PIN_MATRIZ_DATOS: int = 36  # GPIO 16 (BCM) ← 74HC165 Q7

# Lecturas iguales seguidas que tiene que dar la matriz antes de reportar un cambio
# (antirrebote de los reed switches y del paso de la mano sobre el tablero).
MATRIZ_LECTURAS_ESTABLES: int = 3

# Mapeo matriz cruda → casilla de ajedrez. La matriz se lee como
# [salida Y0..Y7 del 74HC138][entrada D0..D7 del 74HC165]; cada salida es una fila
# física y cada entrada una columna física, así que alcanza con dos permutaciones:
#   FILA_DE_SALIDA_138[y]  = fila de ajedrez (0 = fila 1, 7 = fila 8)
#   COLUMNA_DE_ENTRADA_165[d] = columna de ajedrez (0 = columna a, 7 = columna h)
# Los valores de abajo son un placeholder (identidad): en el esquemático las columnas
# no entran en orden al 74HC165. Se generan con
# `uv run python -m tablero.io.sensores calibrar` (ver software-docs/sensores.md).
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
# genera el real con `sudo .venv/bin/python -m tablero.io.leds calibrar`
# (ver software-docs/leds.md).
LED_DE_CASILLA: tuple[int, ...] = tuple(
    1 + fila * 8 + (7 - columna if fila % 2 else columna) for fila in range(8) for columna in range(8)
)

# Registro de partidas (ver logica/registro.py y software-docs/registro.md). No se
# trackea en git: son datos de ejecución, igual que la calibración táctil.
DIRECTORIO_REGISTROS: Path = Path(__file__).resolve().parent.parent.parent / "registros"
MAX_PARTIDAS_REGISTRADAS: int = 15  # PGN (movimientos legales + resultado)
MAX_DETALLES_REGISTRADOS: int = 5  # log detallado de eventos
