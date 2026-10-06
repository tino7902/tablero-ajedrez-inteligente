# `io/leds.py`

Controla los 65 LEDs WS2812B del tablero (64 casillas + 1 LED de sacrificio, ver
`hardware-docs/componentes.md`) con `rpi-ws281x`. Implementado pero **todavía no probado en
el prototipo**.

## API

| Función/clase | Qué hace |
|---|---|
| `indice_de(casilla)` | Índice en la tira del LED de una `chess.Square`, según la tabla `LED_DE_CASILLA` |
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
| `LED_DE_CASILLA` | serpentina desde a1 | Tabla de 64 índices (`[chess.Square]`); placeholder hasta correr `calibrar` |

## Decisiones de diseño

- **Mapeo casilla → LED por tabla, no por fórmula**: `LED_DE_CASILLA[casilla]` da el índice
  en la tira, igual que las permutaciones de `io/sensores.py` para la matriz. Así no importa
  cómo se haya soldado la tira (serpentina, filas en el mismo sentido, arrancando en h8...) ni
  si algún tramo quedó salteado: se mide con `calibrar` y se pega el resultado. El valor por
  defecto supone serpentina desde a1 justo después del LED de sacrificio.
- **Brillo bajo por defecto**: 64 LEDs en blanco al 100 % consumen ~3,8 A, en el límite de la
  fuente de 5 V >4 A. Para las pruebas alcanza con 32; `--brillo` permite subirlo.
- **LED de sacrificio siempre apagado**: su único trabajo es regenerar la señal de datos a
  nivel de 5 V para el resto de la tira (alimentado a ~4,3 V por el 1N4007), así que no importa
  qué color muestre.

## Requisitos en la Raspberry

- **Root**: `rpi-ws281x` accede a `/dev/mem`. Se corre como el resto del proyecto,
  `uv run python -m tablero.io.leds ...` desde `tablero/`: si el proceso no es root, el
  `__main__` de `io/leds.py` se relanza con `sudo <python del .venv> -m tablero.io.leds ...`
  (en Raspberry Pi OS el usuario principal tiene sudo sin contraseña). No usar
  `sudo uv run`, que corre con el entorno de root y puede dejar archivos de root en el
  `.venv`. Desde código (un futuro loop de juego que importe `TiraLeds`) el relanzamiento no
  aplica: ese proceso tiene que arrancar como root.
- **Audio analógico desactivado**: el PWM de los LEDs es el mismo que el del audio. En
  `/boot/firmware/config.txt` (o `/boot/config.txt` en sistemas viejos) poner
  `dtparam=audio=off` y reiniciar. Sin esto, los LEDs parpadean con colores al azar o no
  responden.
- **GND común** entre la fuente de 5 V de los LEDs y la Raspberry.

## Cómo probarlo

Desde `tablero/`, por SSH en la Raspberry:

```bash
uv run python -m tablero.io.leds todos      # 64 casillas en rojo, verde, azul y blanco
uv run python -m tablero.io.leds recorrer   # un LED por vez, Enter para el siguiente
uv run python -m tablero.io.leds esquinas   # a1 rojo, h1 verde, a8 azul, h8 amarillo
uv run python -m tablero.io.leds calibrar   # genera LED_DE_CASILLA
uv run python -m tablero.io.leds verificar  # recorre a1, b1, ..., h8 con el mapeo
```

Orden recomendado: `todos` (¿prenden todos? ¿colores correctos, o rojo y verde invertidos?
Eso sería `strip_type` GRB/RGB), después `calibrar` y por último `verificar`/`esquinas` para
confirmar el mapeo. `Ctrl+C` apaga la tira y sale.

### `calibrar`

Prende cada LED (1..64) en blanco y pregunta en qué casilla se ve. Se responde con el nombre
(`e4`), `-` si ese LED no cae en ninguna casilla, o `r` para volver al LED anterior si hubo un
error. No deja asignar dos LEDs a la misma casilla. Al final imprime la tupla
`LED_DE_CASILLA` lista para pegar en `config.py`, una fila de ajedrez por línea.
