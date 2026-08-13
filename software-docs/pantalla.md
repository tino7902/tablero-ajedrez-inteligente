# `io/pantalla.py`

Control de la pantalla táctil integrada: la RPI LCD V3, un panel SPI de 480x320 con
chip de video ILI9486 y controlador táctil XPT2046. Además de dibujar texto estático,
ya incluye un test manual de touch (`probar_boton`) — ver "Precisión táctil" más abajo
sobre lo que se observó al probarlo en hardware real.

## Por qué existe este módulo

Aísla al resto del proyecto de los detalles de cómo se dibuja sobre la pantalla física
(inicialización de `pygame`, backend de video, tamaño en píxeles). Cualquier código que
quiera mostrar algo solo necesita llamar a `mostrar_texto`, sin conocer que por debajo
hay un dispositivo DRM/KMS.

## API

| Función | Qué hace |
|---|---|
| `mostrar_texto(texto)` | Inicializa `pygame`, pinta la pantalla de negro y dibuja `texto` centrado en blanco |
| `probar_boton()` | Dibuja un botón de prueba y loguea (`logging`) cada evento de toque recibido — `FINGERDOWN`/`MOUSEBUTTONDOWN`, coordenadas ya corregidas por calibración (si existe), y si cayó dentro del botón. Test manual, corre hasta `Ctrl+C`. |

`io/calibracion_touch.py` es el módulo de calibración táctil — ver "Calibración del touch" más abajo.

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
   dtoverlay=piscreen,drm,speed=16000000,rotate=180
   ```
3. Instalar las libs de sistema que `pygame` necesita para dibujar sobre DRM/KMS:
   ```bash
   sudo apt install -y libsdl2-2.0-0 libsdl2-dev libdrm2 libgbm1 \
       libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
       libfreetype6-dev libjpeg-dev libportmidi-dev pkg-config \
       libegl1 libgles2 python3-dev
   ```
4. Si el sistema es **Raspberry Pi OS Desktop** (no Lite), hay que bootear a consola
   en vez de escritorio — el compositor gráfico (Wayfire/labwc) toma el "DRM master"
   al arrancar y bloquea a `pygame` para usar la pantalla vía KMS, aunque todo lo
   demás esté bien configurado:
   ```bash
   sudo raspi-config nonint do_boot_behaviour B2   # consola con autologin
   ```
5. `sudo reboot`.

`rotate=180` es el valor que terminó siendo correcto para el montaje físico de este
tablero — depende de cómo quede la pantalla en cada caso, se ajusta por prueba y error
(`0`, `90`, `180`, `270`). `speed` es la velocidad del bus SPI en Hz; `16000000`
funcionó sin ajustes.

### Verificación

No hay un mensaje único y confiable a buscar en `dmesg` — el driver que atiende el
overlay se anuncia con el nombre del chip (`ili9486`, `spi0`, etc.), no con la palabra
"piscreen", así que buscar `dmesg | grep -i piscreen` puede no devolver nada aunque el
panel esté andando. La verificación real es visual: si el overlay cargó bien, el panel
se enciende y muestra lo que dibuje la app.

### Problemas reales encontrados al hacerlo andar

Dos problemas no obvios aparecieron al probar esto en la práctica (Raspberry Pi OS
Desktop sobre Trixie), ambos con el mismo síntoma (`pygame.error: kmsdrm not
available`) pero causas distintas:

1. **El wheel binario de `pygame` no sirve**: trae su propio SDL2 compilado sin
   soporte KMSDRM, por portabilidad. Se resuelve forzando a que `pygame` se compile
   desde fuente enlazando contra el SDL2 del sistema (ver "Instalación de `pygame`"
   más abajo) — no alcanza con instalar las libs de sistema si `pygame` sigue usando
   su propio SDL2 empaquetado.
2. **El compositor de escritorio bloquea el DRM master**: aunque el SDL2 del sistema
   sí tiene KMSDRM compilado, en Raspberry Pi OS Desktop el compositor gráfico
   (Wayfire/labwc) toma el control exclusivo de la pantalla al arrancar, y solo un
   proceso a la vez puede ser dueño del DRM master. Por eso hace falta el paso 4 de
   arriba (bootear a consola).

### Instalación de `pygame`

`pyproject.toml` tiene `[tool.uv] no-binary-package = ["pygame"]`, que fuerza a `uv`
a compilar `pygame` desde fuente en vez de usar el wheel binario de PyPI (ver el
problema 1 arriba). Como ya se había instalado el wheel roto antes de agregar esa
configuración, la primera vez hace falta forzar la recompilación:
```bash
cd tablero
uv sync --reinstall-package pygame
```
Compilar en una Raspberry Pi 3B tarda varios minutos (no es una descarga de wheel).
Compilaciones posteriores (`uv sync` normal) ya respetan la config y no hace falta
el `--reinstall-package`.

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
  Las variables de entorno de SDL se setean con `io/_sdl.py::configurar_entorno_sdl()` al
  importar el módulo, antes de tocar `pygame.display`, porque SDL las lee una sola vez al
  inicializar el video. Esa función es compartida por `pantalla.py`, `calibracion_touch.py`
  y `menus.py` — ver [`menus.md`](./menus.md#modo-ventana-testear-sin-la-raspberry) para el
  porqué de centralizarla ahí en vez de duplicarla, y para el toggle
  `TABLERO_PANTALLA_VENTANA=1` que permite correr sin el panel físico.
- **`pygame` compilado desde fuente (`[tool.uv] no-binary-package` en
  `pyproject.toml`), no el wheel de PyPI**: el wheel trae un SDL2 propio sin soporte
  KMSDRM compilado. Ver "Problemas reales encontrados" más abajo.
- **Consola en vez de escritorio (Raspberry Pi OS Desktop)**: el compositor gráfico
  toma el DRM master al arrancar y bloquea cualquier otro proceso (incluido
  `pygame`) de usar la pantalla vía KMS. Se resuelve booteando a consola
  (`raspi-config nonint do_boot_behaviour B2`) en vez de tocar el ciclo de vida del
  compositor a mano.
- **Sin manejo de rotación en Python**: la rotación física se resuelve en el parámetro
  `rotate=` del overlay (nivel kernel/DRM), no en la app — el driver ya entrega el
  framebuffer con la orientación final, así que `config.py` no tiene una constante de
  rotación (evita tener un valor que ningún código lee).

## Configuración relacionada (`config.py`)

- `PANTALLA_ANCHO` / `PANTALLA_ALTO`: `480` / `320`, resolución del panel.
- `PANTALLA_TAMANO_FUENTE`: tamaño de fuente por default para `mostrar_texto`.

## Precisión táctil: a tener en cuenta en el diseño de la UI

Al probar `probar_boton()` en la pantalla física, el touch registra bien el contacto (el
evento `FINGERDOWN`/`MOUSEBUTTONDOWN` se loguea siempre que se toca), pero la posición
reportada no siempre coincide con el punto físico tocado: hubo toques dentro del área
visual del botón que no sumaron al contador porque la coordenada del evento cayó fuera de
`rect_boton`. No se investigó todavía la causa exacta (calibración del XPT2046, el
`rotate=180` del overlay, o algo inherente a este panel resistivo) — queda pendiente si
hace falta más precisión más adelante.

Ver [`consideracion-sobre-diseño.md`](./consideracion-sobre-diseño.md) para las implicancias
de esto en el diseño de cualquier UI táctil futura (botones grandes, separación entre
elementos, evitar UI densa).

## Calibración del touch

`io/calibracion_touch.py` corrige el descalce de "Precisión táctil" ajustando una
transformación afín entre la coordenada cruda que reporta el XPT2046 y la coordenada real
de pantalla:

```
x_real = a*x_raw + b*y_raw + c
y_real = d*x_raw + e*y_raw + f
```

No se implementó a nivel de sistema (`xinput_calibrator` u otra herramienta de X11) porque
el panel corre en modo DRM/KMS sin escritorio (ver "Requisito de sistema" arriba) — no hay
X11 corriendo, así que la corrección se resuelve en la propia app.

### Cómo calibrar

Por SSH, en la Raspberry, con el overlay activado:

```bash
cd tablero && uv run python -m tablero.io.calibracion_touch
```

Se muestran 5 cruces en orden (las 4 esquinas, con margen de 40px para evitar el borde
donde el resistivo es menos preciso, más el centro). Tocar cada una; al terminar se ajustan
los 6 coeficientes por mínimos cuadrados (el sistema queda sobredeterminado con 5 puntos
para 3 incógnitas por eje, así que amortigua el ruido de un toque individual en vez de
interpolar exactamente por 3 de ellos) y se guardan en `config.CALIBRACION_TOUCH_PATH`
(`tablero/calibracion_touch.json`, gitignoreado — es específico del panel físico montado,
igual que el `rotate=180` del overlay).

`probar_boton()` (y cualquier código futuro que lea touch) carga ese archivo si existe y
corrige las coordenadas antes de usarlas; si no existe, loguea un warning y usa las
coordenadas crudas sin corregir.

Si con el tiempo el ajuste afín de 5 puntos no alcanza (por ejemplo si el panel resistivo
tiene distorsión no lineal fuerte cerca de los bordes), la vía de escape es agregar más
puntos de calibración a `PUNTOS_CALIBRACION` — el ajuste por mínimos cuadrados ya soporta
cualquier cantidad ≥ 3 sin cambios.

## Fuera de alcance (todavía)

- Integración con `logica/estado_tablero.py` (mostrar el estado real de la partida).
- Refresco dinámico / loop de render — por ahora son dibujos estáticos entre toques.

## Cómo probarlo

Por SSH, en la Raspberry, con el overlay activado:

```bash
cd tablero && uv sync
uv run python -m tablero.io.pantalla
```

`mostrar_texto` no tiene un `__main__` propio todavía — el `__main__` del módulo corre
`probar_boton()`, que debería mostrar un botón gris "Tocame" centrado y loguear cada toque
en consola.
