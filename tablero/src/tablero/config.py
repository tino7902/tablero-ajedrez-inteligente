"""Configuración general del proyecto (pines GPIO, motor, etc.)."""

import os
import shutil
from pathlib import Path
from typing import NamedTuple

# Donde lo instala `apt install stockfish` en Raspberry Pi OS. `io/juego.py` se relanza con
# sudo por los LEDs, y el PATH de sudo (secure_path) normalmente no incluye /usr/games.
_STOCKFISH_APT = "/usr/games/stockfish"


def buscar_stockfish() -> str:
    """Ruta al binario de stockfish: primero el PATH, después el de apt.

    Si no está en ningún lado devuelve el nombre solo, para que el error al abrir el
    motor sea explícito.
    """
    if ruta := shutil.which("stockfish"):
        return ruta
    if os.access(_STOCKFISH_APT, os.X_OK):
        return _STOCKFISH_APT
    return "stockfish"


STOCKFISH_PATH: str = buscar_stockfish()
STOCKFISH_MOVETIME: float = 1.0  # segundos por jugada sin nivel, ver motor/stockfish.py


class NivelMagnus(NamedTuple):
    """Un nivel de Magnus (Stockfish) en el modo vs-máquina, ver motor/stockfish.py."""

    nombre: str  # para mostrar, con tildes: "fácil"
    skill_level: int  # opción UCI `Skill Level` de Stockfish, 0-20
    segundos_por_jugada: float


# Niveles del modo vs Magnus. Las claves van en ASCII porque son flags de la terminal
# (`juego.py --magnus facil`). Son valores iniciales para afinar jugando (por ejemplo con
# `uv run python -m tablero.simulacion --magnus facil`): `Skill Level 0` anda por los
# 1300 Elo según la calibración de Stockfish. Ver software-docs/vs-magnus.md.
NIVELES_MAGNUS: dict[str, NivelMagnus] = {
    "facil": NivelMagnus("fácil", 0, 0.1),
    "medio": NivelMagnus("medio", 6, 0.5),
    "dificil": NivelMagnus("difícil", 20, 1.0),
}

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
# no sea una grilla. Generado con `uv run python -m tablero.io.sensores mapear` el
# 2026-10-18 (ver software-docs/sensores.md): es una grilla, F0 = fila 8 … F7 = fila 1 y
# C0..C7 = columnas a..h.
CASILLA_DE_CELDA_HALL: tuple[tuple[str, ...], ...] = (
    ("h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8"),  # F0: C0..C7
    ("g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"),  # F1: C0..C7
    ("f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"),  # F2: C0..C7
    ("e1", "e2", "e3", "e4", "e5", "e6", "e7", "e8"),  # F3: C0..C7
    ("d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8"),  # F4: C0..C7
    ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"),  # F5: C0..C7
    ("b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8"),  # F6: C0..C7
    ("a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"),  # F7: C0..C7
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
LED_BRILLO: int = (
    32  # 0-LED_BRILLO_MAX; bajo por defecto: 64 LEDs en blanco al máximo son ~3,8 A
)
# Tope del brillo (75 % de 255): TiraLeds no pasa de acá aunque se pida más con --brillo.
LED_BRILLO_MAX: int = 191
# Mapeo casilla → índice en la tira: LED_DE_CASILLA[chess.Square] (0 = a1, 1 = b1, ...,
# 63 = h8). Generado con `uv run python -m tablero.io.prueba_tablero leds` el
# 2026-10-18 (ver software-docs/prueba-tablero.md): la tira va en serpentina desde h1
# (fila 1 h→a, fila 2 a→h, ...) justo después del LED de sacrificio.
# fmt: off
LED_DE_CASILLA: tuple[int, ...] = (
     8,  7,  6,  5,  4,  3,  2,  1,  # fila 1: a..h
     9, 10, 11, 12, 13, 14, 15, 16,  # fila 2: a..h
    24, 23, 22, 21, 20, 19, 18, 17,  # fila 3: a..h
    25, 26, 27, 28, 29, 30, 31, 32,  # fila 4: a..h
    40, 39, 38, 37, 36, 35, 34, 33,  # fila 5: a..h
    41, 42, 43, 44, 45, 46, 47, 48,  # fila 6: a..h
    56, 55, 54, 53, 52, 51, 50, 49,  # fila 7: a..h
    57, 58, 59, 60, 61, 62, 63, 64,  # fila 8: a..h
)
# fmt: on
# Registro de partidas (ver logica/registro.py y software-docs/registro.md). No se
# trackea en git: son datos de ejecución, igual que la calibración táctil.
DIRECTORIO_REGISTROS: Path = Path(__file__).resolve().parent.parent.parent / "registros"
MAX_PARTIDAS_REGISTRADAS: int = 15  # PGN (movimientos legales + resultado)
MAX_DETALLES_REGISTRADOS: int = 5  # log detallado de eventos
