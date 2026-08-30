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

Cada partida queda registrada en `registros/` (PGN + log detallado, ver
`logica/registro.py`), salvo que se pase `--sin-registro`.
"""

from __future__ import annotations

import argparse
import logging

import chess

from tablero import config
from tablero.logica.notacion import NOMBRES_COLOR, Idioma
from tablero.logica.partida import (
    MOTIVO_ABANDONO,
    Partida,
    ResultadoBoton,
    ResultadoJugada,
    TipoBoton,
)
from tablero.logica.registro import RegistroPartida
from tablero.logica.reloj import formatear_tiempo

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
    return (
        f"⏱  blancas {formatear_tiempo(reloj.restante(chess.WHITE))}"
        f"  ·  negras {formatear_tiempo(reloj.restante(chess.BLACK))}"
    )


def _mostrar_jugada(resultado: ResultadoJugada) -> None:
    if resultado.aceptado:
        print(f"✓  ACEPTADO  {resultado.san}  ({resultado.descripcion})")
    else:
        print(f"⛔  BLOQUEADO: {resultado.motivo}")


def _mostrar_boton(resultado: ResultadoBoton) -> None:
    if resultado.paso_turno:
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
    if partida.reloj.tiempo_agotado:
        perdedor = NOMBRES_COLOR[partida.reloj.perdedor]
        print(f"\n⏱  ¡{perdedor.capitalize()} se quedaron sin tiempo! Gana {NOMBRES_COLOR[not partida.reloj.perdedor]}.")
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
        "--sin-registro",
        action="store_true",
        help="no escribe el PGN ni el log de la partida en registros/",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Punto de entrada: pregunta lo que falte, arma la partida y corre el loop."""
    args = _parsear_argumentos(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    print("=== Tablero de ajedrez inteligente — simulación de partida ===")
    idioma = Idioma(args.notacion) if args.notacion else preguntar_idioma()
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


if __name__ == "__main__":
    main()
