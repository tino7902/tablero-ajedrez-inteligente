# `io/pantalla.py`

Control de la pantalla táctil integrada: la RPI LCD V3, un panel SPI de 480x320 con
chip de video ILI9486 y controlador táctil XPT2046. Esta primera versión solo muestra
texto estático — la lectura táctil queda fuera de alcance por ahora.

## Por qué existe este módulo

Aísla al resto del proyecto de los detalles de cómo se dibuja sobre la pantalla física
(inicialización de `pygame`, backend de video, tamaño en píxeles). Cualquier código que
quiera mostrar algo solo necesita llamar a `mostrar_texto`, sin conocer que por debajo
hay un dispositivo DRM/KMS.

## API

| Función | Qué hace |
|---|---|
| `mostrar_texto(texto)` | Inicializa `pygame`, pinta la pantalla de negro y dibuja `texto` centrado en blanco |

## Requisito de sistema: overlay de kernel `piscreen`

Esta pantalla es un panel SPI, no HDMI: no anda "sola", necesita que el kernel de la
Raspberry Pi sepa manejar el chip ILI9486 (video) y XPT2046 (touch). Eso se resuelve
con el overlay `piscreen`, que viene compilado en el kernel oficial de Raspberry Pi OS
(no hace falta instalar nada de terceros).

Pasos (una sola vez, en la Raspberry, por SSH):

1. Backup de `config.txt` (en Raspberry Pi OS Bookworm/Trixie vive en
   `/boot/firmware/config.txt`, no en `/boot/`):
   ```bash
   sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak-pantalla
   ```
2. Agregar al final del archivo:
   ```
   dtparam=spi=on
   dtoverlay=piscreen,drm,speed=16000000,rotate=0
   ```
3. Instalar las libs de sistema que `pygame` necesita para dibujar sobre DRM/KMS:
   ```bash
   sudo apt install -y libsdl2-2.0-0 libsdl2-dev libdrm2 libgbm1
   ```
4. `sudo reboot`.

`rotate` depende de cómo quede montada la pantalla en el tablero — se ajusta por
prueba y error (`0`, `90`, `180`, `270`) viendo la orientación real. `speed` es la
velocidad del bus SPI en Hz; `16000000` es un punto de partida razonable, no un valor
garantizado para todas las unidades del panel.

### Verificación

No hay un mensaje único y confiable a buscar en `dmesg` — el driver que atiende el
overlay se anuncia con el nombre del chip (`ili9486`, `spi0`, etc.), no con la palabra
"piscreen", así que buscar `dmesg | grep -i piscreen` puede no devolver nada aunque el
panel esté andando. La verificación real es visual: si el overlay cargó bien, el panel
se enciende y muestra lo que dibuje la app.

## Decisiones de diseño

- **Overlay `piscreen` en modo DRM, no `goodtft/LCD-show`**: `goodtft/LCD-show` es un
  driver de terceros (paquetes `.deb` prearmados + patches al kernel vía script `sudo`)
  con issues abiertos de rotura en Bookworm/Trixie
  ([#369](https://github.com/goodtft/LCD-show/issues/369),
  [#350](https://github.com/goodtft/LCD-show/issues/350)). El overlay `piscreen` está
  compilado en el kernel oficial de Raspberry Pi (`raspberrypi/linux`), cubre paneles
  ILI9486+XPT2046 como este, y se activa con una línea de configuración sin ejecutar
  nada de terceros.
- **Modo `drm`, no el legacy `fbtft`**: en Bookworm/Trixie el framebuffer legacy
  (`fbcon`) tiene cada vez más fricción con el resto del stack gráfico. El modo DRM/KMS
  es el que reportan funcionando en instalaciones recientes. Por eso no hay ningún
  `/dev/fb1` ni constante de path de framebuffer en `config.py` — el panel aparece como
  dispositivo DRM (`/dev/dri/card*`).
- **`pygame` con backend `SDL_VIDEODRIVER=kmsdrm`**: coherente con el modo DRM del
  overlay. Sin X11/escritorio — la app dibuja directo sobre el framebuffer del panel.
  Las variables de entorno de SDL se setean al importar el módulo, antes de tocar
  `pygame.display`, porque SDL las lee una sola vez al inicializar el video.
- **Sin manejo de rotación en Python**: la rotación física se resuelve en el parámetro
  `rotate=` del overlay (nivel kernel/DRM), no en la app — el driver ya entrega el
  framebuffer con la orientación final, así que `config.py` no tiene una constante de
  rotación (evita tener un valor que ningún código lee).

## Configuración relacionada (`config.py`)

- `PANTALLA_ANCHO` / `PANTALLA_ALTO`: `480` / `320`, resolución del panel.
- `PANTALLA_TAMANO_FUENTE`: tamaño de fuente por default para `mostrar_texto`.

## Fuera de alcance (todavía)

- Lectura de eventos táctiles (el touch XPT2046 ya queda expuesto como dispositivo
  `evdev` en `/dev/input/` gracias al mismo overlay, pero nada en el repo lo lee aún).
- Integración con `logica/estado_tablero.py` (mostrar el estado real de la partida).
- Refresco dinámico / loop de render — por ahora es un dibujo único y estático.

## Cómo probarlo

Por SSH, en la Raspberry, con el overlay activado:

```bash
cd tablero && uv sync
uv run python -m tablero.io.pantalla
```

Debería verse "Hola tablero" centrado en la pantalla física.
