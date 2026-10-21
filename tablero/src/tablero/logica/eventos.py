"""Detección de jugadas a partir de la ocupación de las casillas.

Los sensores físicos (sensores Hall, ver `hardware-docs/`) solo reportan presencia o
ausencia de pieza por casilla, no qué pieza es. Este módulo responde, para cada lectura,
qué jugada representa la posición física comparándola con la ocupación que dejaría cada
jugada legal del tablero lógico. No depende de `io/sensores.py`: define su propia entrada
(`Ocupacion`, un `frozenset[chess.Square]`) para mantenerse testable sin hardware,
siguiendo el boundary documentado en `CLAUDE.md`.

**No aplica nada.** La jugada recién cuenta cuando el jugador aprieta su botón del reloj
(eso lo resuelve `logica/partida_fisica.py`): hasta entonces puede acomodar las piezas como
quiera, y cada lectura se reinterpreta desde cero. Por eso el enroque y las capturas, que
pasan por estados intermedios, no necesitan una máquina de estados: alcanza con comparar
la ocupación final. Ver `software-docs/eventos.md`.

Lo único que se recuerda entre lecturas es qué casillas se vaciaron y se volvieron a
ocupar desde la última posición de reposo, para desempatar capturas de una misma pieza a
casillas distintas (todas dejan la misma ocupación: `−origen`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto

import chess

from tablero.logica.estado_tablero import EstadoTablero
# Los nombres en español viven en `notacion.py` (el módulo de "lenguaje" del proyecto),
# compartidos con los mensajes de `logica/partida.py` y el log de `logica/registro.py`.
from tablero.logica.notacion import NOMBRES_COLOR as _NOMBRES_COLOR
from tablero.logica.notacion import NOMBRES_PIEZA as _NOMBRES_PIEZA

log = logging.getLogger(__name__)

Ocupacion = frozenset[chess.Square]


def casillas_ocupadas(board: chess.Board) -> Ocupacion:
    """Casillas ocupadas de `board` como `frozenset[chess.Square]`."""
    return frozenset(chess.SquareSet(board.occupied))


def ocupacion_tras(board: chess.Board, movimiento: chess.Move) -> Ocupacion:
    """Casillas ocupadas después de jugar `movimiento` (sobre una copia de `board`).

    Cubre todos los tipos de jugada sin casos especiales: normal y promoción
    (`−origen +destino`), captura (`−origen`), al paso (`−origen −peón +destino`) y
    enroque (`−rey −torre +rey' +torre'`).
    """
    copia = board.copy(stack=False)
    copia.push(movimiento)
    return casillas_ocupadas(copia)


def casillas_tocadas(board: chess.Board, movimiento: chess.Move) -> tuple[Ocupacion, Ocupacion]:
    """Casillas que cambian con `movimiento`: `(todas, origenes)`.

    `todas` son las casillas cuyo contenido cambia (origen, destino, la torre en el enroque,
    el peón capturado al paso); `origenes`, las que tenían una pieza del que mueve y quedan
    vacías (el origen y, en el enroque, la casilla de la torre).
    """
    antes = board.piece_map()
    copia = board.copy(stack=False)
    copia.push(movimiento)
    despues = copia.piece_map()
    todas = frozenset(sq for sq in antes.keys() | despues.keys() if antes.get(sq) != despues.get(sq))
    origenes = frozenset(
        sq for sq in todas if sq not in despues and antes[sq].color == board.turn
    )
    return todas, origenes


def _jugadas_detectables(board: chess.Board) -> list[chess.Move]:
    """Jugadas legales, con las promociones reducidas a la de dama.

    Las cuatro promociones de un peón dejan la misma ocupación y los sensores no ven qué
    pieza se puso, así que se asume dama (mismo criterio que tenía la versión anterior).
    """
    return [m for m in board.legal_moves if m.promotion in (None, chess.QUEEN)]


class TipoLectura(Enum):
    """Qué representa la posición física respecto del tablero lógico."""

    REPOSO = auto()  # coincide con el tablero lógico: no hay nada en curso
    JUGADA = auto()  # coincide con la ocupación de una jugada legal
    AMBIGUA = auto()  # coincide con varias capturas de la misma pieza y no hay cómo elegir
    INCOMPLETA = auto()  # no coincide con ninguna jugada legal (en curso o mal hecha)


@dataclass(frozen=True)
class Lectura:
    """Interpretación de una lectura de sensores.

    `faltan` son las casillas que en el tablero lógico tienen pieza y en el físico están
    vacías; `sobran`, al revés. Se completan siempre, también en una `JUGADA` (ahí son el
    diff de la jugada en curso). `candidatos` son todas las jugadas cuya ocupación coincide;
    en una `JUGADA` incluye la elegida.
    """

    tipo: TipoLectura
    ocupacion: Ocupacion
    movimiento: chess.Move | None = None
    candidatos: tuple[chess.Move, ...] = ()
    faltan: Ocupacion = field(default_factory=frozenset)
    sobran: Ocupacion = field(default_factory=frozenset)


class Marca(Enum):
    """Qué mostrar en una casilla (los colores los elige `io/`)."""

    ORIGEN = auto()  # pieza del que mueve que se está moviendo
    DESTINO = auto()  # adónde puede ir, o qué pieza rival se puede capturar
    JUGADA = auto()  # casillas de la jugada detectada, lista para confirmar con el botón
    FALTA = auto()  # debería tener pieza y no tiene
    SOBRA = auto()  # tiene pieza y no debería
    # Modo vs Magnus (`logica/partida_magnus.py`): la jugada de la máquina, que hay que
    # hacer a mano en el tablero.
    MAGNUS_ORIGEN = auto()  # tiene que quedar vacía (origen, torre del enroque, peón al paso)
    MAGNUS_DESTINO = auto()  # adonde va una pieza de Magnus (también la casilla de una captura)


class RastreadorMovimientos:
    """Interpreta lecturas sucesivas de ocupación contra el tablero de `estado`.

    Solo lee `estado.board`: quien aplica la jugada es `Partida`. Cuando el tablero lógico
    cambia (se confirmó una jugada), el historial de casillas se descarta solo.
    """

    def __init__(self, estado: EstadoTablero) -> None:
        self._estado = estado
        self._fen: str | None = None
        self._por_ocupacion: dict[Ocupacion, list[chess.Move]] = {}
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida el historial de lecturas; la próxima se compara contra el reposo."""
        self._anterior: Ocupacion | None = None
        self._vaciadas: set[chess.Square] = set()
        # Casilla → número de orden de la última vez que se volvió a ocupar después de
        # haberse vaciado. La captura se resuelve hacia la más reciente.
        self._reocupadas: dict[chess.Square, int] = {}
        self._contador = 0
        self._ultima: Lectura | None = None

    def _sincronizar_con_tablero(self) -> None:
        fen = self._estado.board.fen()
        if fen == self._fen:
            return
        self._fen = fen
        board = self._estado.board
        self._por_ocupacion = {}
        for movimiento in _jugadas_detectables(board):
            self._por_ocupacion.setdefault(ocupacion_tras(board, movimiento), []).append(movimiento)
        self.reiniciar()

    def _prefijo_log(self) -> str:
        board = self._estado.board
        return f"Jugada {board.fullmove_number} ({_NOMBRES_COLOR[board.turn]})"

    def _describir_casilla(self, sq: chess.Square) -> str:
        pieza = self._estado.board.piece_at(sq)
        if pieza is None:
            return f"pieza de {chess.square_name(sq)}"
        return f"{_NOMBRES_PIEZA[pieza.piece_type]} de {chess.square_name(sq)}"

    def _registrar_cambios(self, ocupacion: Ocupacion, reposo: Ocupacion) -> None:
        anterior = reposo if self._anterior is None else self._anterior
        for sq in sorted(anterior - ocupacion):
            self._vaciadas.add(sq)
            log.info("%s: se levanta %s", self._prefijo_log(), self._describir_casilla(sq))
        for sq in sorted(ocupacion - anterior):
            if sq in self._vaciadas:
                self._contador += 1
                self._reocupadas[sq] = self._contador
            log.info("%s: aparece pieza en %s", self._prefijo_log(), chess.square_name(sq))
        self._anterior = ocupacion

    def procesar_ocupacion(self, ocupacion: Ocupacion) -> Lectura:
        """Interpreta una lectura de sensores contra el tablero lógico actual."""
        self._sincronizar_con_tablero()
        reposo = casillas_ocupadas(self._estado.board)
        self._registrar_cambios(ocupacion, reposo)

        if ocupacion == reposo:
            self._vaciadas.clear()
            self._reocupadas.clear()
            lectura = Lectura(TipoLectura.REPOSO, ocupacion)
        else:
            lectura = self._resolver(ocupacion, reposo)

        if lectura != self._ultima:
            self._loguear(lectura)
        self._ultima = lectura
        return lectura

    def _resolver(self, ocupacion: Ocupacion, reposo: Ocupacion) -> Lectura:
        faltan, sobran = reposo - ocupacion, ocupacion - reposo
        candidatos = tuple(self._por_ocupacion.get(ocupacion, ()))

        def lectura(tipo: TipoLectura, movimiento: chess.Move | None = None) -> Lectura:
            return Lectura(tipo, ocupacion, movimiento, candidatos, faltan, sobran)

        if not candidatos:
            return lectura(TipoLectura.INCOMPLETA)
        if len(candidatos) == 1:
            return lectura(TipoLectura.JUGADA, candidatos[0])

        # Varios candidatos con la misma ocupación: capturas de una misma pieza a casillas
        # distintas. Gana la casilla capturada que se volvió a ocupar más recientemente.
        vistas = [m for m in candidatos if m.to_square in self._reocupadas]
        if not vistas:
            return lectura(TipoLectura.AMBIGUA)
        return lectura(TipoLectura.JUGADA, max(vistas, key=lambda m: self._reocupadas[m.to_square]))

    def _loguear(self, lectura: Lectura) -> None:
        if lectura.tipo is TipoLectura.JUGADA:
            log.info(
                "%s: posición de %s, falta el botón del reloj",
                self._prefijo_log(),
                self._estado.board.san(lectura.movimiento),
            )
        elif lectura.tipo is TipoLectura.AMBIGUA:
            log.warning(
                "%s: captura ambigua entre %s",
                self._prefijo_log(),
                ", ".join(self._estado.board.san(m) for m in lectura.candidatos),
            )


def marcas(lectura: Lectura, board: chess.Board) -> dict[chess.Square, Marca]:
    """Qué mostrar en cada casilla para una lectura (las que no aparecen, apagadas).

    - `JUGADA`: todas las casillas que toca la jugada (con la torre del enroque y el peón
      capturado al paso).
    - `AMBIGUA`: el origen como `JUGADA` y las casillas posibles de la captura como `DESTINO`.
    - `INCOMPLETA`: las jugadas compatibles con lo que se movió hasta ahora (las que tocan
      todas las casillas cambiadas) muestran sus orígenes y destinos. Si no hay ninguna (por
      ejemplo, la pieza se apoyó en una casilla ilegal), se muestran las jugadas de las
      piezas propias levantadas. Lo que quede sin explicar es `FALTA` o `SOBRA`.
    """
    if lectura.tipo is TipoLectura.REPOSO:
        return {}
    if lectura.tipo is TipoLectura.JUGADA:
        todas, _ = casillas_tocadas(board, lectura.movimiento)
        return dict.fromkeys(todas, Marca.JUGADA)

    resultado: dict[chess.Square, Marca] = {}
    if lectura.tipo is TipoLectura.AMBIGUA:
        for movimiento in lectura.candidatos:
            resultado[movimiento.from_square] = Marca.JUGADA
            resultado.setdefault(movimiento.to_square, Marca.DESTINO)
        return resultado

    cambiadas = lectura.faltan | lectura.sobran
    tocadas = [(m, *casillas_tocadas(board, m)) for m in _jugadas_detectables(board)]
    compatibles = [(todas, origenes) for _, todas, origenes in tocadas if cambiadas <= todas]
    if not compatibles:
        compatibles = [
            (todas, origenes) for m, todas, origenes in tocadas if m.from_square in lectura.faltan
        ]
    for todas, origenes in compatibles:
        for sq in origenes:
            resultado[sq] = Marca.ORIGEN
        for sq in todas - origenes:
            resultado.setdefault(sq, Marca.DESTINO)
    for sq in lectura.faltan:
        resultado.setdefault(sq, Marca.FALTA)
    for sq in lectura.sobran:
        resultado.setdefault(sq, Marca.SOBRA)
    return resultado
