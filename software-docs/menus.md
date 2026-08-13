# `io/menus.py`

Interfaz gráfica de navegación entre pantallas: implementa los 6 bocetos de
[`diseño-docs/diseño-interfaz.md`](../diseño-docs/diseño-interfaz.md) (menú principal,
selectores de tiempo/dificultad/color, e interfaz de juego PvP/vs-Magnus), con cada botón
tocado logueado y un botón "Volver" para retroceder.

## Alcance actual

`juego_pvp` tiene reloj real (ver "Reloj PvP" más abajo): cuenta regresiva al iniciar, dos
temporizadores independientes, cambio de turno al presionar boton_1/boton_2, y mensaje de
fin de partida cuando alguno se queda sin tiempo. `juego_vs_magnus` sigue **estática**: el
reloj siempre muestra `04:53` y los indicadores "¡Es tu turno!"/"¡Te quedaste sin tiempo!"
están siempre presentes en gris (en el boceto original solo aparecen "según necesidad") —
sin conexión con `logica/estado_tablero.py` todavía, eso es integración futura. El único
botón interactivo de esa pantalla es "¿Rendirse?", que loguea el input y vuelve al menú
principal (`juego_pvp` también lo tiene, funciona igual incluso después de que termine la
partida por tiempo).

La excepción estática restante es el color del jugador humano en `juego_vs_magnus`: al
tocar "Blancas"/"Aleatorio"/"Negras" en `selector_color`, `EleccionColor` se resuelve a un
`chess.Color` real (`_resolver_color()` — "Aleatorio" usa `random.choice`) y se guarda en
`EstadoPartida.color_humano`, una instancia que vive en `ejecutar_menus()` y se comparte
con las pantallas vía `functools.partial` (mismo patrón que usa `_dibujar_pantalla_seleccion`
para título/subtítulo/pregunta). `juego_vs_magnus` lee ese estado para mostrar "¡Sos
blancas!" o "¡Sos negras!" en vez de un texto fijo, y cada asignación de color queda
logueada (`Color asignado: jugador humano ..., máquina ...`) además del log genérico de
input de cada botón.

## Reloj PvP

Campos de `EstadoPartida` para el reloj (además de `color_humano`, que es para vs-Magnus):

| Campo | Qué es |
|---|---|
| `tiempo_restante_blancas` / `_negras` | Segundos restantes de cada lado (float, se decrementa en tiempo real). |
| `turno_blancas` | De quién es el turno mientras se juega. Una vez `tiempo_agotado=True` queda "congelado" en el lado que perdió — así identifica a la vez "de quién es el turno" y "quién se quedó sin tiempo" sin un campo separado. |
| `reloj_corriendo` | `False` durante la cuenta regresiva y después de que alguien se queda sin tiempo; `True` mientras se juega. |
| `tiempo_agotado` | Se pone en `True` cuando algún reloj llega a 0; dispara el mensaje de fin de partida y congela ambos relojes. |
| `entrada_pantalla_ts` | `time.monotonic()` de cuándo se entró a la pantalla actual — lo usa la cuenta regresiva para saber cuánto pasó. |

Al elegir duración en `selector_tiempo` (3/5/10 min) se setean `tiempo_restante_blancas`/
`_negras` de una y se navega a `cuenta_regresiva` (no directo a `juego_pvp`). Esa pantalla
no tiene botones ni permite Volver: `_dibujar_cuenta_regresiva()` calcula cuántos segundos
pasaron desde `entrada_pantalla_ts` y muestra "3"/"2"/"1"/"¡Partida iniciada!" (un segundo
cada uno, `_TEXTOS_CUENTA_REGRESIVA`); el loop principal de `ejecutar_menus()` la saca de
ahí automáticamente por tiempo (no por click) una vez pasan los 4 segundos, seteando
`turno_blancas=True`, `reloj_corriendo=True` y navegando a `juego_pvp`.

Mientras `reloj_corriendo`, cada vuelta del loop resta `dt` (el tiempo real transcurrido
desde la vuelta anterior) al lado activo. Al llegar a 0: `reloj_corriendo=False`,
`tiempo_agotado=True`, y `_dibujar_juego_pvp()` reemplaza toda la fila de
encabezados/indicadores por el mensaje combinado "¡Blancas se quedó sin tiempo! Gana
Negras" (o el caso inverso) en dos líneas — no alcanza el espacio del indicador chico de
"¡Te quedaste sin tiempo!" para meter también "gana X" sin superponerse con el otro lado.
Los relojes quedan congelados con su último valor, visibles debajo del mensaje.

**Por qué `_renderizar()` no se llama en cada vuelta del loop incondicionalmente:** la
lógica de tiempo (`dt`, avance de la cuenta regresiva, decremento del reloj activo) sí
corre en cada vuelta, pero el `pygame.display.flip()` de `_renderizar()` solo se dispara si
hubo algún evento real (click/touch/tecla/GPIO) o si la pantalla actual es "viva"
(`cuenta_regresiva`, o `juego_pvp` con `reloj_corriendo=True`) — las demás pantallas
(menús, selectores, `juego_vs_magnus`, `juego_pvp` ya terminado) vuelven al comportamiento
original de redibujar solo ante un evento. Llamar a `flip()` sin parar (~50/s) contra el
backend `kmsdrm` de la Raspberry deja la pantalla en blanco (no pasa con el backend de
ventana/escritorio) — confirmado por Tino en hardware real (2026-08-13): con el redibujado
sin gatear, ni siquiera `menu_principal` (pantalla sin ningún código nuevo de esta feature)
llegaba a mostrarse.

Los botones físicos se traducen a `boton_1`/`boton_2` y se procesan en
`_procesar_boton_reloj()`: solo tienen efecto si `pantalla_actual == juego_pvp`,
`reloj_corriendo` y es el turno de ese lado — igual que un reloj de ajedrez real, un jugador
solo puede parar su propio reloj, no el del rival.

## Grafo de navegación

```
menu_principal (raíz, sin botón "Volver")
 ├─ "Jugar contra un Amigo" → selector_tiempo
 │                              ├─ "3 minutos" / "5 minutos" / "10 minutos" → cuenta_regresiva
 │                              │                                              └─ (auto, ~4s) → juego_pvp
 │                              └─ Volver → menu_principal
 └─ "Jugar contra Magnus" → selector_dificultad
                              ├─ "Fácil" / "Medio" / "Difícil" → selector_color
                              │    ├─ "Blancas" / "Aleatorio" / "Negras" → juego_vs_magnus
                              │    └─ Volver → selector_dificultad
                              └─ Volver → menu_principal

cuenta_regresiva: sin botones, sin Volver — auto-avanza a juego_pvp por tiempo, no por click
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

En modo ventana, `boton_1`/`boton_2` del reloj se simulan con las teclas ← / → (ver más
abajo) — no hace falta hardware ni `io/sensores.py` para probar el flujo completo del
reloj PvP en notebook.

## Modo hardware real (Raspberry con botones GPIO)

`io/menus.py::ejecutar_menus()` no sabe de dónde vienen los eventos de "se presionó
boton_1/boton_2": siempre escucha las teclas ←/→ (inofensivo en la Raspberry, que
normalmente no tiene teclado conectado) y siempre escucha un evento custom de pygame,
`EVENTO_BOTON_RELOJ = pygame.USEREVENT + 1`, sin importar quién lo publique. Este archivo
**no importa `io/sensores.py` ni sabe nada de GPIO**, a propósito.

`io/menus_gpio.py` (archivo nuevo, separado) es el driver de hardware real: importa
`menus` y `sensores`, llama a `sensores.configurar_botones_reloj()` para que cada presión
física publique `EVENTO_BOTON_RELOJ` (vía `pygame.event.post`, desde el callback que corre
en el thread interno de `rpi-lgpio`), y después llama a `menus.ejecutar_menus()` sin
modificarlo.

**Por qué está separado en dos archivos** (pedido explícito de Tino, 2026-08-13): antes de
esto, la idea era un solo `if`/`else` según `TABLERO_PANTALLA_VENTANA` dentro del mismo
loop para elegir entre teclado y GPIO. El problema: tocar la rama de teclado (que es la
única que se puede probar en notebook) puede romper sin darse cuenta la rama de GPIO real
(que solo se prueba por SSH en la Raspberry), porque conviven en la misma función. Con el
split, `io/menus.py` y `io/menus_gpio.py` son independientes — solo comparten
`menus.ejecutar_menus()` y `menus.EVENTO_BOTON_RELOJ`, nada de la lógica de teclado ni de
GPIO se toca entre sí.

## Cómo probarlo

**Test en notebook, sin la Raspberry** (para iterar el diseño visual y el flujo del reloj
con teclado):

```bash
cd tablero
env TABLERO_PANTALLA_VENTANA=1 uv run python -m tablero.io.menus
```

**Test en hardware real, por SSH en la Raspberry**, con el overlay de pantalla activado y
los botones del reloj cableados (para probar con el panel táctil, el touch real —
idealmente ya calibrado, ver [`pantalla.md`](./pantalla.md#calibración-del-touch)— y los
botones físicos):

```bash
cd tablero
uv run python -m tablero.io.menus_gpio
```

(`uv run python -m tablero.io.menus` directo en la Raspberry sigue funcionando para
navegación por touch, pero sin los botones físicos del reloj conectados — solo tiene
sentido si además hay un teclado conectado para simular boton_1/boton_2.)

En todos los casos, cada botón tocado/clickeado/presionado se loguea por consola
(`logging`, nivel INFO) con el texto del botón, la pantalla de origen y la de destino;
corre hasta `Ctrl+C`.
