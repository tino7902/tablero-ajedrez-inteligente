# `io/menus.py`

Interfaz gráfica de navegación entre pantallas: implementa los 6 bocetos de
[`diseño-docs/diseño-interfaz.md`](../diseño-docs/diseño-interfaz.md) (menú principal,
selectores de tiempo/dificultad/color, e interfaz de juego PvP/vs-Magnus), con cada botón
tocado logueado y un botón "Volver" para retroceder.

## Alcance actual

Solo la parte gráfica de navegación. Las dos pantallas de "Interfaz de Juego" (PvP y
vs-Magnus) se dibujan **estáticas**: el reloj siempre muestra `04:53` y los indicadores
"¡Es tu turno!"/"¡Te quedaste sin tiempo!" están siempre presentes en gris (en el boceto
original solo aparecen "según necesidad"). No hay lógica real de turnos, tiempo, ni
conexión con `logica/estado_tablero.py` todavía — eso es una integración futura. El único
botón interactivo de esas dos pantallas es "¿Rendirse?", que loguea el input y vuelve al
menú principal.

La excepción es el color del jugador humano en `juego_vs_magnus`: al tocar "Blancas"/
"Aleatorio"/"Negras" en `selector_color`, `EleccionColor` se resuelve a un `chess.Color`
real (`_resolver_color()` — "Aleatorio" usa `random.choice`) y se guarda en
`EstadoPartida.color_humano`, una instancia que vive en `ejecutar_menus()` y se comparte
con las pantallas vía `functools.partial` (mismo patrón que usa `_dibujar_pantalla_seleccion`
para título/subtítulo/pregunta). `juego_vs_magnus` lee ese estado para mostrar "¡Sos
blancas!" o "¡Sos negras!" en vez de un texto fijo, y cada asignación de color queda
logueada (`Color asignado: jugador humano ..., máquina ...`) además del log genérico de
input de cada botón.

## Grafo de navegación

```
menu_principal (raíz, sin botón "Volver")
 ├─ "Jugar contra un Amigo" → selector_tiempo
 │                              ├─ "3 minutos" / "5 minutos" / "10 minutos" → juego_pvp
 │                              └─ Volver → menu_principal
 └─ "Jugar contra Magnus" → selector_dificultad
                              ├─ "Fácil" / "Medio" / "Difícil" → selector_color
                              │    ├─ "Blancas" / "Aleatorio" / "Negras" → juego_vs_magnus
                              │    └─ Volver → selector_dificultad
                              └─ Volver → menu_principal

juego_pvp:        "¿Rendirse?" (uno por lado) → menu_principal · Volver → selector_tiempo
juego_vs_magnus:  "¿Rendirse?" → menu_principal · Volver → selector_color
```

"Volver" no tiene un destino fijo por pantalla: hace `pop()` sobre un historial de
navegación (`list[str]` de nombres de pantalla), así que automáticamente vuelve a la
pantalla desde la que se llegó — no hace falta codificar el destino de "Volver" a mano
para cada pantalla, el `pop()` ya da el resultado correcto en todos los casos del grafo de
arriba. La única excepción es "¿Rendirse?": en vez de *empujar* una pantalla más al
historial, lo **reinicia** a `[menu_principal]`, porque rendirse termina la partida en vez
de ser un paso más de configuración.

## Estructuras de datos

```python
@dataclass(frozen=True)
class Boton:
    texto: str
    rect: pygame.Rect
    destino: str  # nombre de la pantalla a la que navega al tocarlo

@dataclass(frozen=True)
class Pantalla:
    nombre: str
    dibujar: Callable[[pygame.Surface, "Pantalla"], None]
    botones: list[Boton]
    permite_volver: bool = True
```

`_construir_pantallas()` arma las 6 `Pantalla` y las devuelve en un `dict[str, Pantalla]`
indexado por nombre. Las 4 pantallas de selección (menú principal, tiempo, dificultad,
color) comparten la misma composición visual — título, subtítulo, pregunta, fila de
botones — a través de `_dibujar_pantalla_seleccion` (parametrizada con `functools.partial`
para el texto de cada una) y del helper `_fila_de_botones(cantidad, y)`, que centra N
rects del mismo tamaño horizontalmente. Las dos pantallas de juego tienen layout propio
(`_dibujar_juego_pvp`, `_dibujar_juego_vs_magnus`) porque no encajan en ese esquema de
"título + botones en fila".

El botón "Volver" y el pie de página ("Desarrollado por CDR-FPUNA 2026") no forman parte
de las funciones `dibujar` de cada pantalla — se dibujan una sola vez, centralizados en
`_renderizar()`, para no repetir ese código en las 6 pantallas.

## Modo ventana (testear sin la Raspberry)

El forzado de `SDL_VIDEODRIVER=kmsdrm`/`SDL_NOMOUSE=1` vive centralizado en
`io/_sdl.py` (`configurar_entorno_sdl()`), que llaman los tres módulos de `io/` que usan
`pygame` (`pantalla.py`, `calibracion_touch.py`, `menus.py`) antes de su propio
`import pygame`:

```python
def configurar_entorno_sdl() -> None:
    if os.environ.get("TABLERO_PANTALLA_VENTANA") == "1":
        os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
        return
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    os.environ.setdefault("SDL_NOMOUSE", "1")
```

**Por qué `wayland` en modo ventana:** la primera versión de este toggle forzaba `x11`
(vía XWayland), asumiendo que era la opción más compatible en un escritorio Linux con
Wayland. En niri (el compositor de Tino, CachyOS) eso da una ventana completamente negra
— niri no soporta Xwayland de forma nativa (corre `xwayland-satellite` aparte) y su propia
documentación marca las ventanas Xwayland como negras por defecto (hay que forzarlas a
floating/fullscreen para verlas), sin relación con `pygame`. El backend `wayland` nativo de
SDL2 no pasa por Xwayland y renderiza bien. Es un `setdefault`, así que si hace falta otro
backend (por ejemplo `x11` en un escritorio sin soporte Wayland nativo en SDL2) alcanza con
exportar `SDL_VIDEODRIVER` antes de correr el script.

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

## Cómo probarlo

**En una máquina de escritorio, sin la Raspberry** (para iterar el diseño visual):

```bash
cd tablero
env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus
```

**Por SSH, en la Raspberry, con el overlay activado** (para probar con el panel y el touch
real, idealmente ya calibrado — ver [`pantalla.md`](./pantalla.md#calibración-del-touch)):

```bash
cd tablero
uv run python -m tablero.io.menus
```

En ambos casos, cada botón tocado/clickeado se loguea por consola (`logging`, nivel INFO)
con el texto del botón, la pantalla de origen y la de destino; corre hasta `Ctrl+C`.
