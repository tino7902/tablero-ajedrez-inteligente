"""Partida en el tablero físico: matriz Hall + botones del reloj + LEDs, por terminal.

Lo que ve el tablero lo interpreta `logica/partida_fisica.py` (la jugada cuenta al apretar
el botón del reloj); acá solo se leen los sensores, se pintan los LEDs y se imprime qué pasa.
Usa los LEDs, así que necesita root: igual que io/prueba_tablero.py, si no se corre como
root se relanza solo con `sudo` (salvo con `--sin-leds`).

Con `--magnus` se juega contra Stockfish, sin límite de tiempo (`logica/partida_magnus.py`):
el motor piensa en otro hilo, así los LEDs y la matriz no se congelan, y su jugada la hace
el jugador en el tablero y la confirma con cualquier botón.

En la Raspberry, desde tablero/ (ver software-docs/juego.md):

    uv run python -m tablero.io.juego                       # partida de 5 minutos
    uv run python -m tablero.io.juego --minutos 3
    uv run python -m tablero.io.juego --fen "8/4p3/8/8/8/8/4P3/8 w - - 0 1"   # con 2 imanes
    uv run python -m tablero.io.juego --sin-leds --sin-registro
    uv run python -m tablero.io.juego --magnus facil --color negras
"""

import argparse
import logging
import os
import queue
import random
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import chess
import chess.engine

from tablero import config
from tablero.io import matriz, sensores
from tablero.logica.estado_tablero import EstadoTablero
from tablero.logica.eventos import Marca, RastreadorMovimientos, TipoLectura
from tablero.logica.notacion import NOMBRES_COLOR
from tablero.logica.partida import MOTIVO_ABANDONO, TipoBoton
from tablero.logica.partida_fisica import PartidaFisica, ResultadoConfirmacion
from tablero.logica.partida_magnus import (
    Fase,
    PartidaVsMagnus,
    ResultadoPulsacion,
    nombres_pgn,
    validar_posicion_magnus,
)
from tablero.logica.registro import SUBDIR_DETALLE, SUBDIR_PARTIDAS, RegistroPartida
from tablero.logica.reloj import formatear_duracion, formatear_tiempo
from tablero.motor.stockfish import MotorStockfish

logger = logging.getLogger(__name__)

_COLOR_DE_BOTON = {"boton_1": chess.WHITE, "boton_2": chess.BLACK}  # igual que io/menus.py
_COLORES = {"blancas": chess.WHITE, "negras": chess.BLACK}
_PAUSA = 0.01  # entre lecturas de la matriz, como prueba_tablero espejo


class _Leds:
    """Los LEDs de la partida, o nada con `--sin-leds` (así no hace falta root)."""

    def __init__(self, brillo: int | None) -> None:
        self._tira = None
        self._pintadas: dict[chess.Square, Marca] | None = None
        if brillo is None:
            return
        from tablero.io import leds  # importa rpi_ws281x: solo si se usan

        self._color_de_marca = {
            Marca.ORIGEN: leds.AZUL,
            Marca.DESTINO: leds.BLANCO_TENUE,
            Marca.JUGADA: leds.VERDE,
            Marca.FALTA: leds.ROJO,
            Marca.SOBRA: leds.AMARILLO,
            Marca.MAGNUS_ORIGEN: leds.VIOLETA,
            Marca.MAGNUS_DESTINO: leds.CIAN,
        }
        self._tira = leds.TiraLeds(brillo)

    def pintar(self, marcas: dict[chess.Square, Marca]) -> None:
        if self._tira is None or marcas == self._pintadas:
            return
        self._pintadas = marcas
        self._tira.limpiar()
        for casilla, marca in marcas.items():
            self._tira.encender(casilla, self._color_de_marca[marca])
        self._tira.mostrar()

    def apagar(self) -> None:
        if self._tira is not None:
            self._tira.apagar()


def _linea_reloj(partida: PartidaFisica) -> str:
    reloj = partida.partida.reloj
    blancas, negras = reloj.restante(chess.WHITE), reloj.restante(chess.BLACK)
    assert blancas is not None and negras is not None  # jugador contra jugador: siempre con límite
    return f"⏱  blancas {formatear_tiempo(blancas)}  ·  negras {formatear_tiempo(negras)}"


def _botones_pendientes(cola: queue.Queue[str]) -> list[chess.Color]:
    colores = []
    while True:
        try:
            colores.append(_COLOR_DE_BOTON[cola.get_nowait()])
        except queue.Empty:
            return colores


def esperar_posicion(lector: sensores.LectorMatriz, cola: queue.Queue[str], fen: str | None, leds: _Leds) -> None:
    """Espera a que las piezas estén en la posición de arranque y a que se apriete un botón."""
    rastreador = RastreadorMovimientos(EstadoTablero(fen))
    print("Acomodá las piezas: rojo = falta pieza, amarillo = sobra.")
    lista, descripcion = False, None
    while True:
        lectura_matriz = lector.leer()
        if lectura_matriz is not None:
            lectura = rastreador.procesar_ocupacion(sensores.ocupacion(lectura_matriz))
            lista = lectura.tipo is TipoLectura.REPOSO
            leds.pintar(
                dict.fromkeys(lectura.ocupacion, Marca.JUGADA)
                if lista
                else {**dict.fromkeys(lectura.faltan, Marca.FALTA), **dict.fromkeys(lectura.sobran, Marca.SOBRA)}
            )
            nueva = (
                "Posición lista: apretá cualquier botón del reloj para empezar."
                if lista
                else f"Falta pieza en: {_nombres(lectura.faltan)} · sobra en: {_nombres(lectura.sobran)}"
            )
            if nueva != descripcion:
                print(nueva)
                descripcion = nueva
        if _botones_pendientes(cola) and lista:
            return
        time.sleep(_PAUSA)


def _nombres(casillas: frozenset[chess.Square]) -> str:
    return ", ".join(chess.square_name(sq) for sq in sorted(casillas)) or "-"


def _mostrar_confirmacion(partida: PartidaFisica, resultado: ResultadoConfirmacion) -> None:
    color = NOMBRES_COLOR[resultado.boton.color]
    if resultado.jugada is not None and resultado.jugada.aceptado:
        print(f"✓  {color}: {resultado.jugada.san} ({resultado.jugada.descripcion})")
    if (turno_nuevo := resultado.boton.turno_nuevo) is not None:
        print(f"🔔  turno de {NOMBRES_COLOR[turno_nuevo]}   {_linea_reloj(partida)}")
    elif resultado.boton.tipo is TipoBoton.IGNORADO_TERMINADA:
        pass  # el fin de partida se anuncia aparte
    elif resultado.motivo:
        print(f"⛔  botón de {color}: {resultado.motivo}")
    else:
        print(f"·  {resultado.boton.motivo}")


def _anunciar_fin(partida: PartidaFisica) -> None:
    p = partida.partida
    if (perdedor := p.reloj.perdedor) is not None:
        print(f"\n⏱  ¡{NOMBRES_COLOR[perdedor].capitalize()} se quedaron sin tiempo! Ganan {NOMBRES_COLOR[not perdedor]}.")
    elif p.estado.es_jaque_mate():
        print(f"\n♛  ¡Jaque mate! Ganan {NOMBRES_COLOR[not p.estado.turno]}.")
    else:
        print(f"\n🤝  Partida terminada en tablas ({p.motivo_fin}).")
    print(f"Resultado: {p.resultado()}")


def jugar(partida: PartidaFisica, lector: sensores.LectorMatriz, cola: queue.Queue[str], leds: _Leds) -> None:
    """Bucle de la partida: hasta que termine o Ctrl+C."""
    print(f"\n¡Arranca! Juegan {NOMBRES_COLOR[partida.partida.turno]}.   {_linea_reloj(partida)}")
    mostrada = None
    while not partida.terminada:
        lectura_matriz = lector.leer()
        if lectura_matriz is not None:
            partida.procesar_ocupacion(sensores.ocupacion(lectura_matriz))
        for color in _botones_pendientes(cola):
            _mostrar_confirmacion(partida, partida.pulsar_boton(color))
        if partida.actualizar_tiempo():
            break

        # Las marcas recorren las jugadas legales: se recalculan solo si cambió la lectura.
        if partida.lectura != mostrada:
            mostrada = partida.lectura
            leds.pintar(partida.marcas())
            if mostrada.tipo is not TipoLectura.REPOSO:
                print(f"   {NOMBRES_COLOR[partida.partida.turno]}: {partida.describir()}")
        time.sleep(_PAUSA)
    _anunciar_fin(partida)


def _mostrar_pulsacion(resultado: ResultadoPulsacion) -> None:
    jugada = resultado.jugada
    if resultado.confirmado and jugada is not None and resultado.fase is Fase.MOVER_MAGNUS:
        print(f"✓  Magnus: {jugada.san}")
    elif resultado.confirmado and jugada is not None:
        print(f"✓  {jugada.san} ({jugada.descripcion})")
    elif resultado.fase is not Fase.TERMINADA:
        print(f"⛔  {resultado.motivo}")


def _anunciar_fin_magnus(partida: PartidaVsMagnus) -> None:
    p = partida.partida
    # La jugada final de Magnus, si la partida terminó con ella, y el mensaje final.
    print(f"\n{partida.texto_estado()}")
    if p.estado.es_jaque_mate():
        print(f"♛  ¡Jaque mate! Ganan {NOMBRES_COLOR[not p.estado.turno]}.")
    else:
        print(f"🤝  Partida terminada en tablas ({p.motivo_fin}).")
    print(f"Resultado: {p.resultado()}")


def _esperar_boton_final(partida: PartidaVsMagnus, lector: sensores.LectorMatriz, cola: queue.Queue[str], leds: _Leds) -> None:
    """La jugada de Magnus terminó la partida: sigue en los LEDs hasta que se apriete un botón."""
    print("Hacé la jugada de Magnus en el tablero para verla; apretá un botón para salir.")
    while not _botones_pendientes(cola):
        lectura_matriz = lector.leer()
        if lectura_matriz is not None:
            partida.procesar_ocupacion(sensores.ocupacion(lectura_matriz))
            leds.pintar(partida.marcas())
        time.sleep(_PAUSA)


def jugar_magnus(
    partida: PartidaVsMagnus,
    motor: MotorStockfish,
    lector: sensores.LectorMatriz,
    cola: queue.Queue[str],
    leds: _Leds,
) -> None:
    """Bucle de la partida contra Magnus: hasta que termine, Magnus falle o Ctrl+C.

    El motor piensa en un hilo aparte y el bucle solo mira si ya contestó, así nunca se
    bloquea. Al salir (también con Ctrl+C), el `with` espera la jugada en curso, que dura
    como mucho el tiempo del nivel, y recién después `main` cierra el motor.
    """
    print(
        f"\n¡Arranca! Jugás con {NOMBRES_COLOR[partida.color_humano]} contra Magnus.   "
        f"⏱  {formatear_duracion(partida.duracion)}"
    )
    texto = mostrada = None
    turno = partida.partida.turno
    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        pedido: Future[chess.Move] | None = None
        while True:  # sale con `break` al terminar la partida
            lectura_matriz = lector.leer()
            if lectura_matriz is not None:
                partida.procesar_ocupacion(sensores.ocupacion(lectura_matriz))
            for _ in _botones_pendientes(cola):  # cualquiera de los dos botones
                _mostrar_pulsacion(partida.pulsar_boton())

            if partida.fase is Fase.MAGNUS_PENSANDO and pedido is None:
                pedido = ejecutor.submit(motor.mejor_movimiento, partida.board_para_motor())
            if pedido is not None and pedido.done():
                try:
                    movimiento = pedido.result()
                except (chess.engine.EngineError, TimeoutError) as error:
                    print(f"\nMagnus dejó de responder: {error}", file=sys.stderr)
                    return
                pedido = None
                partida.recibir_jugada_motor(movimiento)
            partida.actualizar_tiempo()

            fase = partida.fase
            if fase is Fase.TERMINADA:
                break
            if partida.partida.turno != turno:
                turno = partida.partida.turno
                print(f"⏱  {formatear_duracion(partida.duracion)}")
            # Las marcas recorren las jugadas legales y el texto depende de la fase: se
            # recalculan solo si cambió algo.
            if (partida.lectura, fase) != mostrada:
                mostrada = (partida.lectura, fase)
                leds.pintar(partida.marcas())
                if partida.texto_estado() != texto:
                    texto = partida.texto_estado()
                    print(texto)
                if fase is Fase.TURNO_HUMANO and partida.lectura.tipo is not TipoLectura.REPOSO:
                    print(f"   {partida.describir()}")
            time.sleep(_PAUSA)

    _anunciar_fin_magnus(partida)
    leds.pintar(partida.marcas())
    if partida.marcas():
        _esperar_boton_final(partida, lector, cola, leds)


def _devolver_al_usuario(registro: RegistroPartida) -> None:
    """Con `sudo`, los registros quedan de root: se los devuelve a quien lo corrió.

    Si no, la simulación (que corre sin root) después no puede escribir ni rotar en
    `registros/`.
    """
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if os.geteuid() != 0 or uid is None or gid is None:
        return
    raiz = Path(config.DIRECTORIO_REGISTROS)
    for ruta in (raiz, raiz / SUBDIR_PARTIDAS, raiz / SUBDIR_DETALLE, registro.ruta_pgn, registro.ruta_log):
        try:
            os.chown(ruta, int(uid), int(gid))
        except OSError as error:
            logger.warning("No se pudo devolver %s a su dueño: %s", ruta, error)


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="juego", description="Partida en el tablero físico (sensores Hall, reloj y LEDs)."
    )
    parser.add_argument("--minutos", type=float, help="minutos por jugador (5 por defecto)")
    parser.add_argument("--fen", help="posición de arranque en FEN (por defecto, la inicial)")
    parser.add_argument(
        "--magnus",
        choices=list(config.NIVELES_MAGNUS),
        help="jugar contra Magnus (Stockfish) en ese nivel, sin límite de tiempo",
    )
    parser.add_argument(
        "--color", choices=[*_COLORES, "aleatorio"], help="tu color contra Magnus (blancas por defecto)"
    )
    parser.add_argument("--brillo", type=int, default=config.LED_BRILLO, help=f"0-{config.LED_BRILLO_MAX}")
    parser.add_argument("--sin-leds", action="store_true", help="no usa los LEDs (y no necesita sudo)")
    parser.add_argument("--sin-registro", action="store_true", help="no escribe el PGN ni el log en registros/")
    parser.add_argument("-v", "--detalle", action="store_true", help="loguea cada pieza que se levanta o apoya")
    args = parser.parse_args(argv)
    if args.magnus and args.minutos is not None:
        parser.error("--minutos no se puede usar con --magnus: contra Magnus no hay límite de tiempo")
    if args.color and not args.magnus:
        parser.error("--color solo sirve con --magnus")
    if args.minutos is None:
        args.minutos = 5
    return args


def main() -> None:
    args = _parsear_argumentos()
    if not args.sin_leds and os.geteuid() != 0:
        # rpi-ws281x necesita root (/dev/mem), ver io/leds.py: mismo relanzamiento.
        os.execvp("sudo", ["sudo", sys.executable, "-m", "tablero.io.juego", *sys.argv[1:]])
    logging.basicConfig(
        level=logging.INFO if args.detalle else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.fen:
        try:
            estado = EstadoTablero(args.fen)
        except ValueError as error:
            sys.exit(f"FEN inválido: {error}")
        if args.magnus:
            try:
                validar_posicion_magnus(estado.board)
            except ValueError as error:
                sys.exit(f"FEN inválido para jugar contra Magnus: {error}")

    motor = color_humano = nombre_color = nivel = None
    if args.magnus:
        # Antes de esperar la posición: si falta el binario, que falle al arrancar.
        try:
            motor = MotorStockfish(nivel=args.magnus)
        except FileNotFoundError:
            sys.exit(f"No se encontró Stockfish ({config.STOCKFISH_PATH}): instalalo con 'sudo apt install stockfish'.")
        nombre_color = args.color or "blancas"
        if nombre_color == "aleatorio":
            nombre_color = random.choice(list(_COLORES))
        color_humano = _COLORES[nombre_color]
        nivel = config.NIVELES_MAGNUS[args.magnus]
        print(f"Contra Magnus ({nivel.nombre}), sin límite de tiempo. Jugás con {nombre_color}.")

    cola: queue.Queue[str] = queue.Queue()
    leds = _Leds(None if args.sin_leds else args.brillo)
    partida = registro = None
    botones_configurados = False
    try:
        sensores.configurar_matriz()
        sensores.configurar_botones_reloj(cola.put)  # corre en el hilo de rpi-lgpio
        botones_configurados = True
        lector = sensores.LectorMatriz()
        esperar_posicion(lector, cola, args.fen, leds)

        if args.magnus:
            assert motor is not None and color_humano is not None and nivel is not None
            if not args.sin_registro:
                blancas, negras = nombres_pgn(color_humano, nivel.nombre)
                registro = RegistroPartida(
                    config.DIRECTORIO_REGISTROS,
                    modo="vs_magnus",
                    segundos_por_jugador=None,
                    max_partidas=config.MAX_PARTIDAS_REGISTRADAS,
                    max_detalles=config.MAX_DETALLES_REGISTRADOS,
                    extras_cabecera=f"nivel={args.magnus} color={nombre_color}",
                    blancas=blancas,
                    negras=negras,
                )
            partida = PartidaVsMagnus(color_humano=color_humano, fen=args.fen, registro=registro)
            jugar_magnus(partida, motor, lector, cola, leds)
        else:
            if not args.sin_registro:
                registro = RegistroPartida(
                    config.DIRECTORIO_REGISTROS,
                    modo="tablero",
                    segundos_por_jugador=args.minutos * 60,
                    max_partidas=config.MAX_PARTIDAS_REGISTRADAS,
                    max_detalles=config.MAX_DETALLES_REGISTRADOS,
                )
            partida = PartidaFisica(segundos_por_jugador=args.minutos * 60, fen=args.fen, registro=registro)
            jugar(partida, lector, cola, leds)
    except KeyboardInterrupt:
        print("\nPartida abandonada.")
    except matriz.ErrorNano as error:
        print(f"Error con el Nano: {error}", file=sys.stderr)
    finally:
        if partida is not None:
            partida.finalizar(MOTIVO_ABANDONO)
        if registro is not None:
            _devolver_al_usuario(registro)
            print(f"Registro: {registro.ruta_pgn}\n          {registro.ruta_log}")
        leds.apagar()
        if botones_configurados:
            sensores.liberar_botones_reloj()
        sensores.liberar_matriz()
        if motor is not None:
            try:
                motor.cerrar()
            except (chess.engine.EngineError, TimeoutError) as error:
                logger.warning("No se pudo cerrar Stockfish: %s", error)


if __name__ == "__main__":
    main()
