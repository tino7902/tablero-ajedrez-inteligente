"""Configuración general del proyecto (pines GPIO, motor, etc.)."""

import shutil

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
