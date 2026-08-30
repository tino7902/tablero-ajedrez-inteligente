"""Fixtures compartidas por los tests del paquete `tablero`."""

import pytest


class RelojFalso:
    """Fuente de tiempo controlada a mano, en segundos.

    Se le pasa a `RelojAjedrez`/`Partida` en lugar de `time.monotonic` para que los
    tests que involucran tiempo sean deterministas y no tengan que dormir.
    """

    def __init__(self) -> None:
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


@pytest.fixture
def tiempo() -> RelojFalso:
    """Reloj falso arrancado en cero."""
    return RelojFalso()
