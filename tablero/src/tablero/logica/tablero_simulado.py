"""Tablero simulado para probar la pantalla en la notebook, sin el Nano.

Es una fuente de ocupación (`logica/sesion.py::FuenteOcupacion`) que se maneja con texto:
`e2e4` levanta la pieza de e2, saca la de e4 si había (captura) y la apoya en e4; `-e4`
solo levanta, `+e4` solo apoya, e `inicial` vuelve a la posición inicial. El enroque son
dos jugadas (`e1g1` y `h1f1`), igual que con la mano.

Cada paso se entrega en una lectura distinta, como lo vería la matriz: así el rastreador
ve vaciarse la casilla capturada y la captura cuenta (ver `software-docs/eventos.md`).
`io/menus.py` lo alimenta desde un hilo que lee la terminal, por eso `enviar` y `leer`
se pueden llamar desde hilos distintos.
"""

from __future__ import annotations

import queue
import re

import chess

from tablero.logica.eventos import Ocupacion, casillas_ocupadas

_JUGADA = re.compile(r"^([a-h][1-8])([a-h][1-8])$")
_UNA = re.compile(r"^([+-])([a-h][1-8])$")
AYUDA = "Jugadas: e2e4 (con captura también), -e4 levanta, +e4 apoya, inicial. Botones del reloj: ← y →."


class TableroSimulado:
    def __init__(self) -> None:
        self._ocupacion: Ocupacion = casillas_ocupadas(chess.Board())
        self._comandos: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._pendientes: list[Ocupacion] = [self._ocupacion]

    def enviar(self, texto: str) -> str | None:
        """Encola un comando; devuelve el error si no se entiende. Se puede llamar desde otro hilo."""
        texto = texto.strip().lower()
        if not (texto == "inicial" or _JUGADA.match(texto) or _UNA.match(texto)):
            return f"no entiendo {texto!r}. {AYUDA}"
        self._comandos.put(texto)
        return None

    def reiniciar(self) -> None:
        """La próxima lectura vuelve a entregar la ocupación actual (para una partida nueva)."""
        self._pendientes = [self._ocupacion]

    def leer(self) -> Ocupacion | None:
        """Un paso por lectura: la ocupación nueva, o `None` si no hay nada pendiente."""
        while not self._pendientes:
            try:
                self._pendientes = self._pasos(self._comandos.get_nowait())
            except queue.Empty:
                return None
        self._ocupacion = self._pendientes.pop(0)
        return self._ocupacion

    def _pasos(self, comando: str) -> list[Ocupacion]:
        ocupacion = self._ocupacion
        if comando == "inicial":
            return [casillas_ocupadas(chess.Board())]
        if m := _UNA.match(comando):
            casilla = chess.parse_square(m[2])
            return [ocupacion - {casilla} if m[1] == "-" else ocupacion | {casilla}]
        m = _JUGADA.match(comando)
        assert m is not None
        origen, destino = chess.parse_square(m[1]), chess.parse_square(m[2])
        pasos = [ocupacion := ocupacion - {origen}]
        if destino in ocupacion:
            pasos.append(ocupacion := ocupacion - {destino})
        pasos.append(ocupacion | {destino})
        return pasos
