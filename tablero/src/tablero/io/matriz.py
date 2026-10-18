"""Barrido de la matriz de casillas: se lo pide al Arduino Nano por el puerto serie (USB).

El Nano (firmware/matriz-nano/) enciende las filas de a una con su NPN, lee las 8 columnas
y contesta; acá solo se abre el puerto, se mandan los comandos y se leen las respuestas.
Armar los comandos y validar las respuestas es lógica pura y vive en logica/matriz.py
(testeada en tests/test_matriz.py). Protocolo en software-docs/firmware-nano.md, cableado en
hardware-docs/matriz-hall-nano.md.

Común a las dos versiones de sensor, porque el Nano barre igual cualquier sensor que baje
su columna cuando la fila está encendida:
- Hall (la actual): io/sensores.py.
- Reed (la anterior): io/sensores_reed.py.

Cada versión pone su propia espera por fila, su antirrebote y su mapeo celda → casilla;
acá solo está el diálogo con el Nano y la vista en vivo que usan las dos. Detalle en
software-docs/sensores.md.
"""

import errno
import glob
import logging
import termios
import time
from collections.abc import Callable

import chess
import serial

from tablero import config
from tablero.logica import matriz as logica_matriz
from tablero.logica.matriz import MatrizCruda

logger = logging.getLogger(__name__)

_BAUDIOS = 115200
# Abrir el puerto resetea el Nano (señal DTR del USB): tarda 1–2 s en mandar el LISTO.
_PLAZO_LISTO = 3.0
# Si el LISTO no llegó (un Nano que no se resetea al abrir el puerto), se le manda `?`.
_PLAZO_PING = 1.0
# Plazo para cualquier respuesta, además de lo que tarda el barrido en sí.
_PLAZO_RESPUESTA = 0.3
_INTENTOS = 3

# Lo que puede tirar el puerto cuando el Nano desaparece (USB desenchufado): pyserial no
# envuelve los errores de tcflush, que llegan como termios.error.
_ERRORES_PUERTO = (serial.SerialException, OSError, termios.error)

# Pin del Nano de cada fila F0..F7 y de cada columna C0..C7 en el cableado normal (en el
# plan B, C0–C2 pasan a A5–A7), para saber dónde medir con el multímetro.
PIN_DE_FILA = ("D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9")
PIN_DE_COLUMNA = ("D10", "D11", "D12", "A0", "A1", "A2", "A3", "A4")

_puerto: serial.Serial | None = None


class ErrorNano(RuntimeError):
    """El Nano no está, no se puede abrir su puerto o no contesta el protocolo."""


# -- Puerto ---------------------------------------------------------------------------------


def _elegir_puerto() -> str:
    """`config.NANO_PUERTO`, o el único /dev/ttyUSB* o /dev/ttyACM* que haya."""
    if config.NANO_PUERTO is not None:
        return config.NANO_PUERTO
    candidatos = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise ErrorNano("No aparece el Nano: no hay ningún /dev/ttyUSB* ni /dev/ttyACM*. ¿Está enchufado por USB?")
    raise ErrorNano(
        f"Hay varios puertos serie ({', '.join(candidatos)}): poner el del Nano en NANO_PUERTO de "
        "config.py (`ls -l /dev/serial/by-id/` dice cuál es cuál)."
    )


def _explicar_apertura(nombre: str, error: serial.SerialException) -> str:
    if error.errno == errno.EACCES:
        return (
            f"Sin permiso para abrir {nombre}: el usuario tiene que estar en el grupo dialout "
            "(`sudo usermod -aG dialout $USER` y volver a entrar por SSH)."
        )
    if error.errno == errno.ENOENT:
        return f"No existe {nombre}: ¿está enchufado el Nano? ¿Está bien NANO_PUERTO en config.py?"
    if error.errno in (errno.EBUSY, errno.EAGAIN):
        return f"{nombre} está ocupado por otro programa (¿el monitor serie de arduino-cli, u otra prueba corriendo?)."
    return f"No se pudo abrir {nombre}: {error}"


def _escribir(comando: str) -> None:
    assert _puerto is not None
    _puerto.write(comando.encode("ascii") + b"\n")


def _leer_linea(plazo: float) -> str:
    """Una línea del Nano, sin el fin de línea; '' si no llegó entera dentro del plazo."""
    assert _puerto is not None
    if _puerto.timeout != plazo:  # cambiarlo reconfigura el puerto (tcsetattr): solo si hace falta
        _puerto.timeout = plazo
    crudo = _puerto.read_until(b"\n")
    if not crudo.endswith(b"\n"):
        return ""
    # Con el reset entra basura por el USB: no tiene que romper la decodificación.
    return crudo.decode("ascii", errors="replace").strip()


def _esperar_listo(plazo: float) -> bool:
    """Descarta líneas hasta el LISTO del Nano. False si no llegó dentro del plazo."""
    fin = time.monotonic() + plazo
    while (resto := fin - time.monotonic()) > 0:
        linea = _leer_linea(resto)
        version = logica_matriz.version_listo(linea)
        if version is None:
            continue  # basura del reset o la línea vacía que manda antes del LISTO
        if linea != logica_matriz.LISTO_NANO:
            raise ErrorNano(
                f"El Nano habla la versión {version} del protocolo y este código la de "
                f"{logica_matriz.LISTO_NANO!r}: subir el firmware de firmware/matriz-nano/ de este repo."
            )
        return True
    return False


def _cerrar() -> None:
    global _puerto
    if _puerto is None:
        return
    try:
        _puerto.close()
    except _ERRORES_PUERTO:
        pass
    _puerto = None


def configurar_matriz() -> None:
    """Abre el puerto del Nano y espera su LISTO (~2 s). Llamar a `liberar_matriz()` al terminar.

    Tira `ErrorNano` con lo que hay que revisar si el Nano no está o no contesta.
    """
    global _puerto
    if _puerto is not None:
        return
    nombre = _elegir_puerto()
    try:
        # exclusive: otra prueba con el puerto abierto falla acá, en vez de robarle respuestas.
        _puerto = serial.Serial(nombre, _BAUDIOS, timeout=_PLAZO_RESPUESTA, exclusive=True)
    except serial.SerialException as error:
        raise ErrorNano(_explicar_apertura(nombre, error)) from error
    try:
        if not _esperar_listo(_PLAZO_LISTO):
            _escribir("?")
            if not _esperar_listo(_PLAZO_PING):
                raise ErrorNano(
                    f"El Nano en {nombre} no contesta. ¿Tiene cargado el firmware de firmware/matriz-nano/? "
                    f"Probarlo a mano con `arduino-cli monitor -p {nombre} -c baudrate=115200`."
                )
    except _ERRORES_PUERTO as error:
        _cerrar()
        raise ErrorNano(f"Se cortó la comunicación con el Nano en {nombre}: {error}") from error
    except BaseException:
        _cerrar()
        raise
    logger.info("Nano listo en %s", nombre)


def liberar_matriz() -> None:
    """Apaga las filas y cierra el puerto. No falla si el Nano ya no está (USB desenchufado)."""
    if _puerto is None:
        return
    try:
        _escribir("X")
        _puerto.flush()
    except _ERRORES_PUERTO:
        pass
    finally:
        _cerrar()


def _pedir[T](comando: str, decodificar: Callable[[str], T], plazo: float = _PLAZO_RESPUESTA) -> T:
    """Manda `comando` y decodifica la respuesta; reintenta si no llega o llega mal formada.

    `decodificar` tira `ValueError` si la línea no es la respuesta esperada (incluye `ERR …`).
    """
    if _puerto is None:
        raise ErrorNano("La matriz no está configurada: falta llamar a configurar_matriz().")
    respuesta = ""
    try:
        for _ in range(_INTENTOS):
            _puerto.reset_input_buffer()  # lo que haya quedado de un intento anterior
            _escribir(comando)
            respuesta = _leer_linea(plazo)
            try:
                return decodificar(respuesta)
            except ValueError:
                logger.warning("Respuesta inválida del Nano a %r: %r. Se reintenta.", comando, respuesta)
    except _ERRORES_PUERTO as error:
        raise ErrorNano(f"Se cortó la comunicación con el Nano ({error}). ¿Se desenchufó el USB?") from error
    raise ErrorNano(
        f"El Nano no contestó bien a {comando!r} en {_INTENTOS} intentos (última respuesta: {respuesta!r})."
    )


def _confirmacion(esperada: str) -> Callable[[str], None]:
    def confirmar(linea: str) -> None:
        if linea != esperada:
            raise ValueError(f"Se esperaba {esperada!r} y llegó {linea!r}")

    return confirmar


# -- Comandos ---------------------------------------------------------------------------------


def elegir_fila(fila: int) -> None:
    """Deja encendida fija la fila Fk (`F k`) y apaga las demás, hasta el próximo barrido o `X`."""
    if not 0 <= fila <= 7:
        raise ValueError(f"Las filas van de F0 a F7, no F{fila}")
    _pedir(f"F {fila}", _confirmacion(f"OK F{fila}"))


def apagar_filas() -> None:
    """Apaga todas las filas (`X`)."""
    _pedir("X", _confirmacion("OK X"))


def leer_columnas() -> tuple[bool, ...]:
    """Lee las 8 columnas C0..C7 sin tocar las filas (`C`): con `elegir_fila(k)`, las casillas de Fk."""
    return _pedir("C", logica_matriz.decodificar_columnas)


def leer_analogico() -> tuple[int | None, ...]:
    """Lectura del ADC de cada columna C0..C7 (`A`), 0 = 0 V y 1023 ≈ 5 V; `None` si no es analógica."""
    return _pedir("A", logica_matriz.decodificar_analogico)


def leer_matriz(espera: float) -> MatrizCruda:
    """Un barrido completo (`L <µs>`): la matriz cruda, sin antirrebote ni mapeo a casillas.

    `espera` son los segundos que el Nano espera en cada fila después de encenderla y antes
    de leer las columnas: lo que tardan los Hall en arrancar (máximo 50 ms).
    """
    comando = logica_matriz.comando_barrido(espera)
    return _pedir(comando, logica_matriz.decodificar_barrido, 8 * espera + _PLAZO_RESPUESTA)


# -- Antirrebote y vista en vivo --------------------------------------------------------------


class LectorMatriz:
    """Lectura con antirrebote: solo reporta una matriz que se repitió N veces seguidas.

    Cada versión de sensor tiene su subclase con su espera y su N por defecto
    (`sensores.LectorMatriz`, `sensores_reed.LectorMatriz`).
    """

    def __init__(self, espera: float, lecturas_estables: int) -> None:
        self.espera = espera
        self._lecturas_estables = lecturas_estables
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida lo leído: la próxima matriz estable se devuelve aunque no haya cambiado."""
        self._candidata: MatrizCruda | None = None
        self._repeticiones = 0
        self.estable: MatrizCruda | None = None

    def leer(self) -> MatrizCruda | None:
        """Hace una lectura; devuelve la nueva matriz estable si cambió, si no `None`."""
        lectura = leer_matriz(self.espera)
        if lectura == self._candidata:
            self._repeticiones += 1
        else:
            self._candidata, self._repeticiones = lectura, 1
        if self._repeticiones >= self._lecturas_estables and lectura != self.estable:
            self.estable = lectura
            return lectura
        return None

    def esperar_estable(self) -> MatrizCruda:
        """Olvida lo leído y espera la próxima matriz estable, aunque sea igual a la anterior."""
        self.reiniciar()
        while (matriz := self.leer()) is None:
            time.sleep(0.01)
        return matriz


def formatear_matriz(matriz: MatrizCruda) -> str:
    lineas = ["      " + " ".join(f"C{c}" for c in range(8))]
    for fila, columnas in enumerate(matriz):
        lineas.append(f"  F{fila}   " + "  ".join("#" if ocupada else "." for ocupada in columnas))
    return "\n".join(lineas)


def formatear_tablero(casillas: frozenset[chess.Square]) -> str:
    lineas = []
    for fila in range(7, -1, -1):
        celdas = "  ".join("#" if chess.square(col, fila) in casillas else "." for col in range(8))
        lineas.append(f"  {fila + 1}   {celdas}")
    lineas.append("      " + "  ".join("abcdefgh"))
    return "\n".join(lineas)


def mostrar_en_vivo(
    lector: LectorMatriz,
    a_casillas: Callable[[MatrizCruda], frozenset[chess.Square]],
    leyenda: str,
) -> None:
    """Muestra en vivo la matriz cruda y el tablero mapeado; loguea cada cambio. Ctrl+C sale.

    `a_casillas` es el mapeo de la versión de sensor (`ocupacion()` de cada módulo) y
    `leyenda`, qué significa un `#` en la matriz cruda.
    """
    configurar_matriz()
    anteriores: frozenset[chess.Square] = frozenset()
    logger.info("Leyendo la matriz (Ctrl+C para salir)...")
    try:
        while True:
            matriz = lector.leer()
            if matriz is not None:
                actuales = a_casillas(matriz)
                print("\033[2J\033[H", end="")  # limpia la terminal
                print(f"Matriz cruda (# = {leyenda}):")
                print(formatear_matriz(matriz))
                print(f"\nTablero mapeado ({len(actuales)} piezas):")
                print(formatear_tablero(actuales))
                print()
                for sq in sorted(actuales - anteriores):
                    logger.info("aparece pieza en %s", chess.square_name(sq))
                for sq in sorted(anteriores - actuales):
                    logger.info("se levanta pieza de %s", chess.square_name(sq))
                anteriores = actuales
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        liberar_matriz()
        logger.info("Puerto del Nano cerrado, saliendo.")
