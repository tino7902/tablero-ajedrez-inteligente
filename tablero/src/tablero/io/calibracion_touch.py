"""Calibración del touch XPT2046 de la RPI LCD V3.

Ver "Precisión táctil" en software-docs/pantalla.md: la coordenada que reporta
el touch no siempre coincide con el punto físico tocado. Como el panel corre
en modo DRM/KMS sin X11 (ver docs/pantalla.md), no hay herramientas de sistema
tipo `xinput_calibrator` disponibles — la calibración se resuelve acá, a nivel
de aplicación, ajustando una transformación afín entre coordenadas crudas del
touch y coordenadas reales de pantalla.

Uso (por SSH, en la Raspberry, con el overlay activado):

    cd tablero && uv run python -m tablero.io.calibracion_touch

Se muestran 5 cruces (4 esquinas + centro); tocar cada una en orden. Al final
se guarda `config.CALIBRACION_TOUCH_PATH`, que `pantalla.py` lee para corregir
cualquier evento de touch futuro.
"""

import json
import logging
from pathlib import Path

from tablero.io._sdl import configurar_entorno_sdl

configurar_entorno_sdl()

import pygame

from tablero import config

logger = logging.getLogger(__name__)

_NEGRO = (0, 0, 0)
_BLANCO = (255, 255, 255)
_VERDE = (60, 180, 75)

_MARGEN = 40
PUNTOS_CALIBRACION: list[tuple[float, float]] = [
    (_MARGEN, _MARGEN),
    (config.PANTALLA_ANCHO - _MARGEN, _MARGEN),
    (config.PANTALLA_ANCHO // 2, config.PANTALLA_ALTO // 2),
    (_MARGEN, config.PANTALLA_ALTO - _MARGEN),
    (config.PANTALLA_ANCHO - _MARGEN, config.PANTALLA_ALTO - _MARGEN),
]


def _construir_normales(
    puntos_raw: list[tuple[float, float]], objetivos: list[float]
) -> tuple[list[list[float]], list[float]]:
    """Arma el sistema de ecuaciones normales (A^T A) coef = A^T b para ajustar
    objetivo = coef_a*x_raw + coef_b*y_raw + coef_c por mínimos cuadrados."""
    ata = [[0.0] * 3 for _ in range(3)]
    atb = [0.0, 0.0, 0.0]
    for (x_raw, y_raw), objetivo in zip(puntos_raw, objetivos):
        fila = (x_raw, y_raw, 1.0)
        for i in range(3):
            atb[i] += fila[i] * objetivo
            for j in range(3):
                ata[i][j] += fila[i] * fila[j]
    return ata, atb


def _resolver_3x3(matriz: list[list[float]], vector: list[float]) -> list[float]:
    """Resuelve un sistema lineal 3x3 por eliminación gaussiana con pivoteo parcial."""
    m = [fila[:] + [vector[i]] for i, fila in enumerate(matriz)]
    n = 3
    for col in range(n):
        pivote = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivote][col]) < 1e-9:
            raise ValueError("Puntos de calibración colineales o degenerados")
        m[col], m[pivote] = m[pivote], m[col]
        for fila in range(col + 1, n):
            factor = m[fila][col] / m[col][col]
            for k in range(col, n + 1):
                m[fila][k] -= factor * m[col][k]
    solucion = [0.0] * n
    for fila in range(n - 1, -1, -1):
        suma = sum(m[fila][k] * solucion[k] for k in range(fila + 1, n))
        solucion[fila] = (m[fila][n] - suma) / m[fila][fila]
    return solucion


def calcular_transformacion(
    puntos_raw: list[tuple[float, float]], puntos_reales: list[tuple[float, float]]
) -> dict[str, float]:
    """Ajusta por mínimos cuadrados la transformación afín que mapea coordenadas
    crudas del touch a coordenadas reales de pantalla:

        x_real = a*x_raw + b*y_raw + c
        y_real = d*x_raw + e*y_raw + f

    Requiere al menos 3 puntos no colineales. Con los 5 de `PUNTOS_CALIBRACION`
    el sistema queda sobredeterminado, así que el ajuste amortigua el ruido de
    cada toque individual en vez de interpolar exactamente por 3 de ellos.
    """
    xs_reales = [p[0] for p in puntos_reales]
    ys_reales = [p[1] for p in puntos_reales]

    a, b, c = _resolver_3x3(*_construir_normales(puntos_raw, xs_reales))
    d, e, f = _resolver_3x3(*_construir_normales(puntos_raw, ys_reales))

    return {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f}


def aplicar_transformacion(
    pos: tuple[float, float], coefs: dict[str, float]
) -> tuple[float, float]:
    """Corrige una coordenada cruda del touch con los coeficientes de `calcular_transformacion`."""
    x_raw, y_raw = pos
    x_real = coefs["a"] * x_raw + coefs["b"] * y_raw + coefs["c"]
    y_real = coefs["d"] * x_raw + coefs["e"] * y_raw + coefs["f"]
    return (x_real, y_real)


def guardar_calibracion(coefs: dict[str, float], ruta: Path) -> None:
    ruta.write_text(json.dumps(coefs, indent=2))


def cargar_calibracion(ruta: Path) -> dict[str, float] | None:
    """Devuelve los coeficientes guardados, o `None` si todavía no se calibró
    (archivo inexistente) — quien llama decide si usar coordenadas sin corregir."""
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text())


def _dibujar_objetivo(pantalla, fuente, centro: tuple[float, float], indice: int, total: int) -> None:
    pantalla.fill(_NEGRO)
    x, y = centro
    pygame.draw.line(pantalla, _VERDE, (x - 15, y), (x + 15, y), 2)
    pygame.draw.line(pantalla, _VERDE, (x, y - 15), (x, y + 15), 2)
    pygame.draw.circle(pantalla, _VERDE, (int(x), int(y)), 15, 2)
    texto = fuente.render(f"Tocá la cruz ({indice}/{total})", True, _BLANCO)
    pantalla.blit(texto, texto.get_rect(center=(config.PANTALLA_ANCHO // 2, 30)))
    pygame.display.flip()


def _esperar_toque() -> tuple[float, float]:
    while True:
        for evento in pygame.event.get():
            if evento.type == pygame.FINGERDOWN:
                return (evento.x * config.PANTALLA_ANCHO, evento.y * config.PANTALLA_ALTO)
            if evento.type == pygame.MOUSEBUTTONDOWN:
                return evento.pos
        pygame.time.wait(20)


def ejecutar_calibracion() -> None:
    """Flujo interactivo: muestra los puntos de `PUNTOS_CALIBRACION` uno por vez,
    captura el toque físico correspondiente a cada uno, ajusta la transformación
    y la guarda en `config.CALIBRACION_TOUCH_PATH`."""
    pygame.init()
    pantalla = pygame.display.set_mode((config.PANTALLA_ANCHO, config.PANTALLA_ALTO))
    fuente = pygame.font.Font(None, 32)

    puntos_raw: list[tuple[float, float]] = []

    try:
        for i, punto_real in enumerate(PUNTOS_CALIBRACION, start=1):
            _dibujar_objetivo(pantalla, fuente, punto_real, i, len(PUNTOS_CALIBRACION))
            pos_raw = _esperar_toque()
            puntos_raw.append(pos_raw)
            logger.info(
                "Punto %d/%d: tocado en %s (objetivo %s)",
                i, len(PUNTOS_CALIBRACION), pos_raw, punto_real,
            )
            pygame.event.clear()
            pygame.time.wait(300)
    except KeyboardInterrupt:
        pygame.quit()
        logger.warning("Calibración cancelada, no se guardó nada")
        return

    coefs = calcular_transformacion(puntos_raw, PUNTOS_CALIBRACION)
    guardar_calibracion(coefs, config.CALIBRACION_TOUCH_PATH)
    logger.info("Calibración guardada en %s: %s", config.CALIBRACION_TOUCH_PATH, coefs)
    pygame.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ejecutar_calibracion()
