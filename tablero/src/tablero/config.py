import shutil

STOCKFISH_PATH: str = shutil.which("stockfish") or "stockfish"
STOCKFISH_MOVETIME: float = 1.0  # segundos por jugada
