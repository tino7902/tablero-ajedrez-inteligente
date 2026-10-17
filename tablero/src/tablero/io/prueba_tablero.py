"""Prueba del tablero completo: los sensores Hall (io/sensores.py) y los LEDs (io/leds.py) juntos.

Necesita el mapeo de los Hall hecho (`CASILLA_DE_CELDA_HALL`, de `sensores mapear`); salvo
`leds`, que lo genera, también el de los LEDs (`LED_DE_CASILLA`). Usa los LEDs, así que
necesita root: igual que io/leds.py, si no se corre como root se relanza solo con `sudo`.

Pruebas manuales en la Raspberry (desde tablero/, ver software-docs/prueba-tablero.md):

    uv run python -m tablero.io.prueba_tablero leds        # asocia cada LED a su casilla con una pieza
    uv run python -m tablero.io.prueba_tablero recorrido   # verificación guiada de a1 a h8
    uv run python -m tablero.io.prueba_tablero espejo      # los LEDs muestran las casillas ocupadas
    uv run python -m tablero.io.prueba_tablero inicial     # compara con la posición inicial
"""

import argparse
import logging
import os
import select
import sys
import time

import chess

from tablero import config
from tablero.io import leds, sensores

logger = logging.getLogger(__name__)

_POSICION_INICIAL = frozenset(chess.SquareSet(chess.BB_RANK_1 | chess.BB_RANK_2 | chess.BB_RANK_7 | chess.BB_RANK_8))
_IDENTIDAD_HALL = tuple(
    tuple(chess.square_name(chess.square(entrada, salida)) for entrada in range(8)) for salida in range(8)
)


def _nombres(casillas: frozenset[chess.Square]) -> str:
    return ", ".join(chess.square_name(c) for c in sorted(casillas))


def _pintar(tira: leds.TiraLeds, colores: dict[chess.Square, int]) -> None:
    tira.limpiar()
    for casilla, color in colores.items():
        tira.encender(casilla, color)
    tira.mostrar()


def _se_apreto_enter() -> bool:
    """True si hay una línea tipeada esperando, sin bloquear (la terminal la entrega con el Enter)."""
    if not select.select([sys.stdin], [], [], 0)[0]:
        return False
    sys.stdin.readline()
    return True


def _avisar_si_falta_mapear() -> None:
    if config.CASILLA_DE_CELDA_HALL == _IDENTIDAD_HALL:
        print(
            "AVISO: CASILLA_DE_CELDA_HALL es la identidad, el valor por defecto. Si todavía no corriste "
            "`uv run python -m tablero.io.sensores mapear`, hacelo antes.\n"
        )


def asociar_leds(tira: leds.TiraLeds) -> None:
    """Genera LED_DE_CASILLA con los Hall: prende cada LED y lee en qué casilla se puso la pieza.

    Lo mismo que `leds calibrar`, pero sin tipear casillas: la casilla la dicen los Hall.
    """
    _avisar_si_falta_mapear()
    lector = sensores.LectorMatriz()
    indices = [i for i in range(config.LED_CANTIDAD) if i != config.LED_INDICE_SACRIFICIO]
    asignadas: dict[chess.Square, int] = {}
    historial: list[chess.Square | None] = []
    print("Asociación de LEDs: dejá una sola pieza en el tablero. Se prende un LED por vez.\n")
    posicion = 0
    while posicion < len(indices):
        indice = indices[posicion]
        tira.limpiar()
        tira.encender_indice(indice, leds.BLANCO)
        tira.mostrar()
        respuesta = input(
            f"[{posicion + 1}/{len(indices)}] LED {indice}: poné la pieza en la casilla iluminada y Enter "
            "('-' si no ilumina ninguna casilla, 'r' repite el anterior)... "
        ).strip().lower()
        if respuesta == "r":
            if posicion == 0:
                print("  No hay LED anterior.")
                continue
            posicion -= 1
            anterior = historial.pop()
            if anterior is not None:
                del asignadas[anterior]
            continue
        if respuesta == "-":
            historial.append(None)
            posicion += 1
            continue
        casillas = sensores.ocupacion(lector.esperar_estable())
        if len(casillas) != 1:
            print(f"  Se detectaron {len(casillas)} piezas ({_nombres(casillas) or 'ninguna'}), tiene que ser 1. Se repite.")
            continue
        (casilla,) = casillas
        nombre = chess.square_name(casilla)
        if casilla in asignadas:
            print(f"  {nombre} ya es del LED {asignadas[casilla]}: ¿la pieza sigue ahí? Si te equivocaste antes, 'r'. Se repite.")
            continue
        asignadas[casilla] = indice
        historial.append(casilla)
        print(f"  LED {indice} → {nombre}")
        posicion += 1

    faltantes = [chess.square_name(c) for c in chess.SQUARES if c not in asignadas]
    if faltantes:
        print(f"\nFaltan casillas sin LED: {', '.join(faltantes)}. Revisar la tira y repetir.")
        return
    print("\nCopiar en tablero/src/tablero/config.py (reemplazando el LED_DE_CASILLA actual):\n")
    print(leds.formatear_led_de_casilla(tuple(asignadas[c] for c in chess.SQUARES)))


def recorrido(tira: leds.TiraLeds) -> None:
    """Verificación guiada de a1 a h8: prende la casilla en azul y espera la pieza ahí.

    Prueba todo junto: que cada Hall detecte, que el mapeo de los Hall y el de los LEDs
    coincidan con el tablero real. Si la pieza aparece en otra casilla, esa se prende en
    rojo y queda anotada; Enter saltea la casilla (por ejemplo, si no se detecta nunca).
    """
    _avisar_si_falta_mapear()
    lector = sensores.LectorMatriz()
    fallas: dict[chess.Square, set[chess.Square]] = {}
    salteadas: list[chess.Square] = []
    print(
        "Recorrido: dejá una sola pieza en el tablero y llevala a la casilla que se prende en azul.\n"
        "Enter saltea la casilla (queda anotada). Ctrl+C corta.\n"
    )
    anterior: chess.Square | None = None
    for casilla in chess.SQUARES:
        nombre = chess.square_name(casilla)
        print(f"→ {nombre}")
        _pintar(tira, {casilla: leds.AZUL})
        lector.reiniciar()
        while True:
            if _se_apreto_enter():
                salteadas.append(casilla)
                print(f"  {nombre} salteada")
                break
            lectura = lector.leer()
            if lectura is None:
                time.sleep(0.01)
                continue
            casillas = sensores.ocupacion(lectura)
            if casillas == {casilla}:
                print("  bien")
                _pintar(tira, {casilla: leds.VERDE})
                time.sleep(0.3)
                break
            if not casillas or casillas == {anterior}:
                # Pieza levantada, o todavía en la casilla anterior: nada que reportar.
                _pintar(tira, {casilla: leds.AZUL})
            elif len(casillas) == 1:
                fallas.setdefault(casilla, set()).update(casillas)
                print(f"  FALLA: la pieza se detecta en {_nombres(casillas)}, se esperaba {nombre}")
                _pintar(tira, {casilla: leds.AZUL, **dict.fromkeys(casillas, leds.ROJO)})
            else:
                print(f"  Se detectan {len(casillas)} piezas ({_nombres(casillas)}): dejá una sola.")
                _pintar(tira, {**dict.fromkeys(casillas, leds.AMARILLO), casilla: leds.AZUL})
        anterior = casilla

    print()
    if not fallas and not salteadas:
        print("OK: las 64 casillas se detectaron donde se prendieron.")
        return
    for casilla, otras in fallas.items():
        print(f"FALLA en {chess.square_name(casilla)}: la pieza se detectó en {_nombres(frozenset(otras))}")
    if salteadas:
        print(f"Salteadas: {_nombres(frozenset(salteadas))}")


def espejo(tira: leds.TiraLeds) -> None:
    """Los LEDs muestran en vivo las casillas ocupadas, en verde; loguea cada cambio. Ctrl+C sale."""
    lector = sensores.LectorMatriz()
    anteriores: frozenset[chess.Square] = frozenset()
    logger.info("Espejo: cada casilla con pieza se prende en verde (Ctrl+C para salir)...")
    while True:
        lectura = lector.leer()
        if lectura is not None:
            actuales = sensores.ocupacion(lectura)
            _pintar(tira, dict.fromkeys(actuales, leds.VERDE))
            for sq in sorted(actuales - anteriores):
                logger.info("aparece pieza en %s", chess.square_name(sq))
            for sq in sorted(anteriores - actuales):
                logger.info("se levanta pieza de %s", chess.square_name(sq))
            anteriores = actuales
        time.sleep(0.01)


def inicial(tira: leds.TiraLeds) -> None:
    """Compara en vivo con la posición inicial: verde bien, rojo falta pieza, amarillo sobra. Ctrl+C sale."""
    lector = sensores.LectorMatriz()
    logger.info(
        "Armá la posición inicial: verde = pieza bien puesta, rojo = falta, amarillo = sobra (Ctrl+C para salir)..."
    )
    while True:
        lectura = lector.leer()
        if lectura is not None:
            actuales = sensores.ocupacion(lectura)
            faltan = _POSICION_INICIAL - actuales
            sobran = actuales - _POSICION_INICIAL
            _pintar(
                tira,
                {
                    **dict.fromkeys(_POSICION_INICIAL & actuales, leds.VERDE),
                    **dict.fromkeys(faltan, leds.ROJO),
                    **dict.fromkeys(sobran, leds.AMARILLO),
                },
            )
            if not faltan and not sobran:
                logger.info("Posición inicial completa (32 piezas).")
            else:
                logger.info(
                    "%d piezas. Faltan %d (%s); sobran %d (%s)",
                    len(actuales),
                    len(faltan),
                    _nombres(faltan) or "-",
                    len(sobran),
                    _nombres(sobran) or "-",
                )
        time.sleep(0.01)


if __name__ == "__main__":
    if os.geteuid() != 0:
        # rpi-ws281x necesita root (/dev/mem), ver io/leds.py: mismo relanzamiento.
        os.execvp("sudo", ["sudo", sys.executable, "-m", "tablero.io.prueba_tablero", *sys.argv[1:]])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Prueba del tablero completo: sensores Hall y LEDs juntos.")
    parser.add_argument(
        "prueba",
        choices=["leds", "recorrido", "espejo", "inicial"],
        help=(
            "leds: generar LED_DE_CASILLA con una pieza; recorrido: verificación guiada de a1 a h8; "
            "espejo: los LEDs siguen a las piezas; inicial: comparar con la posición inicial"
        ),
    )
    parser.add_argument("--brillo", type=int, default=config.LED_BRILLO, help="0-255")
    argumentos = parser.parse_args()
    pruebas = {
        "leds": asociar_leds,
        "recorrido": recorrido,
        "espejo": espejo,
        "inicial": inicial,
    }
    tira = leds.TiraLeds(argumentos.brillo)
    sensores.configurar_matriz()
    try:
        pruebas[argumentos.prueba](tira)
    except KeyboardInterrupt:
        pass
    finally:
        tira.apagar()
        sensores.liberar_matriz()
        logger.info("LEDs apagados y GPIO liberado, saliendo.")
