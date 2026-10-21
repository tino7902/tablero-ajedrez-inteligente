"""Tests de la lógica que hay en config.py (tablero/src/tablero/config.py).

No requieren hardware ni Stockfish: la búsqueda del binario se prueba reemplazando
`shutil.which` y `os.access`.
"""

from tablero import config


def test_stockfish_se_busca_primero_en_el_path(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda nombre: "/opt/bin/stockfish")

    assert config.buscar_stockfish() == "/opt/bin/stockfish"


def test_sin_stockfish_en_el_path_prueba_el_de_apt(monkeypatch):
    # Con sudo, secure_path no incluye /usr/games, que es donde lo instala apt.
    monkeypatch.setattr(config.shutil, "which", lambda nombre: None)
    monkeypatch.setattr(config.os, "access", lambda ruta, modo: ruta == "/usr/games/stockfish")

    assert config.buscar_stockfish() == "/usr/games/stockfish"


def test_sin_stockfish_en_ningun_lado_deja_el_nombre_solo(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda nombre: None)
    monkeypatch.setattr(config.os, "access", lambda ruta, modo: False)

    assert config.buscar_stockfish() == "stockfish"
