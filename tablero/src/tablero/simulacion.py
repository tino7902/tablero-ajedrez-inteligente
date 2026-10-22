"""Simulación de partida por terminal, para probar la lógica sin la Raspberry.

Se tipea un movimiento y el tablero contesta cómo reaccionaría el tablero físico:
lo acepta o lo bloquea con el motivo. El reloj de la partida es real (el tiempo corre
mientras pensás y tipeás) y rige la misma regla que el tablero de verdad —el turno pasa
solo si el jugador correcto hizo un movimiento legal **y** después presionó su botón—,
porque toda la lógica es la de `logica/partida.py`, la misma que va a usar el tablero
cuando `io/sensores.py` reporte los movimientos.

Vive en la raíz del paquete y no en `io/` a propósito: `io/` es el código que necesita
hardware (GPIO, DRM, touch) y no corre en una notebook, que es justamente donde tiene que
poder correr esto. Acá solo hay entrada/salida de terminal; la lógica está en `logica/`.

    uv run python -m tablero.simulacion          # pregunta notación y minutos
    uv run simulacion --notacion es --minutos 3  # sin preguntas
    uv run simulacion --magnus facil --color negras   # contra Magnus (necesita stockfish)

Contra Magnus (`--magnus`) no hay límite de tiempo: tipeás tu jugada, apretás Enter y
Magnus contesta solo (su jugada se aplica y se confirma directamente, porque no hay
tablero que actualizar). Sirve para afinar `config.NIVELES_MAGNUS` sin armar el tablero.

Cada partida queda registrada en `registros/` (PGN + log detallado, ver
`logica/registro.py`), salvo que se pase `--sin-registro`.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from typing import Protocol

import chess

from tablero import config
from tablero.logica.notacion import NOMBRES_COLOR, Idioma
from tablero.logica.partida import (
    MOTIVO_ABANDONO,
    MOTIVO_RENDICION,
    Partida,
    ResultadoBoton,
    ResultadoJugada,
    TipoBoton,
)
from tablero.logica.partida_magnus import (
    describir_jugada_magnus,
    mensaje_final_magnus,
    nombres_pgn,
    validar_posicion_magnus,
)
from tablero.logica.registro import RegistroPartida
from tablero.logica.reloj import formatear_duracion, formatear_tiempo

log = logging.getLogger(__name__)

DURACIONES_SUGERIDAS = (3, 5, 10)  # minutos, las mismas del selector de io/menus.py

_AYUDA = """
Comandos:
  <movimiento>   e4, Cf3/Nf3, e8=D, O-O, o UCI (e2e4, e7e8d)
  <Enter>        presiona el botón del reloj del jugador que tiene el turno
  b1 / b2        presiona el botón de blancas / de negras (para probar el equivocado)
  esperar N      hace correr N segundos de reloj sin esperarlos de verdad
  tablero        muestra la posición actual
  reloj          muestra el tiempo de cada jugador
  fen            muestra la posición en notación FEN
  ayuda          muestra esta ayuda
  salir          termina la partida (queda registrada como abandonada)
""".strip()

_AYUDA_MAGNUS = """
Contra Magnus: tipeá tu jugada y apretá Enter (tu botón del reloj); Magnus contesta solo.
  rendirse       abandona la partida (gana Magnus)
""".strip()

COLORES = {"blancas": chess.WHITE, "negras": chess.BLACK}


class Motor(Protocol):
    """Lo que la simulación necesita del motor (`motor.stockfish.MotorStockfish`)."""

    def mejor_movimiento(self, tablero: chess.Board) -> chess.Move: ...


def _preguntar_opcion(pregunta: str, opciones: list[str], por_defecto: int = 1) -> int:
    """Pregunta hasta obtener un número de opción válido; devuelve el índice (base 0)."""
    print(f"\n{pregunta}")
    for i, opcion in enumerate(opciones, start=1):
        print(f"  {i}) {opcion}")
    while True:
        respuesta = input(f"Opción [{por_defecto}]: ").strip()
        if not respuesta:
            return por_defecto - 1
        if respuesta.isdigit() and 1 <= int(respuesta) <= len(opciones):
            return int(respuesta) - 1
        print(f"Elegí un número entre 1 y {len(opciones)}.")


def preguntar_idioma() -> Idioma:
    """Pregunta en qué notación se van a tipear los movimientos."""
    idiomas = [Idioma.ESPANOL, Idioma.INGLES]
    indice = _preguntar_opcion(
        "¿En qué notación vas a escribir los movimientos?",
        [idioma.descripcion for idioma in idiomas],
    )
    return idiomas[indice]


def preguntar_minutos() -> float:
    """Pregunta cuánto tiempo tiene cada jugador."""
    opciones = [f"{m} minutos" for m in DURACIONES_SUGERIDAS] + ["Otro (lo escribo yo)"]
    indice = _preguntar_opcion("¿Cuánto tiempo tiene cada jugador?", opciones, por_defecto=2)
    if indice < len(DURACIONES_SUGERIDAS):
        return float(DURACIONES_SUGERIDAS[indice])
    while True:
        respuesta = input("Minutos por jugador: ").strip().replace(",", ".")
        try:
            minutos = float(respuesta)
        except ValueError:
            minutos = 0
        if minutos > 0:
            return minutos
        print("Escribí un número de minutos mayor a cero.")


def _linea_reloj(partida: Partida) -> str:
    reloj = partida.reloj
    blancas, negras = reloj.restante(chess.WHITE), reloj.restante(chess.BLACK)
    if blancas is None or negras is None:  # sin límite de tiempo
        return f"⏱  {formatear_duracion(reloj.duracion)}"
    return f"⏱  blancas {formatear_tiempo(blancas)}  ·  negras {formatear_tiempo(negras)}"


def _mostrar_jugada(resultado: ResultadoJugada) -> None:
    if resultado.aceptado:
        print(f"✓  ACEPTADO  {resultado.san}  ({resultado.descripcion})")
    else:
        print(f"⛔  BLOQUEADO: {resultado.motivo}")


def _mostrar_boton(resultado: ResultadoBoton) -> None:
    if resultado.turno_nuevo is not None:
        print(
            f"🔔  botón {NOMBRES_COLOR[resultado.color]} → turno de "
            f"{NOMBRES_COLOR[resultado.turno_nuevo]}"
        )
    elif resultado.tipo is TipoBoton.IGNORADO_COLOR:
        print(f"·  {resultado.motivo}")
    else:
        print(f"⛔  botón ignorado: {resultado.motivo}")


def _mostrar_tablero(partida: Partida) -> None:
    print()
    print(partida.estado.board.unicode(invert_color=True, empty_square="·", borders=True))
    print()


def _mostrar_pendiente(partida: Partida) -> None:
    pendiente = partida.esperando_boton
    if pendiente is not None:
        print(f"⏳  {NOMBRES_COLOR[pendiente]} tienen que presionar su botón del reloj")


def _anunciar_fin(partida: Partida) -> None:
    motivo = partida.motivo_fin
    resultado = partida.resultado()
    if (color_perdedor := partida.reloj.perdedor) is not None:
        perdedor = NOMBRES_COLOR[color_perdedor]
        print(f"\n⏱  ¡{perdedor.capitalize()} se quedaron sin tiempo! Gana {NOMBRES_COLOR[not color_perdedor]}.")
    elif partida.estado.es_jaque_mate():
        ganador = NOMBRES_COLOR[not partida.estado.turno]
        print(f"\n♛  ¡Jaque mate! Ganan {ganador}.")
    else:
        print(f"\n🤝  Partida terminada en tablas ({motivo}).")
    print(f"Resultado: {resultado}")


def _procesar_comando(partida: Partida, entrada: str) -> bool:
    """Ejecuta un comando de la simulación; devuelve `False` si hay que salir del loop."""
    comando = entrada.strip()
    minuscula = comando.lower()

    if minuscula in {"salir", "chau", "exit", "quit"}:
        return False
    if minuscula in {"ayuda", "help", "?"}:
        print(_AYUDA)
        return True
    if minuscula == "tablero":
        _mostrar_tablero(partida)
        return True
    if minuscula == "fen":
        print(partida.estado.fen())
        return True
    if minuscula == "reloj":
        return True  # la línea de reloj se imprime siempre al final del comando
    if minuscula.startswith("esperar"):
        _, _, argumento = minuscula.partition(" ")
        try:
            segundos = float(argumento.strip().replace(",", "."))
        except ValueError:
            print("Uso: esperar <segundos>, por ejemplo 'esperar 30'")
            return True
        partida.avanzar_tiempo(segundos)
        return True

    if comando == "":
        _mostrar_boton(partida.pulsar_boton(partida.turno))
        return True
    if minuscula in {"b1", "b2"}:
        color = chess.WHITE if minuscula == "b1" else chess.BLACK
        _mostrar_boton(partida.pulsar_boton(color))
        return True

    _mostrar_jugada(partida.intentar_movimiento(comando))
    return True


def jugar(partida: Partida) -> None:
    """Corre el loop de comandos hasta que la partida termine o el jugador salga."""
    print(_AYUDA)
    _mostrar_tablero(partida)

    while not partida.terminada:
        _mostrar_pendiente(partida)
        print(_linea_reloj(partida))
        try:
            entrada = input(f"{NOMBRES_COLOR[partida.turno]}> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        # El tiempo que pasó tipeando le corre a quien tiene el reloj, como en la mesa.
        if partida.actualizar_tiempo():
            break
        if not _procesar_comando(partida, entrada):
            break
        print()

    partida.actualizar_tiempo()
    if partida.terminada:
        _anunciar_fin(partida)
        partida.finalizar()
    else:
        print("Partida abandonada.")
        partida.finalizar(MOTIVO_ABANDONO)


def _turno_de_magnus(partida: Partida, motor: Motor, color_magnus: chess.Color) -> None:
    """Pide la jugada al motor, la aplica y la confirma (acá no hay piezas que mover)."""
    print("Magnus está pensando…")
    antes = partida.estado.board.copy(stack=False)
    movimiento = motor.mejor_movimiento(partida.estado.board.copy())
    resultado = partida.intentar_jugada(movimiento)
    print(f"🤖  {describir_jugada_magnus(antes, movimiento)}  ({resultado.san})")
    if not partida.terminada:
        partida.pulsar_boton(color_magnus)
    _mostrar_tablero(partida)


def _anunciar_fin_magnus(partida: Partida, color_humano: chess.Color) -> None:
    if partida.motivo_fin == MOTIVO_RENDICION:
        print("\n🏳  Te rendiste.")
    elif partida.estado.es_jaque_mate():
        print(f"\n♛  ¡Jaque mate! Ganan {NOMBRES_COLOR[not partida.estado.turno]}.")
    else:
        print(f"\n🤝  Partida terminada en tablas ({partida.motivo_fin}).")
    print(mensaje_final_magnus(partida.resultado(), color_humano, partida.reloj.duracion))
    print(f"Resultado: {partida.resultado()}")


def jugar_magnus(partida: Partida, motor: Motor, color_humano: chess.Color) -> None:
    """Como `jugar`, pero las jugadas del otro color las hace Magnus."""
    print(_AYUDA)
    print(_AYUDA_MAGNUS)
    _mostrar_tablero(partida)

    while not partida.terminada:
        if partida.turno != color_humano:
            _turno_de_magnus(partida, motor, not color_humano)
            continue
        _mostrar_pendiente(partida)
        print(_linea_reloj(partida))
        try:
            entrada = input(f"{NOMBRES_COLOR[partida.turno]}> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        partida.actualizar_tiempo()
        if entrada.strip().lower() == "rendirse":
            partida.rendirse(color_humano)
            break
        if not _procesar_comando(partida, entrada):
            break
        print()

    if partida.terminada:
        _anunciar_fin_magnus(partida, color_humano)
    else:
        print("Partida abandonada.")
    partida.finalizar(MOTIVO_ABANDONO)


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="simulacion",
        description="Simulación de partida por terminal (sin hardware).",
    )
    parser.add_argument(
        "--notacion",
        choices=[idioma.value for idioma in Idioma],
        help="notación de los movimientos: es (Cf3) o en (Nf3). Si falta, se pregunta.",
    )
    parser.add_argument(
        "--minutos", type=float, help="minutos por jugador. Si falta, se pregunta."
    )
    parser.add_argument("--fen", help="posición inicial en FEN (por defecto, la de una partida nueva)")
    parser.add_argument(
        "--magnus",
        choices=list(config.NIVELES_MAGNUS),
        help="jugar contra Magnus (Stockfish) en ese nivel, sin límite de tiempo",
    )
    parser.add_argument(
        "--color",
        choices=[*COLORES, "aleatorio"],
        default="blancas",
        help="tu color contra Magnus (blancas por defecto)",
    )
    parser.add_argument(
        "--sin-registro",
        action="store_true",
        help="no escribe el PGN ni el log de la partida en registros/",
    )
    args = parser.parse_args(argv)
    if args.magnus and args.minutos:
        parser.error("--minutos no se puede usar con --magnus: contra Magnus no hay límite de tiempo")
    return args


def main(argv: list[str] | None = None) -> None:
    """Punto de entrada: pregunta lo que falte, arma la partida y corre el loop."""
    args = _parsear_argumentos(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    print("=== Tablero de ajedrez inteligente — simulación de partida ===")
    idioma = Idioma(args.notacion) if args.notacion else preguntar_idioma()
    if args.magnus:
        _main_magnus(args, idioma)
        return
    minutos = args.minutos if args.minutos else preguntar_minutos()
    segundos = minutos * 60

    registro = None
    if not args.sin_registro:
        registro = RegistroPartida(
            config.DIRECTORIO_REGISTROS,
            modo="simulacion",
            segundos_por_jugador=segundos,
            max_partidas=config.MAX_PARTIDAS_REGISTRADAS,
            max_detalles=config.MAX_DETALLES_REGISTRADOS,
            extras_cabecera=f"notacion={idioma.value}",
        )

    partida = Partida(
        segundos_por_jugador=segundos, idioma=idioma, fen=args.fen, registro=registro
    )
    print(f"\nPartida de {minutos:g} minutos por jugador, notación {idioma.descripcion.lower()}.")

    try:
        jugar(partida)
    finally:
        # Un Ctrl+C o una excepción no deben dejar el registro a medio escribir.
        partida.finalizar(MOTIVO_ABANDONO)
        if registro is not None:
            print(f"\nRegistro: {registro.ruta_pgn}\n          {registro.ruta_log}")


def _main_magnus(args: argparse.Namespace, idioma: Idioma) -> None:
    """Partida contra Magnus: abre el motor, arma la partida sin límite y corre el loop."""
    # Se importa acá: el modo normal no necesita python-chess.engine ni el binario.
    from tablero.motor.stockfish import MotorStockfish

    if args.fen:
        try:
            validar_posicion_magnus(chess.Board(args.fen))
        except ValueError as error:
            sys.exit(f"FEN inválido para jugar contra Magnus: {error}")
    nivel = config.NIVELES_MAGNUS[args.magnus]
    nombre_color = random.choice(list(COLORES)) if args.color == "aleatorio" else args.color
    color_humano = COLORES[nombre_color]
    try:
        motor = MotorStockfish(nivel=args.magnus)
    except FileNotFoundError:
        sys.exit(f"No se encontró Stockfish ({config.STOCKFISH_PATH}): instalalo con 'sudo apt install stockfish'.")

    registro = None
    if not args.sin_registro:
        blancas, negras = nombres_pgn(color_humano, nivel.nombre)
        registro = RegistroPartida(
            config.DIRECTORIO_REGISTROS,
            modo="simulacion_magnus",
            segundos_por_jugador=None,
            max_partidas=config.MAX_PARTIDAS_REGISTRADAS,
            max_detalles=config.MAX_DETALLES_REGISTRADOS,
            extras_cabecera=f"notacion={idioma.value} nivel={args.magnus} color={nombre_color}",
            blancas=blancas,
            negras=negras,
        )

    partida = Partida(segundos_por_jugador=None, idioma=idioma, fen=args.fen, registro=registro)
    print(f"\nContra Magnus ({nivel.nombre}), sin límite de tiempo. Jugás con {nombre_color}.")
    try:
        with motor:
            jugar_magnus(partida, motor, color_humano)
    finally:
        partida.finalizar(MOTIVO_ABANDONO)
        if registro is not None:
            print(f"\nRegistro: {registro.ruta_pgn}\n          {registro.ruta_log}")


if __name__ == "__main__":
    main()
