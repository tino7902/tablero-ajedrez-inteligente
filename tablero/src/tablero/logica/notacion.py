"""Parseo de movimientos tipeados por el jugador (SAN español/inglés y UCI).

Lo usa la simulación por terminal (`tablero/simulacion.py`, vía `logica/partida.py`)
para traducir lo que se escribe a un `chess.Move`. Es una función pura sobre un
`chess.Board`: no toca hardware ni mantiene estado.

El idioma se elige al arrancar la partida en vez de autodetectarse, porque `R` es
ambigua — rey en español, torre (*rook*) en inglés — y adivinar entre dos lecturas
legales daría movimientos silenciosamente equivocados. UCI (`e2e4`) se acepta en
ambos idiomas; solo cambia la letra de promoción (`e7e8d` vs `e7e8q`).

Distingue dos errores, que la interfaz muestra distinto: `NotacionInvalidaError`
(no se entiende lo que se escribió) y `MovimientoIlegalError` (se entiende, pero la
pieza no está ahí o no puede hacer ese movimiento — el "movimiento bloqueado").
"""

from __future__ import annotations

import enum
import re

import chess

from tablero.logica.estado_tablero import MovimientoIlegalError

__all__ = [
    "Idioma",
    "NotacionInvalidaError",
    "MovimientoIlegalError",
    "parsear_movimiento",
    "NOMBRES_COLOR",
    "NOMBRES_PIEZA",
    "describir_pieza",
    "GENERO_PIEZA",
    "ninguna_pieza",
    "traducir_san",
]

# Nombres en español para los mensajes al jugador y para el log de `logica/registro.py`.
NOMBRES_COLOR = {chess.WHITE: "blancas", chess.BLACK: "negras"}
NOMBRES_PIEZA = {
    chess.PAWN: "peón",
    chess.KNIGHT: "caballo",
    chess.BISHOP: "alfil",
    chess.ROOK: "torre",
    chess.QUEEN: "dama",
    chess.KING: "rey",
}
# Género gramatical de cada pieza, para concordar los mensajes ("ninguna torre",
# "ningún alfil") sin tener que repetir la excepción en cada texto.
GENERO_PIEZA = {
    chess.PAWN: "m",
    chess.KNIGHT: "m",
    chess.BISHOP: "m",
    chess.ROOK: "f",
    chess.QUEEN: "f",
    chess.KING: "m",
}
_ARTICULOS_PIEZA = {
    chess.PAWN: "el",
    chess.KNIGHT: "el",
    chess.BISHOP: "el",
    chess.ROOK: "la",
    chess.QUEEN: "la",
    chess.KING: "el",
}


def describir_pieza(tipo: chess.PieceType, *, con_articulo: bool = True) -> str:
    """Nombre en español del tipo de pieza, con su artículo ("la dama", "el peón")."""
    nombre = NOMBRES_PIEZA[tipo]
    return f"{_ARTICULOS_PIEZA[tipo]} {nombre}" if con_articulo else nombre


def ninguna_pieza(tipo: chess.PieceType) -> str:
    """"ningún alfil" / "ninguna torre", concordando con el género de la pieza."""
    ninguno = "ninguna" if GENERO_PIEZA[tipo] == "f" else "ningún"
    return f"{ninguno} {NOMBRES_PIEZA[tipo]}"


class NotacionInvalidaError(ValueError):
    """El texto ingresado no es un movimiento reconocible en el idioma elegido."""


class Idioma(enum.Enum):
    """Idioma de la notación algebraica que tipea el jugador."""

    ESPANOL = "es"
    INGLES = "en"

    @property
    def descripcion(self) -> str:
        return "Española (Cf3, Ad3, Dh5)" if self is Idioma.ESPANOL else "Inglesa (Nf3, Bd3, Qh5)"


# Letra de pieza en español -> inglés (la que entiende python-chess).
_PIEZAS_ES_A_EN = {"R": "K", "D": "Q", "T": "R", "A": "B", "C": "N"}
# Sufijo de promoción en UCI, por idioma.
_PROMOCION_UCI = {
    Idioma.ESPANOL: {"d": "q", "t": "r", "a": "b", "c": "n"},
    Idioma.INGLES: {"q": "q", "r": "r", "b": "b", "n": "n"},
}

_RE_UCI = re.compile(r"^[a-h][1-8][a-h][1-8][a-z]?$")
_ENROQUES = {"0-0": "O-O", "0-0-0": "O-O-O", "o-o": "O-O", "o-o-o": "O-O-O"}


def traducir_san(texto: str, idioma: Idioma) -> str:
    """Pasa un SAN español a la notación inglesa de python-chess (inglés queda igual).

    Solo se traducen las posiciones donde una mayúscula es realmente una pieza: la
    inicial y la que sigue a un `=` de promoción. Reemplazar en todo el string sería
    incorrecto (`T`→`R` y después `R`→`K` se pisarían entre sí).
    """
    if idioma is Idioma.INGLES or not texto:
        return texto
    if texto[0] in _PIEZAS_ES_A_EN:
        texto = _PIEZAS_ES_A_EN[texto[0]] + texto[1:]
    if "=" in texto:
        cabeza, _, cola = texto.partition("=")
        if cola and cola[0] in _PIEZAS_ES_A_EN:
            texto = f"{cabeza}={_PIEZAS_ES_A_EN[cola[0]]}{cola[1:]}"
    return texto


def _parsear_uci(texto: str, board: chess.Board, idioma: Idioma) -> chess.Move:
    promociones = _PROMOCION_UCI[idioma]
    if len(texto) == 5:
        letra = texto[4].lower()
        if letra not in promociones:
            raise NotacionInvalidaError(
                f"'{texto}': '{texto[4]}' no es una pieza de promoción válida "
                f"({', '.join(sorted(promociones))})"
            )
        texto = texto[:4] + promociones[letra]
    movimiento = chess.Move.from_uci(texto.lower())
    if not board.is_legal(movimiento):
        raise MovimientoIlegalError(texto)
    return movimiento


def parsear_movimiento(texto: str, board: chess.Board, idioma: Idioma) -> chess.Move:
    """Traduce `texto` a un `chess.Move` legal en `board`.

    Acepta UCI (`e2e4`, `e7e8d`) y SAN en el idioma indicado (`Cf3`/`Nf3`, `e8=D`,
    `O-O`, `0-0`). Levanta `NotacionInvalidaError` si no se entiende y
    `MovimientoIlegalError` si se entiende pero no es legal en la posición.
    """
    texto = texto.strip()
    if not texto:
        raise NotacionInvalidaError("no se ingresó ningún movimiento")

    if _RE_UCI.match(texto.lower()):
        return _parsear_uci(texto, board, idioma)

    san = _ENROQUES.get(texto.lower(), texto)
    san = traducir_san(san, idioma)
    try:
        return board.parse_san(san)
    except chess.IllegalMoveError as exc:
        raise MovimientoIlegalError(texto) from exc
    except chess.AmbiguousMoveError as exc:
        raise NotacionInvalidaError(
            f"'{texto}' es ambiguo: más de una pieza puede hacer ese movimiento, "
            "aclarar la columna de origen (ej. Cbd2) o usar UCI (ej. b1d2)"
        ) from exc
    except chess.InvalidMoveError as exc:
        raise NotacionInvalidaError(
            f"'{texto}' no es un movimiento válido en notación "
            f"{'española' if idioma is Idioma.ESPANOL else 'inglesa'}"
        ) from exc
