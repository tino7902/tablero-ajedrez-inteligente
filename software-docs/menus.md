# `io/menus.py` — la pantalla táctil

Interfaz de la pantalla (480×320) para jugar en el tablero sin la terminal. Implementa los
bocetos de [`diseño-docs/diseño-interfaz.md`](../diseño-docs/diseño-interfaz.md) y lo acordado
con Tino el 2026-10-22. **Escrita, sin probar todavía** (ni en la notebook ni en la Pi; ver
[`pendiente-pi.md`](./pendiente-pi.md#32-jugar-desde-la-pantalla)).

## Flujo

```
menú principal
 ├─ Contra un amigo → tiempo (3 / 5 / 10 min) → acomodá las piezas → 3, 2, 1 → partida PvP → fin
 └─ Contra Magnus → dificultad → color (blancas / aleatorio / negras) → acomodá las piezas → partida → fin
```

- **Acomodá las piezas**: compara con la posición inicial, como `juego.py`. Los LEDs marcan
  rojo (falta) y amarillo (sobra), y la pantalla dice cuántas y cuáles. Con todo en su
  lugar, "¡Posición lista!" y cualquier botón del reloj arranca. Tiene "Volver".
- **Cuenta regresiva 3, 2, 1**: solo en PvP. Contra Magnus el cronómetro arranca con el botón.
- **Partida PvP**: dos columnas (Blancas, Negras) con "¡Es tu turno!", el reloj (borde verde
  el que corre) y dos botones, "¿Rendirse?" y "Tablas". Abajo, en naranja, la línea de estado:
  lo que se está armando ("Blancas: peón e2→e4, falta apretar el reloj") o el motivo del
  último botón rechazado.
- **Tablas (solo PvP)**: al tocar "Tablas", ese botón pasa a "Ofrecidas" y en la columna del
  rival aparecen "Aceptar" y "Rechazar". Aceptar termina en ½-½ ("Tablas por acuerdo");
  confirmar una jugada sin contestar es rechazar (reglamento FIDE). No se puede retirar; una
  oferta a la vez; se puede volver a ofrecer después de un rechazo. El reloj sigue corriendo.
  Lógica en `PartidaFisica.ofrecer_tablas` / `responder_tablas` y `Partida.acordar_tablas`.
- **Partida vs Magnus**: "¡Sos blancas!", el tiempo, el recuadro con la fase ("Tu turno",
  "Magnus está pensando…", "Magnus: caballo g8→f6 / Movelo y apretá un botón") y
  "¿Rendirse?". Sin tablas contra Magnus (decisión de Tino).
- **Sin "Volver" durante la partida**, y **"¿Rendirse?" pide confirmación** ("Sí, me rindo" /
  "No"): con el touch impreciso es fácil tocar sin querer.
- **Fin**: el motivo ("¡Jaque mate!" / "Ganan negras", "Tablas por acuerdo", "Blancas se
  rindieron", "Tablas: ahogado"…) o, contra Magnus, la jugada final y "Aguantaste 01:23
  contra Magnus"; botón "Menú principal". Si Magnus dio mate, su jugada sigue en los LEDs.
- **Error**: si el Nano no está o se corta, "Problema con el tablero" con el mensaje de qué
  revisar y "Menú principal"; la partida queda abandonada en el registro. Si falta
  Stockfish, el mismo aviso al elegir el color contra Magnus.

## Arquitectura

| Pieza | Qué hace |
|---|---|
| `logica/sesion.py` | `SesionPvP` y `SesionMagnus`: una partida de punta a punta sin bloquear. Fases `PREPARANDO`, `CUENTA_REGRESIVA` (PvP), `JUGANDO`, `TERMINADA`. `actualizar()` lee la fuente, avanza el reloj, mira si Magnus contestó (corre el motor en su propio hilo) y pinta los LEDs si cambiaron; devuelve si hay que redibujar. Sin hardware: testeada en `tests/test_sesion.py` |
| `io/menus.py` | Las pantallas. Dibuja lo que expone la sesión y le pasa toques y botones. Recibe el hardware en un `Hardware` (`crear_fuente`, `pintar`, `crear_motor`): **no importa** GPIO, el Nano ni los LEDs |
| `io/menus_gpio.py` | En la Pi: arma el `Hardware` real (matriz del Nano, tira de LEDs con los colores de `juego.py`, botones GPIO como `EVENTO_BOTON_RELOJ`, Stockfish) y se relanza con `sudo` |
| `logica/tablero_simulado.py` | En la notebook: la fuente de ocupación manejada desde la terminal |

**Un solo hilo toca la lógica**: el loop de pygame. Los botones GPIO llegan como eventos de
pygame (los publica el hilo de `rpi-lgpio`), Stockfish corre en el hilo de la sesión y, en la
notebook, un hilo lee la terminal y encola comandos en el tablero simulado.

**Redibujado**: solo ante un toque o botón, o cuando `actualizar()` avisa un cambio visible
(la sesión compara una "firma" de lo que se ve, que incluye los segundos del reloj, así que
durante la partida es una vez por segundo). Llamar a `pygame.display.flip()` en cada vuelta
del loop deja en blanco la pantalla con el backend KMSDRM de la Raspberry (confirmado por
Tino el 2026-08-13; no pasa en modo ventana).

**Por qué dos archivos** (`menus.py` y `menus_gpio.py`, pedido de Tino del 2026-08-13): la
versión de la notebook (teclado, tablero simulado) es la única que se puede probar sin la Pi;
si conviviera con la de GPIO en la misma función, tocar una podría romper la otra sin que se
note.

**Fuentes**: los textos usan DejaVu Sans (`pygame.font.match_font("dejavusans")`) porque
traen "→", "½" y "…"; la fuente por defecto de pygame no los tiene. Si DejaVu no está, cae
en la de pygame.

## Cómo probarlo

**En la notebook**, con el tablero simulado:

```bash
cd tablero
env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus
```

Se clickea con el mouse; en la terminal se tipean las jugadas (`e2e4`, también capturas;
`-e4` levanta, `+e4` apoya, `inicial` vuelve a la posición inicial; el enroque son dos:
`e1g1` y `h1f1`), y ← / → son los botones del reloj de blancas y negras. Los LEDs que se
prenderían se loguean. Contra Magnus usa el Stockfish de la notebook.

**En la Pi**: `uv run python -m tablero.io.menus_gpio` (ver
[`pendiente-pi.md`](./pendiente-pi.md#32-jugar-desde-la-pantalla)).

## Modo ventana: el backend de SDL

El forzado de `SDL_VIDEODRIVER=kmsdrm`/`SDL_NOMOUSE=1` vive centralizado en
`io/_sdl.py` (`configurar_entorno_sdl()`), que llaman los tres módulos de `io/` que usan
`pygame` (`pantalla.py`, `calibracion_touch.py`, `menus.py`) antes de su propio
`import pygame`:

```python
def configurar_entorno_sdl() -> None:
    if os.environ.get("TABLERO_PANTALLA_VENTANA") == "1":
        if sys.platform.startswith("linux"):
            os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
        return
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    os.environ.setdefault("SDL_NOMOUSE", "1")
```

**Por qué `wayland` en modo ventana (solo en Linux):** la primera versión de este toggle
forzaba `x11` (vía XWayland), asumiendo que era la opción más compatible en un escritorio
Linux con Wayland. En niri (el compositor de Tino, CachyOS) eso da una ventana completamente
negra — niri no soporta Xwayland de forma nativa (corre `xwayland-satellite` aparte) y su
propia documentación marca las ventanas Xwayland como negras por defecto (hay que forzarlas
a floating/fullscreen para verlas), sin relación con `pygame`. El backend `wayland` nativo
de SDL2 no pasa por Xwayland y renderiza bien. Es un `setdefault`, así que si hace falta otro
backend (por ejemplo `x11` en un escritorio sin soporte Wayland nativo en SDL2) alcanza con
exportar `SDL_VIDEODRIVER` antes de correr el script.

El `if sys.platform.startswith("linux")` se agregó en sesión 2026-08-26: sin él, correr en
modo ventana en Windows fallaba con `pygame.error: wayland not available` (SDL ahí no tiene
ese backend). En Windows/macOS no hace falta tocar `SDL_VIDEODRIVER` — SDL ya elige el
backend nativo correcto (`windows`, `cocoa`) por su cuenta.

Nota para correr en niri: además de esto, hace falta una window-rule en la config de niri
para que la ventana de `pygame` abra en modo floating (si no, el tiling la deja con un
tamaño distinto al fijo de 480×320 que pide el panel).

**Por qué está centralizado y no duplicado en cada archivo** (como estaba al principio):
`menus.py` importa `calibracion_touch` para reusar `cargar_calibracion`/
`aplicar_transformacion`. La primera versión de este toggle solo estaba en `menus.py`, y
`calibracion_touch.py` seguía forzando `kmsdrm` sin condición — como el `import` de
`calibracion_touch` corre antes de que `menus.py` inicialice `pygame`, ese forzado
incondicional terminaba pisando el modo ventana igual. Alcanza con que un solo módulo
importado en la cadena fuerce el driver para romper el toggle en todos, así que ahora los
tres llaman a la misma función.

Con `TABLERO_PANTALLA_VENTANA=1`, `pygame` no busca el dispositivo DRM del panel: abre una
ventana normal de escritorio de 480×320 y el mouse queda habilitado. El loop de eventos ya
manejaba `MOUSEBUTTONDOWN` igual que `FINGERDOWN` (mismo patrón que `probar_boton()` en
`pantalla.py`), así que la navegación se prueba con clicks normales. La calibración táctil
(`calibracion_touch.cargar_calibracion`) simplemente no encuentra
`config.CALIBRACION_TOUCH_PATH` en una máquina que no sea la Raspberry y devuelve `None`
— correcto acá, un mouse en una ventana normal no necesita corrección de coordenadas.

Sin la variable de entorno, el comportamiento es exactamente el de siempre (piensa que
corre contra el panel físico) — para los tres módulos, no solo `menus.py`: si en algún
momento hace falta correr `pantalla.py` o `calibracion_touch.py` en una ventana (por
ejemplo para revisar el layout de `probar_boton()` sin la Raspberry), la misma variable de
entorno ya funciona ahí también.

En modo ventana, `boton_1`/`boton_2` del reloj se simulan con las teclas ← / → (ver más
abajo) — no hace falta hardware ni `io/sensores.py` para probar el flujo completo del
reloj PvP en notebook.

