"""Partida en el tablero físico: matriz Hall + botones del reloj + LEDs, por terminal.

Lo que ve el tablero lo interpreta `logica/partida_fisica.py` (la jugada cuenta al apretar
el botón del reloj); acá solo se leen los sensores, se pintan los LEDs y se imprime qué pasa.
Usa los LEDs, así que necesita root: igual que io/prueba_tablero.py, si no se corre como
root se relanza solo con `sudo` (salvo con `--sin-leds`).

En la Raspberry, desde tablero/ (ver software-docs/juego.md):

    uv run python -m tablero.io.juego                       # partida de 5 minutos
    uv run python -m tablero.io.juego --minutos 3
    uv run python -m tablero.io.juego --fen "8/4p3/8/8/8/8/4P3/8 w - - 0 1"   # con 2 imanes
    uv run python -m tablero.io.juego --sin-leds --sin-registro
"""

import argparse
import logging
import os
import queue
import sys
import time
from pathlib import Path

import chess

from tablero import config
from tablero.io import matriz, sensores
from tablero.logica.estado_tablero import EstadoTablero
from tablero.logica.eventos import Marca, RastreadorMovimientos, TipoLectura
from tablero.logica.notacion import NOMBRES_COLOR
from tablero.logica.partida import MOTIVO_ABANDONO, TipoBoton
from tablero.logica.partida_fisica import PartidaFisica, ResultadoConfirmacion
from tablero.logica.registro import SUBDIR_DETALLE, SUBDIR_PARTIDAS, RegistroPartida
from tablero.logica.reloj import formatear_tiempo

logger = logging.getLogger(__name__)

_COLOR_DE_BOTON = {"boton_1": chess.WHITE, "boton_2": chess.BLACK}  # igual que io/menus.py
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
    return (
        f"⏱  blancas {formatear_tiempo(reloj.restante(chess.WHITE))}"
        f"  ·  negras {formatear_tiempo(reloj.restante(chess.BLACK))}"
    )


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
    if resultado.paso_turno:
        print(f"🔔  turno de {NOMBRES_COLOR[resultado.boton.turno_nuevo]}   {_linea_reloj(partida)}")
    elif resultado.boton.tipo is TipoBoton.IGNORADO_TERMINADA:
        pass  # el fin de partida se anuncia aparte
    elif resultado.motivo:
        print(f"⛔  botón de {color}: {resultado.motivo}")
    else:
        print(f"·  {resultado.boton.motivo}")


def _anunciar_fin(partida: PartidaFisica) -> None:
    p = partida.partida
    if p.reloj.tiempo_agotado:
        perdedor = p.reloj.perdedor
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
    parser.add_argument("--minutos", type=float, default=5, help="minutos por jugador (5 por defecto)")
    parser.add_argument("--fen", help="posición de arranque en FEN (por defecto, la inicial)")
    parser.add_argument("--brillo", type=int, default=config.LED_BRILLO, help="0-255")
    parser.add_argument("--sin-leds", action="store_true", help="no usa los LEDs (y no necesita sudo)")
    parser.add_argument("--sin-registro", action="store_true", help="no escribe el PGN ni el log en registros/")
    parser.add_argument("-v", "--detalle", action="store_true", help="loguea cada pieza que se levanta o apoya")
    return parser.parse_args(argv)


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
            EstadoTablero(args.fen)
        except ValueError as error:
            sys.exit(f"FEN inválido: {error}")

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


if __name__ == "__main__":
    main()
