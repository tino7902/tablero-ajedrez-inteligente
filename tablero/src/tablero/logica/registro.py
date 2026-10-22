"""Registro de partidas: PGN de las últimas 15 y log detallado de las últimas 5.

Lo alimenta `logica/partida.py`, así que registra por igual las partidas simuladas por
terminal (`tablero/simulacion.py`) y las que juegue el tablero físico cuando la pantalla
pase por `Partida` — el registro vive en `logica/` justamente para no depender de
hardware. Se apoya en `chess.pgn` para no reimplementar el formato PGN.

Layout en disco (bajo `config.DIRECTORIO_REGISTROS`, ignorado por git), un archivo por
partida, con el id `AAAAMMDD-HHMMSS`; rotar es borrar los más viejos:

    registros/
    ├── partidas/20260830-201455.pgn   ← las últimas 15: movimientos legales + resultado
    └── detalle/20260830-201455.log    ← las últimas 5: todo lo que pasó

`cat registros/partidas/*.pgn` produce un PGN multi-partida válido, abrible en Lichess o
cualquier visor de ajedrez.

Todo se escribe de forma incremental (el `.log` se anexa y el `.pgn` se reescribe entero
después de cada movimiento aceptado): un Ctrl+C o un corte de luz en la Raspberry deja el
registro completo hasta la última jugada, no un archivo vacío.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import chess
import chess.pgn

from tablero.logica.notacion import NOMBRES_COLOR
from tablero.logica.reloj import RelojAjedrez, formatear_duracion, formatear_tiempo

if TYPE_CHECKING:  # pragma: no cover - solo para tipos; en runtime sería circular
    from tablero.logica.partida import ResultadoBoton, ResultadoJugada

log = logging.getLogger(__name__)

SUBDIR_PARTIDAS = "partidas"
SUBDIR_DETALLE = "detalle"

# `Event` del PGN según de dónde viene la partida.
EVENTOS_POR_MODO = {
    "simulacion": "Simulación por terminal",
    "pvp": "Jugador vs Jugador (tablero)",
    "vs_magnus": "Jugador vs Magnus (tablero)",
    "simulacion_magnus": "Jugador vs Magnus (simulación)",
}


def _rotar(directorio: Path, patron: str, maximo: int) -> None:
    """Deja solo los `maximo` archivos más nuevos que matcheen `patron` en `directorio`.

    Se ordena por fecha de modificación y no por nombre: el id lleva la fecha, pero dos
    partidas del mismo segundo se desambiguan con un sufijo (`-2`) que rompería el orden
    alfabético.
    """
    archivos = sorted(directorio.glob(patron), key=lambda ruta: (ruta.stat().st_mtime_ns, ruta.name))
    for viejo in archivos[: max(0, len(archivos) - maximo)]:
        viejo.unlink(missing_ok=True)
        log.info("Registro rotado: se borró %s", viejo.name)


class RegistroPartida:
    """Registro de una partida: escribe su PGN y su log detallado mientras se juega."""

    def __init__(
        self,
        directorio: Path,
        *,
        modo: str = "simulacion",
        segundos_por_jugador: float | None,
        max_partidas: int = 15,
        max_detalles: int = 5,
        id_partida: str | None = None,
        extras_cabecera: str = "",
        blancas: str = "Blancas",
        negras: str = "Negras",
    ) -> None:
        """Crea los archivos de la partida y rota los registros viejos.

        `segundos_por_jugador=None` es una partida sin límite de tiempo (vs Magnus).
        `max_partidas`/`max_detalles` son cuántos `.pgn` y `.log` se conservan (los
        valores del proyecto están en `config.MAX_PARTIDAS_REGISTRADAS` y
        `config.MAX_DETALLES_REGISTRADOS`). `extras_cabecera` es texto libre que se
        agrega a la primera línea del log (la simulación pasa ahí el idioma elegido).
        `blancas`/`negras` son los nombres de `White`/`Black` en el PGN.
        """
        self._inicio = dt.datetime.now()
        self.id = id_partida or self._inicio.strftime("%Y%m%d-%H%M%S")
        self._modo = modo
        self._segundos_por_jugador = segundos_por_jugador
        self._nombres = {chess.WHITE: blancas, chess.BLACK: negras}
        self._cerrado = False

        dir_partidas = directorio / SUBDIR_PARTIDAS
        dir_detalle = directorio / SUBDIR_DETALLE
        dir_partidas.mkdir(parents=True, exist_ok=True)
        dir_detalle.mkdir(parents=True, exist_ok=True)

        # Dos partidas arrancadas dentro del mismo segundo compartirían id; se
        # desambigua con un sufijo para no pisar el registro de la anterior.
        sufijo = 1
        base = self.id
        while (dir_partidas / f"{self.id}.pgn").exists() or (dir_detalle / f"{self.id}.log").exists():
            sufijo += 1
            self.id = f"{base}-{sufijo}"

        self.ruta_pgn = dir_partidas / f"{self.id}.pgn"
        self.ruta_log = dir_detalle / f"{self.id}.log"

        tiempo = "sin límite" if segundos_por_jugador is None else f"{segundos_por_jugador / 60:g}min"
        extras = f" {extras_cabecera}" if extras_cabecera else ""
        self._escribir_log(
            f"partida iniciada — modo={modo} tiempo={tiempo}{extras}", con_transcurrido=False
        )
        self._escribir_pgn(chess.Board(), "*", None)

        # Recién ahora se rota: los archivos de esta partida ya existen y son los más
        # nuevos, así que el corte deja este más los `maximo - 1` anteriores. Rotar antes
        # liberaría el id que se acaba de descartar por colisión y se pisarían entre sí.
        _rotar(dir_partidas, "*.pgn", max_partidas)
        _rotar(dir_detalle, "*.log", max_detalles)

    # -- Anotaciones que hace `logica/partida.py` ---------------------------------

    def anotar_jugada(
        self, resultado: ResultadoJugada, reloj: RelojAjedrez, board: chess.Board
    ) -> None:
        """Anota un movimiento intentado; si fue aceptado, reescribe también el PGN."""
        jugador = NOMBRES_COLOR[resultado.turno].ljust(7)
        if resultado.aceptado:
            self._escribir_log(
                f"{jugador} intenta '{resultado.texto}' → ACEPTADO {resultado.san} "
                f"({resultado.descripcion}) {self._estado_reloj(reloj)}"
            )
            self._escribir_pgn(board, "*", None)
        else:
            self._escribir_log(
                f"{jugador} intenta '{resultado.texto}' → BLOQUEADO ({resultado.tipo.name}): "
                f"{resultado.motivo}"
            )

    def anotar_boton(self, resultado: ResultadoBoton, reloj: RelojAjedrez) -> None:
        """Anota una pulsación del botón del reloj (haya pasado el turno o no)."""
        color = NOMBRES_COLOR[resultado.color]
        if resultado.turno_nuevo is not None:
            self._escribir_log(
                f"botón {color} → TURNO PASADO a {NOMBRES_COLOR[resultado.turno_nuevo]} "
                f"{self._estado_reloj(reloj)}"
            )
        else:
            self._escribir_log(
                f"botón {color} → IGNORADO ({resultado.tipo.name}): {resultado.motivo}"
            )

    def anotar_tiempo_agotado(self, reloj: RelojAjedrez) -> None:
        """Anota que un jugador se quedó sin tiempo."""
        assert reloj.perdedor is not None
        self._escribir_log(
            f"tiempo agotado: {NOMBRES_COLOR[reloj.perdedor]} {self._estado_reloj(reloj)}"
        )

    def anotar_evento(self, texto: str) -> None:
        """Anota algo que no es ni jugada ni botón (por ejemplo, una oferta de tablas)."""
        self._escribir_log(texto)

    def cerrar(self, resultado: str, motivo: str, board: chess.Board) -> None:
        """Escribe el resultado final en el PGN y en el log. Idempotente."""
        if self._cerrado:
            return
        self._cerrado = True
        self._escribir_pgn(board, resultado, motivo)
        self._escribir_log(f"partida finalizada — {resultado} ({motivo})", con_transcurrido=False)

    # -- Escritura ----------------------------------------------------------------

    def _estado_reloj(self, reloj: RelojAjedrez) -> str:
        blancas, negras = reloj.restante(chess.WHITE), reloj.restante(chess.BLACK)
        if blancas is None or negras is None:  # sin límite de tiempo
            return (
                f"⏱ usado B {formatear_duracion(reloj.usado(chess.WHITE))} "
                f"· N {formatear_duracion(reloj.usado(chess.BLACK))}"
            )
        return f"⏱ B {formatear_tiempo(blancas)} · N {formatear_tiempo(negras)}"

    def _escribir_log(self, linea: str, *, con_transcurrido: bool = True) -> None:
        ahora = dt.datetime.now()
        marca = ahora.strftime("[%Y-%m-%d %H:%M:%S.%f")[:-3] + "]"
        if con_transcurrido:
            # Truncado, no redondeado hacia arriba como `formatear_tiempo`: acá interesa
            # el tiempo ya transcurrido desde el inicio, no lo que le queda a un jugador.
            minutos, segundos = divmod(int((ahora - self._inicio).total_seconds()), 60)
            marca = f"{marca} (t+{minutos:02d}:{segundos:02d})"
        with self.ruta_log.open("a", encoding="utf-8") as f:
            f.write(f"{marca} {linea}\n")

    def _escribir_pgn(self, board: chess.Board, resultado: str, motivo: str | None) -> None:
        juego = chess.pgn.Game.from_board(board)
        juego.headers["Event"] = EVENTOS_POR_MODO.get(self._modo, self._modo)
        juego.headers["Site"] = "Tablero de ajedrez inteligente"
        juego.headers["Date"] = self._inicio.strftime("%Y.%m.%d")
        juego.headers["Round"] = "-"
        juego.headers["White"] = self._nombres[chess.WHITE]
        juego.headers["Black"] = self._nombres[chess.BLACK]
        juego.headers["Result"] = resultado
        # "-" es el valor del estándar PGN para una partida sin control de tiempo.
        juego.headers["TimeControl"] = (
            "-" if self._segundos_por_jugador is None else f"{int(self._segundos_por_jugador)}"
        )
        if motivo is not None:
            juego.headers["Termination"] = motivo
        self.ruta_pgn.write_text(f"{juego}\n", encoding="utf-8")
