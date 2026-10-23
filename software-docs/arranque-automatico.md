# Arranque automático: la Pi prende directo en el menú

Cómo hacer que, al enchufar la Raspberry, la pantalla táctil muestre el menú de
`io/menus_gpio.py` sin entrar por SSH. Se hace con un servicio de systemd, `tablero.service`,
que corre el mismo programa que `uv run python -m tablero.io.menus_gpio`.

Todo se corre **en la Pi, por SSH, en bash** (no en la notebook). Cada paso dice qué se
espera ver; si no sale eso, no seguir al siguiente.

## Antes de empezar

`menus_gpio` tiene que andar a mano (ya pasó en la Pi, punto 3.2 de
[`pendiente-pi.md`](./pendiente-pi.md#32-jugar-desde-la-pantalla); conviene repetirlo si hubo
cambios desde entonces). Si no anda por SSH, el servicio tampoco va a andar: se va a reiniciar
en loop y no se ve por qué en la pantalla.

```bash
cd ~/tablero-ajedrez-inteligente/tablero
uv run python -m tablero.io.menus_gpio
```

Tiene que aparecer el menú en el panel. Salir con Ctrl+C.

## 1. Datos que usa el servicio

```bash
id -u magnus; id -g magnus
ls -l ~/tablero-ajedrez-inteligente/tablero/.venv/bin/python
```

- Los dos `id` dan un número (casi seguro `1000` y `1000`). Si **no** son `1000`, cambiar
  `SUDO_UID`/`SUDO_GID` en el paso 2.
- El `ls` muestra un symlink a un Python 3.12 o más nuevo. Si dice "No such file", falta
  `uv sync` (en la Pi, ver [`pantalla.md`](./pantalla.md#instalación-de-pygame) por el
  `--no-binary-package pygame`).

## 2. Crear el servicio

Pegar entero (desde `sudo tee` hasta `EOF`):

```bash
sudo tee /etc/systemd/system/tablero.service > /dev/null <<'EOF'
[Unit]
Description=Tablero de ajedrez: menú de la pantalla táctil
After=local-fs.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/magnus/tablero-ajedrez-inteligente/tablero
# Esperar a que el driver del panel (overlay piscreen) aparezca en /sys/class/drm: si SDL
# arranca antes, no lo encuentra, usa card1 y la pantalla queda en blanco sin error.
ExecStartPre=/bin/sh -c 'until grep -qs "^DRIVER=ili9486" /sys/class/drm/card*/device/uevent; do sleep 1; done'
# El python del .venv directo, ya como root: sin `uv run` (no sincroniza en cada arranque)
# y sin el relanzamiento con sudo del __main__ (no hace falta, ya es root).
ExecStart=/home/magnus/tablero-ajedrez-inteligente/tablero/.venv/bin/python -m tablero.io.menus_gpio
# Lo que lee _devolver_registros_al_usuario(): los PGN quedan de magnus y no de root.
Environment=SUDO_UID=1000
Environment=SUDO_GID=1000
Environment=PYTHONUNBUFFERED=1
# SIGINT = Ctrl+C: el programa apaga los LEDs, libera GPIO y el Nano y cierra el registro.
# Con el SIGTERM por defecto Python muere sin pasar por el `finally` y los LEDs quedan prendidos.
KillSignal=SIGINT
# El SIGINT solo al programa, no a Stockfish: lo cierra el programa mismo, como con Ctrl+C.
KillMode=mixed
TimeoutStopSec=10
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

No imprime nada. Para ver que quedó bien:

```bash
cat /etc/systemd/system/tablero.service
systemd-analyze verify /etc/systemd/system/tablero.service
```

- `cat` muestra el archivo tal cual el bloque de arriba.
- `systemd-analyze verify` no imprime nada (o solo avisos de **otros** servicios del
  sistema, que no importan). Si nombra `tablero.service`, copiar el error y revisar.

## 3. Probarlo sin reiniciar

```bash
sudo systemctl daemon-reload
sudo systemctl start tablero
systemctl status tablero --no-pager
```

- `status` dice `Active: active (running)` y el menú aparece en el panel.
- Los toques y los botones del reloj andan igual que por SSH.
- Si dice `activating (auto-restart)` o `failed`, ver los logs:
  `journalctl -u tablero -n 50 --no-pager`.

Pararlo y ver que apaga todo:

```bash
sudo systemctl stop tablero
systemctl status tablero --no-pager
```

- `Active: inactive (dead)`, en pocos segundos (no 10).
- Los LEDs se apagan.

## 4. Activarlo al arranque

```bash
sudo systemctl enable tablero
systemctl is-enabled tablero
```

`is-enabled` dice `enabled`. Recién ahora reiniciar:

```bash
sudo reboot
```

- Después de unos ~30-60 s (lo que tarda en bootear la Pi 3B), el panel muestra el menú
  sin haber entrado por SSH.
- Una partida contra un amigo anda con el tablero, los LEDs y los botones.

Si la pantalla queda en blanco o con la consola, entrar por SSH y mirar
`journalctl -u tablero -b --no-pager` (`-b`: solo este arranque).

## Uso diario

| Para | Comando |
|---|---|
| Ver si está corriendo | `systemctl status tablero --no-pager` |
| Ver los logs en vivo | `journalctl -u tablero -f` |
| Pararlo (para probar otra cosa por SSH) | `sudo systemctl stop tablero` |
| Volver a arrancarlo | `sudo systemctl start tablero` |
| Después de un `pushpi` con cambios de código | `sudo systemctl restart tablero` |
| Que deje de arrancar solo | `sudo systemctl disable tablero` |

**Mientras el servicio corre, no se puede correr otra cosa del tablero por SSH**
(`juego.py`, `prueba_tablero`, `sensores`, `leds`, `menus_gpio`…): el servicio tiene
tomados la pantalla, la tira de LEDs, los botones y el puerto del Nano. Primero
`sudo systemctl stop tablero`, y al terminar `sudo systemctl start tablero`.

`pushpi` no reinicia el servicio: hasta el `restart` sigue corriendo el código viejo. Si el
cambio agrega dependencias, antes `uv sync` en la Pi (con `UV_NO_BINARY_PACKAGE=pygame`
seteada, si no reinstala el wheel de pygame sin KMSDRM; ver [`pantalla.md`](./pantalla.md#instalación-de-pygame)).

## Por qué así

- **Servicio de systemd y no autologin + `.bashrc`**: arranca aunque nadie se loguee, se
  reinicia solo si el programa se cae (`Restart=on-failure`; salir con Ctrl+C/`stop` es
  salida normal y no lo relanza) y los logs quedan en `journalctl`.
- **Como root directo**: los LEDs (`rpi-ws281x`) necesitan root, y el `__main__` de
  `menus_gpio` se relanza con `sudo` si no lo es. Correrlo ya como root evita ese `sudo` sin
  terminal y que las señales de systemd pasen por un proceso intermedio. `SUDO_UID`/`SUDO_GID`
  son las variables que el programa usa para devolverle los registros al usuario
  (`_devolver_registros_al_usuario`), así que se setean a mano.
- **`KillSignal=SIGINT`**: `menus.ejecutar_menus` sale limpio con `KeyboardInterrupt`
  (abandona la partida en el registro, apaga LEDs, libera GPIO y el Nano). Python no maneja
  `SIGTERM`, que es lo que manda systemd por defecto. `KillMode=mixed` hace que la señal le
  llegue solo al proceso principal y no a todo el grupo: Stockfish corre en su propio grupo
  de procesos justamente para que un Ctrl+C no lo mate a mitad de jugada (ver
  [`motor.md`](./motor.md)), y lo cierra el programa al salir. Lo que quede vivo después
  recibe `SIGKILL`.
- **Espera del panel en `ExecStartPre`**: el número de `/dev/dri/cardN` del panel cambia entre
  arranques y `io/_sdl.py` lo busca por driver al importar. Si el servicio arranca antes de
  que cargue el driver del overlay, no lo encuentra y usa `card1`, que puede ser la HDMI:
  pantalla en blanco sin ningún error ([`pantalla.md`](./pantalla.md#problemas-reales-encontrados-al-hacerlo-andar),
  problema 3). Si el overlay no cargara nunca, el `until` espera hasta el timeout de arranque
  de systemd (90 s) y el servicio queda `failed`.
- **El Nano no se espera**: si todavía no está listo, `menus_gpio` lo avisa en el log y lo
  vuelve a abrir al empezar una partida; si sigue sin estar, la pantalla muestra "Problema
  con el tablero".
- **Sin `uv run`**: `uv run` sincroniza el entorno antes de correr y, como root, podría
  querer tocar el `.venv` de magnus o el cache de uv. El python del `.venv` ya tiene el
  paquete instalado (editable), así que los cambios de código entran con un `restart`.
