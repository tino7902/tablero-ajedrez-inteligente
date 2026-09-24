# `io/leds.py`

Controla los 65 LEDs WS2812B del tablero (64 casillas + 1 LED de sacrificio, ver
`hardware-docs/componentes.md`) con `rpi-ws281x`. Implementado pero **todavía no probado en
el prototipo**.

## API

| Función/clase | Qué hace |
|---|---|
| `indice_de(casilla)` | Índice en la tira del LED de una `chess.Square`, según `LED_ZIGZAG` |
| `TiraLeds(brillo)` | Inicializa la tira (`PixelStrip.begin()`) |
| `.encender(casilla, color)` / `.encender_indice(i, color)` | Fija el color de un LED (no se ve hasta `mostrar()`) |
| `.limpiar()` / `.mostrar()` / `.apagar()` | Todo en negro / enviar a la tira / las dos cosas |
| `ROJO`, `VERDE`, `AZUL`, `AMARILLO`, `BLANCO`, `APAGADO` | Colores (`rpi_ws281x.Color`) |

## Configuración (`config.py`)

| Constante | Valor | Nota |
|---|---|---|
| `LED_GPIO_BCM` | 12 | Pin físico 32. `rpi-ws281x` usa numeración **BCM**, no BOARD como `io/sensores.py` |
| `LED_CANAL_PWM` | 0 | GPIO 12 es PWM0 |
| `LED_CANTIDAD` | 65 | Incluye el LED de sacrificio |
| `LED_INDICE_SACRIFICIO` | 0 | Siempre apagado: `mostrar()` lo fuerza a negro antes de enviar |
| `LED_BRILLO` | 32 | Brillo global 0–255 |
| `LED_ZIGZAG` | `True` | Supuesto hasta confirmarlo con `recorrer` |

## Decisiones de diseño

- **Mapeo casilla → LED por fórmula, no por tabla**: índice 1 en a1, columnas a→h dentro de
  cada fila; con `LED_ZIGZAG` las filas pares (2, 4, 6, 8) van h→a, que es lo típico al tender
  una tira en serpentina. Si `recorrer` muestra otro orden (por ejemplo arranca en h8), se
  cambia la fórmula en `indice_de()` o se pasa a una tabla de 64.
- **Brillo bajo por defecto**: 64 LEDs en blanco al 100 % consumen ~3,8 A, en el límite de la
  fuente de 5 V >4 A. Para las pruebas alcanza con 32; `--brillo` permite subirlo.
- **LED de sacrificio siempre apagado**: su único trabajo es regenerar la señal de datos a
  nivel de 5 V para el resto de la tira (alimentado a ~4,3 V por el 1N4007), así que no importa
  qué color muestre.

## Requisitos en la Raspberry

- **Root**: `rpi-ws281x` accede a `/dev/mem`. Correr con
  `sudo .venv/bin/python -m tablero.io.leds ...` desde `tablero/` (no `sudo uv run`, que usa
  el entorno de root).
- **Audio analógico desactivado**: el PWM de los LEDs es el mismo que el del audio. En
  `/boot/firmware/config.txt` (o `/boot/config.txt` en sistemas viejos) poner
  `dtparam=audio=off` y reiniciar. Sin esto, los LEDs parpadean con colores al azar o no
  responden.
- **GND común** entre la fuente de 5 V de los LEDs y la Raspberry.

## Cómo probarlo

Desde `tablero/`, por SSH en la Raspberry:

```bash
sudo .venv/bin/python -m tablero.io.leds todos      # 64 casillas en rojo, verde, azul y blanco
sudo .venv/bin/python -m tablero.io.leds recorrer   # un LED por vez, Enter para el siguiente
sudo .venv/bin/python -m tablero.io.leds esquinas   # a1 rojo, h1 verde, a8 azul, h8 amarillo
```

Orden recomendado: `todos` (¿prenden todos? ¿colores correctos, o rojo y verde invertidos?
Eso sería `strip_type` GRB/RGB), después `recorrer` (anotar en qué casilla cae cada índice) y
por último `esquinas` para confirmar el mapeo. `Ctrl+C` apaga la tira y sale.
