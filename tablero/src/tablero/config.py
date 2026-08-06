"""Configuración general del proyecto (pines GPIO, motor, etc.)."""

import shutil

# Ruta al binario de stockfish: se autodetecta en PATH; si no se encuentra,
# se deja el nombre solo para que el error de arranque sea explícito.
STOCKFISH_PATH: str = shutil.which("stockfish") or "stockfish"
STOCKFISH_MOVETIME: float = 1.0  # segundos por jugada, ver motor/stockfish.py
