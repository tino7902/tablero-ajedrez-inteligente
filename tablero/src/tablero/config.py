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
