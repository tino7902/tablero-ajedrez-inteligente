# `io/sensores.py`

Entradas digitales del tablero: los dos botones físicos del reloj de ajedrez (interruptores fin
de carrera / limit switches, ver `hardware-docs/componentes.md`) y la matriz de ocupación de
casillas, con **64 sensores Hall A3144** que barre un **Arduino Nano**. La Pi le pide cada
lectura por USB serie. Los botones están verificados en hardware. **La matriz funciona de punta
a punta en la Pi** (2026-10-18): `CASILLA_DE_CELDA_HALL` ya está generado con `mapear`, y
`prueba_tablero recorrido` y `espejo` pasan con los LEDs. Falta `calibrar`, que necesita las 32
piezas: hasta entonces `HALL_ESPERA_ENCENDIDO` y `HALL_LECTURAS_ESTABLES` son los valores por
defecto, que alcanzaron para todas las pruebas.

La matriz empezó con reed switches. Esa versión se conserva en `io/sensores_reed.py`, ver
[`sensores-reed.md`](./sensores-reed.md); la de Hall es la actual y la que se usa por defecto.

La v2 de la matriz (la Pi barriendo un 74HC138 + 74HC165 por GPIO) se descartó el 2026-10-17:
el 138 no aguanta la corriente de los Hall. Por qué y qué se probó, en
`hardware-docs/historial-deteccion.md`; su driver GPIO quedó en la historia de git (el
`io/matriz.py` anterior al commit que lo pasó al puerto serie).

## Por qué existe este módulo

Es el punto de entrada de GPIO real del proyecto (primera vez que se usa `rpi-lgpio` en este
repo). Aísla al resto del código de los detalles de `RPi.GPIO`/`rpi-lgpio`: quien lo use solo
necesita reaccionar a "se presionó boton_1/boton_2", no a pines ni flancos. Hoy lo consume
`io/menus_gpio.py`, que traduce cada presión a un evento de `pygame` para el reloj PvP real de
`io/menus.py` (ver `software-docs/menus.md`).

## API

| Función | Qué hace |
|---|---|
| `configurar_botones_reloj(callback)` | Configura GPIO y llama a `callback('boton_1' \| 'boton_2')` en cada presión (flanco descendente, debounce nativo). El callback corre en el thread interno de `rpi-lgpio`. API principal, reusable — la usa `io/menus_gpio.py`. |
| `liberar_botones_reloj()` | Quita la detección de eventos y hace `GPIO.cleanup()` **solo de los pines de los botones**, para no desarmar la matriz si está en uso. Llamar al terminar. |
| `probar_botones_reloj()` | Test manual standalone construido sobre `configurar_botones_reloj()`: loguea cada presión, corre hasta `Ctrl+C`. No implementa lógica de reloj (tiempo, turnos) — eso vive en `io/menus.py`. |

## Pines (ver `config.py` / `hardware-docs/componentes.md`)

| Constante | Pin físico (BOARD) | GPIO (BCM) | Botón |
|---|---|---|---|
| `PIN_BOTON_RELOJ_JUGADOR_1` | 33 | 13 | boton_1 |
| `PIN_BOTON_RELOJ_JUGADOR_2` | 35 | 19 | boton_2 |

## Decisiones de diseño

- **Activo en bajo (`GPIO.FALLING`) + pull-up interno del SoC (`GPIO.PUD_UP`)**: cada botón
  conecta el pin directo a un GND dedicado al presionarse, así que reposo = HIGH, presionado =
  LOW. `hardware-docs/componentes.md` documenta resistencias externas "Configuradas como
  Pull-down (o Pull-up) a 3.3V" — texto ambiguo sobre cuál de las dos es la real. Habilitar
  también el pull-up interno del SoC por software resuelve la ambigüedad sin tener que verificar
  el armado físico: es compatible con un pull-up externo (ambos tiran a HIGH en reposo) y, si el
  externo terminó siendo un pull-down mal pensado o está mal armado, un botón que conecta directo
  a GND al presionarse siempre gana contra cualquier resistencia débil de pull-up (interna o
  externa) — el circuito queda activo-en-bajo de cualquier manera.
- **`GPIO.BOARD`, no `GPIO.BCM`**: `hardware-docs/componentes.md` documenta los pines por número
  físico (33, 35), que es como Tino los cableó y los referencia. Usar `BOARD` en el código evita
  tener que traducir mentalmente a BCM (13, 19) cada vez que se lee el código junto al hardware
  físico o la hoja de pines de la Raspberry.
- **`GPIO.add_event_detect` + `bouncetime`, no polling manual**: `rpi-lgpio` expone la API clásica
  de `RPi.GPIO` (incluida detección de eventos por interrupción con debounce nativo) sobre el
  driver moderno `lgpio`/`gpiod` — es la vía soportada, no hay necesidad de reinventar debounce a
  mano como en `io/pantalla.py::probar_boton()` (ahí se justifica el polling porque el objetivo
  era inspeccionar el evento crudo de `pygame`; acá no hace falta). `bouncetime=200` (ms) es un
  valor de arranque para un limit switch mecánico; si en la prueba real se ven rebotes (mismo
  botón logueado varias veces por una sola presión) o pulsaciones perdidas, es el primer parámetro
  a ajustar.
- **Riesgo conocido, no resuelto de antemano**: es el primer código GPIO real de este repo con
  `rpi-lgpio`. Si `add_event_detect` no dispara o tira una excepción en hardware real, la
  alternativa es un loop de polling manual (`GPIO.input(pin)` cada ~20ms con debounce a mano),
  igual al patrón de `pantalla.py`. No se implementa de entrada porque no hay evidencia de que
  haga falta.

## Matriz de casillas (sensores Hall)

### Cómo está armada

Cada Hall tiene Vcc al 5 V del Nano, **GND → diodo → bus de su fila** y su salida
(open-collector) directo a la columna, que es un pin del Nano con su pull-up interna. Cada fila
tiene un NPN que maneja el Nano (D2–D9) y que conecta el bus a GND: **solo los Hall de la fila
encendida tienen alimentación**. Un Hall encendido con el polo sur de un imán encima baja la
columna, y el Nano la lee como pieza presente. El Nano enciende las filas de a una, espera a que
los Hall arranquen, lee las 8 columnas y le contesta la matriz a la Pi. Cableado, celdas y
transistores en `hardware-docs/matriz-hall-nano.md`; firmware y protocolo en
[`firmware-nano.md`](./firmware-nano.md).

Para el software eso implica tres cosas:

- **Hay que esperar a que el Hall encienda** después de encender cada fila, antes de leer. La
  espera la hace el Nano: la Pi se la manda en cada barrido (`L <µs>`). Ese tiempo se mide con
  `calibrar`.
- **Polaridad**: el A3144 solo reacciona al polo sur. Una pieza con el imán al revés no se ve.
- **Fallas eléctricas**: que el NPN se sature, la tensión de los Hall (el diodo del GND le quita
  ~0,7 V) y el nivel de la columna con pieza. Se diagnostican con `medir`.

### Archivos

| Archivo | Qué tiene |
|---|---|
| `io/matriz.py` | Driver común a las dos versiones de sensor: el diálogo con el Nano por el puerto serie, `LectorMatriz` con antirrebote y la vista en vivo |
| `io/sensores.py` | La versión Hall: espera y antirrebote de los Hall, mapeo de 64 y los comandos `medir`, `matriz`, `calibrar`, `mapear` |
| `io/sensores_reed.py` | La versión reed, la anterior (ver [`sensores-reed.md`](./sensores-reed.md)) |
| `logica/matriz.py` | Lo que no necesita el hardware: validación de la tabla, celda → casilla, las cuentas de `calibrar` y el texto del protocolo del Nano (armar comandos, decodificar respuestas). Testeado en `tests/test_matriz.py` |
| `io/prueba_tablero.py` | Sensores y LEDs juntos (asociar LEDs, recorrido, espejo), ver [`prueba-tablero.md`](./prueba-tablero.md) |
| `firmware/matriz-nano/matriz-nano.ino` | El firmware del Nano, ver [`firmware-nano.md`](./firmware-nano.md) |

### API

| Función/clase | Dónde | Qué hace |
|---|---|---|
| `configurar_matriz()` | `io/matriz.py`, reexportado en `io/sensores.py` | Abre el puerto del Nano (`NANO_PUERTO` o autodetectado) y espera su `LISTO matriz-nano 1` (~2 s, porque abrir el puerto lo resetea) |
| `liberar_matriz()` | ídem | Apaga las filas (`X`) y cierra el puerto. No falla si el Nano ya no está |
| `leer_matriz(espera)` | `io/matriz.py` | Un barrido completo (`L <µs>`), sin antirrebote: `MatrizCruda`, `matriz[fila Fk][columna Ck]`, `True` = sensor activo. El Nano espera `espera` segundos (máximo 50 ms) en cada fila antes de leer |
| `elegir_fila(k)` / `leer_columnas()` / `leer_analogico()` / `apagar_filas()` | `io/matriz.py` | Los comandos `F k` / `C` / `A` / `X` del Nano, para `medir` |
| `ErrorNano` | `io/matriz.py` | Lo que tira todo lo anterior si el Nano no está, no se puede abrir el puerto o no contesta el protocolo; el mensaje dice qué revisar |
| `LectorMatriz(espera, lecturas_estables)` | `io/sensores.py` | Antirrebote: `.leer()` devuelve la matriz solo cuando se repitió N veces seguidas **y** cambió respecto de la última estable; si no, `None`. `.reiniciar()` olvida lo leído; `.esperar_estable()` reinicia y espera la próxima. Por defecto usa `HALL_ESPERA_ENCENDIDO` y `HALL_LECTURAS_ESTABLES` |
| `casilla_de(fila, columna)` | `io/sensores.py` | Celda cruda → `chess.Square`, según `CASILLA_DE_CELDA_HALL` |
| `ocupacion(matriz)` | `io/sensores.py` | Matriz cruda → `frozenset[chess.Square]`, la `Ocupacion` que espera `logica/eventos.py` |
| `medir(objetivo)` / `probar_matriz()` / `calibrar()` / `mapear()` | `io/sensores.py` | CLI `medir` / `matriz` / `calibrar` / `mapear`, ver "Cómo probarlo" |

`io/sensores_reed.py` tiene la misma API (`LectorMatriz`, `configurar_matriz`, `liberar_matriz`,
`casilla_de`, `ocupacion`): la partida en el tablero físico (`io/juego.py`, ver
[`juego.md`](./juego.md)) puede volver a los reed cambiando solo el import.

### Configuración (`config.py`)

| Constante | Valor por defecto | Lo genera |
|---|---|---|
| `NANO_PUERTO` | `None`: autodetectar (el único `/dev/ttyUSB*` o `/dev/ttyACM*`) | A mano, solo si hay varios puertos serie |
| `HALL_ESPERA_ENCENDIDO` | `0.001` (1 ms por fila, generoso; sin calibrar todavía) | `calibrar` |
| `HALL_LECTURAS_ESTABLES` | `3` (sin calibrar todavía) | `calibrar` |
| `CASILLA_DE_CELDA_HALL` | Generado el 2026-10-18: grilla, F0 = fila 8 … F7 = fila 1, C0..C7 = columnas a..h | `mapear` |

Los clones del Nano con CH340 aparecen como `/dev/ttyUSB0`; otros, como `/dev/ttyACM0`. Si hay más
de un puerto serie, poner en `NANO_PUERTO` el del Nano, mejor con su nombre de
`/dev/serial/by-id/` (`ls -l /dev/serial/by-id/`), que no cambia entre reinicios ni según el
orden en que se enchufan las cosas.

### Decisiones de diseño

- **Un driver común para las dos versiones** (`io/matriz.py`): el Nano barre igual cualquier
  sensor que baje su columna cuando la fila está encendida, sea un Hall o un reed con su diodo.
  Cada versión solo pone su espera por fila, su antirrebote y su mapeo.
- **El Nano solo barre; todo lo demás sigue en Python** (antirrebote, calibración, mapeo). Por qué,
  en "Por qué un Nano tonto" de [`firmware-nano.md`](./firmware-nano.md).
- **La misma API que el driver GPIO de la v2**: `configurar_matriz`, `liberar_matriz`,
  `leer_matriz(espera)` y `LectorMatriz` se usan igual, así que `calibrar`, `mapear`,
  `prueba_tablero` y la versión reed no cambiaron. Por eso el puerto abierto es estado del módulo
  (`_puerto`) y no un objeto que haya que pasar.
- **El protocolo, en `logica/matriz.py`**: armar `L <µs>` y decodificar `M …`, `C …`, `A …` y el
  `LISTO` son funciones puras, testeadas en la notebook. `io/matriz.py` solo escribe y lee el
  puerto. Una línea mal formada nunca llega como matriz: el decodificador tira `ValueError`,
  `io/matriz.py` repite el comando (3 intentos) y después tira `ErrorNano`.
- **Arranque**: abrir el puerto resetea el Nano (DTR del USB) y con el reset entra basura. Se
  descarta todo hasta una línea igual a `LISTO matriz-nano 1`, con 3 s de plazo; si no llega
  (un Nano que no se resetea al abrir el puerto), se le manda `?` y se espera 1 s más. Un `LISTO`
  con otra versión de protocolo es un error: hay que subir el firmware del repo.
- **Puerto exclusivo** (`exclusive=True`): si otra prueba ya tiene el puerto abierto, la segunda
  falla al abrirlo en vez de robarle respuestas a la primera. El monitor de `arduino-cli` lo
  bloquea por su lado, con el mismo efecto.
- **Errores con qué revisar**: puerto que no existe, falta de permiso (grupo `dialout`), puerto
  ocupado, Nano que no contesta, USB desenchufado en medio de una lectura. Todos llegan como
  `ErrorNano` con un mensaje que dice qué mirar, y los CLI (`sensores`, `sensores_reed`,
  `prueba_tablero`) lo muestran en una línea, sin traceback. Nada se cuelga esperando: cada
  respuesta tiene plazo (0,3 s más lo que tarda el barrido).
- **Espera de encendido medida, no supuesta**: cuánto tarda un Hall en dar una salida válida
  después de recibir alimentación depende del modelo y del clon, y con la fila cargada puede ser
  más. `calibrar` la mide contra una referencia tomada con 5 ms y recomienda el doble de la
  mínima que anduvo. La espera la hace el Nano con resolución de microsegundos, así que no hace
  falta la espera activa que necesitaba la v2 (`time.sleep` en la Pi duerme bastante más de lo
  pedido).
- **Tabla de 64, no dos permutaciones como los reed**: `CASILLA_DE_CELDA_HALL[f][c]` es el nombre
  de la casilla de cada sensor. Si algún Hall quedó cableado fuera de la grilla, la tabla lo
  absorbe. Además, `mapear` pide las 64 casillas, así que de paso prueba que cada Hall detecte. Se
  guardan nombres (`"e4"`) y no números para poder revisar la grilla a simple vista en
  `config.py`.
- **Validación perezosa de la tabla**: `io/sensores.py` también tiene los botones del reloj, que
  usa `io/menus_gpio.py`. Si la tabla se validara al importar, un `CASILLA_DE_CELDA_HALL` mal
  pegado rompería el reloj. Se valida la primera vez que se usa la matriz, con un error que dice
  qué celda está mal. `tests/test_matriz.py` además valida la tabla de `config.py` en la notebook.
- **Antirrebote por repetición** (`HALL_LECTURAS_ESTABLES`): el Hall no rebota como un contacto
  mecánico, pero la mano pasando sobre el tablero, un imán en el borde de la casilla o un nivel
  eléctrico al límite generan parpadeos. `calibrar` mide la racha más larga de lecturas falsas
  iguales (lo que el antirrebote dejaría pasar) y recomienda esa racha + 2, con un mínimo de 3.
- **Etiquetas F/C**: lo que se imprime (y los comentarios de `config.py`) usa los nombres de cable
  de `hardware-docs/matriz-hall-nano.md`, fila **Fk** y columna **Ck**, que conservan el número
  que tenían como salida Yk del 138 y entrada Dk del 165. En el código las variables se siguen
  llamando `salida` y `entrada`, por la v2.

Lo eléctrico (verificación sin alimentar, prueba con un solo driver) está en
`hardware-docs/matriz-hall-nano.md`.

## Fuera de alcance (todavía)

- Lógica de reloj real (cuenta de tiempo, de quién es el turno, mensaje de fin de partida): esto es
  pura detección de flanco por pin + el puente a nombre de botón — la lógica de reloj vive en
  `logica/reloj.py`, y `io/menus.py`/`io/menus_gpio.py` la usan (ver `software-docs/menus.md`).

## Cómo probarlo

### Botones del reloj

**Test de cableado standalone** (ya verificado por Tino: detecta ambos pines correctamente), por
SSH en la Raspberry, con los dos botones cableados a sus pines y GND dedicados:

```bash
cd tablero
uv run python -m tablero.io.sensores
```

Debería loguear primero la línea de espera, y luego una línea por cada presión, identificando cuál
botón fue:

```
... INFO Esperando presiones en boton_1 (pin 33) o boton_2 (pin 35) (Ctrl+C para salir)...
... INFO boton_1 presionado
... INFO boton_2 presionado
```

Con `Ctrl+C` debería salir limpio (sin traceback), logueando `GPIO liberado, saliendo.`.

(`uv run python -m tablero.io.sensores botones` hace lo mismo; `botones` es la prueba por
defecto.)

### Matriz

Todo se corre desde `tablero/`, por SSH en la Raspberry, con el Nano enchufado a un USB de la Pi.
El Nano tiene que tener cargado el firmware (`firmware/matriz-nano/`, se sube desde la notebook:
ver [`firmware-nano.md`](./firmware-nano.md)). Para probar el hardware sin la Pi, el firmware
tiene sus propios comandos desde el monitor serie (`V`, `F`, `A`; ver "Prueba con un solo driver"
en `hardware-docs/matriz-hall-nano.md`).

La primera vez, antes de los comandos de abajo:

```bash
uv sync                          # instala pyserial
ls /dev/ttyUSB* /dev/ttyACM*     # tiene que aparecer el Nano (uno solo, si no ver NANO_PUERTO)
groups                           # tiene que estar dialout
```

Si falta `dialout`: `sudo usermod -aG dialout $USER` y volver a entrar por SSH.

```bash
uv run python -m tablero.io.sensores matriz
uv run python -m tablero.io.sensores medir F0     # o una casilla, después de mapear: medir e4
uv run python -m tablero.io.sensores calibrar
uv run python -m tablero.io.sensores mapear
```

Cada uno tarda ~2 s en arrancar: abrir el puerto resetea el Nano.

#### Si no conecta

Si algo falla con el Nano, el comando termina con una línea `Error con el Nano: …`:

| Mensaje | Qué hacer |
|---|---|
| `No aparece el Nano: no hay ningún /dev/ttyUSB* ni /dev/ttyACM*` | Cable USB (algunos solo cargan, no tienen datos) o el Nano sin alimentación. `dmesg \| tail` al enchufarlo tiene que mostrar el `ch341` o el `cdc_acm` |
| `Hay varios puertos serie (…)` | Poner el del Nano en `NANO_PUERTO` de `config.py` |
| `Sin permiso para abrir …` | El usuario no está en `dialout` (ver arriba) |
| `… está ocupado por otro programa` | Cerrar el monitor de `arduino-cli` u otra prueba que esté usando la matriz |
| `El Nano en … no contesta` | El firmware no está cargado, o es otro sketch. Probar con `arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200` y escribir `?` |
| `El Nano habla la versión … del protocolo` | El firmware del Nano es de otra versión del repo: volver a subirlo |
| `Se cortó la comunicación con el Nano` | Se desenchufó el USB, o el Nano se reseteó por una caída de tensión (por ejemplo un corto en la matriz) |
| `El Nano no contestó bien a …` | Respuestas mal formadas 3 veces seguidas: ruido en el USB o un firmware distinto. Mirar los `WARNING` de arriba, que muestran lo que llegó |

#### `medir`

Barriendo, cada fila está encendida 1/8 del tiempo y el multímetro muestra un promedio que no
sirve. `medir` deja **una fila fija** encendida (`F k` del Nano) hasta `Ctrl+C`. Acepta una fila
(`medir F3`, con **F mayúscula**: `f3` en minúscula es la casilla f3) o, ya hecho `mapear`, una
casilla (`medir e4`: elige la fila de esa casilla y dice qué pin del Nano es su columna).

Imprime qué medir (las mismas mediciones que "Prueba con un solo driver" de
`hardware-docs/matriz-hall-nano.md`) y debajo, cada 0,2 s, tres líneas por columna C0..C7:

- `pieza`: `#` si el Nano ve un imán (comando `C`).
- `ADC`: el nivel de la columna, de 0 (0 V) a 1023 (~5 V), con el comando `A`. C0–C2 salen como `-`
  porque sus pines no son analógicos; esas se miden con el multímetro.
- `tensión`: lo mismo en voltios.

| Medición (punta negra en GND del Nano) | Tiene que dar | Si no |
|---|---|---|
| 1. El pin de la fila (D2–D9) | ~5 V | La fila no se encendió o el pin está en corto |
| 2. Base del NPN / colector (bus de la fila) | 0,7–0,9 V / < 0,3 V | Falta la de 470 Ω, el transistor está mal puesto o no se satura |
| 3. Entre GND y Vcc de un Hall de la fila | ≥ 3,8 V | Riel de 5 V mal, o el colector no baja |
| 4. Una columna con pieza | < 1,3 V (`ADC` < 270); sin pieza ~5 V (~1020) | Entre 1,3 y 1,5 V funciona justo; más de 1,5 V (`ADC` > 307), plan B |

Si cambia la alimentación del Nano (hoy los LEDs y el Nano van con su propio cargador, ver
`hardware-docs/componentes.md`), el 5 V puede cambiar: conviene repetir `medir` con una fila
llena y comparar los valores de `ADC`.

#### Matriz en vivo

`matriz` limpia la terminal y dibuja la matriz cruda (F0–F7 × C0–C7) y el tablero ya mapeado cada
vez que cambia algo, y loguea `aparece pieza en e4` / `se levanta pieza de e2`.

Qué mirar: con el tablero vacío no tiene que haber ninguna celda `#`; al apoyar una pieza tiene
que encenderse **una sola** celda. Hasta correr `mapear`, el tablero mapeado no significa nada.

| Qué se ve | Causa probable |
|---|---|
| Una fila F entera en `#` con el tablero vacío | El bus de esa fila toca GND directo, o su NPN está en corto |
| Una columna C entera en `#` con el tablero vacío | El cable de la columna toca GND |
| Una fila nunca detecta | NPN con las patas cambiadas, falta la de 470 Ω, o el bus no llega al colector (`medir`, medición 2) |
| Nunca se enciende nada | Falta el 5 V del riel de los Hall, o la unión de GND entre los emisores y el Nano. O todos los imanes con el polo norte hacia abajo |
| **Una pieza no se detecta y otra sí**, en la misma casilla | El imán de esa pieza está al revés: el A3144 solo ve el polo sur. Darlo vuelta y marcar el polo en todas las piezas |
| Una casilla nunca detecta | Diodo del GND cortado o al revés, Hall de cara o dañado, o ese Hall no arranca con ~4 V |
| Una pieza aparece también en otra fila | El diodo de algún Hall de esa columna está en corto o puenteado |
| Celda fija en `#` con el tablero vacío | Hall dañado o un imán cerca (uno suelto debajo del tablero). Hay que arreglarlo antes de `mapear`, que pide una sola celda activa |
| La celda sigue en `#` después de levantar la pieza | Ese sensor es un Hall de tipo *latch* (biestable), no un switch: se apaga solo con el polo contrario. Revisar el modelo |
| Con una pieza detecta, con la fila llena falla | El NPN no se satura (modelo débil o base de más de 470 Ω), o el nivel de la columna supera el umbral: `medir` con la fila llena, y si pasa de 1,5 V, plan B |
| Celdas que parpadean sin tocar nada | Espera de encendido corta (correr `calibrar`), nivel de la columna cerca de 1,5 V (`medir`, medición 4) o el imán en el borde de la casilla. Si no es eso, subir `HALL_LECTURAS_ESTABLES` |

Para probar los diodos, poner piezas en todas las casillas de una columna (o las 32 en la posición
inicial y después las 32 en las filas 3–6): tienen que verse todas, estables, y ninguna fuera de
su casilla.

#### `calibrar`

Mide la espera de encendido y el antirrebote, en tres pasos, y al final imprime las dos líneas
para pegar en `config.py` (`HALL_ESPERA_ENCENDIDO`, `HALL_LECTURAS_ESTABLES`):

1. **Reposo**: con el tablero vacío, 3 s de barridos con 5 ms por fila. Lista los Hall que marcan
   pieza sin imán (hay que arreglarlos antes de `mapear`).
2. **Tiempo de encendido**: con la posición inicial armada, toma como referencia la lectura más
   común con 5 ms por fila. Después prueba 30 barridos con cada espera, de 5 ms a 0, e imprime
   cuántos coincidieron con la referencia. La espera mínima es la más corta tal que ella **y todas
   las más largas** acertaron siempre (un acierto por debajo de una que falló fue casualidad). Se
   recomienda el doble, sin bajar de 0,1 ms. Si ni con 5 ms se lee siempre igual, da `FALLA`: no
   es un problema de tiempo, sino eléctrico (`medir`).
3. **Estabilidad**: 10 s sin tocar el tablero, con la espera recomendada. Imprime las celdas que
   cambiaron y la racha más larga de lecturas falsas iguales; recomienda esa racha + 2 lecturas
   estables, con un mínimo de 3.

#### `mapear`

Genera `CASILLA_DE_CELDA_HALL`. Con una sola pieza, pide la pieza en a1, b1, …, h1, a2, …, h8 (las
64) y Enter en cada una; `r` vuelve a la casilla anterior. En cada paso valida que haya una sola
celda activa: si no hay ninguna avisa de la polaridad del imán, y si la celda ya quedó asignada a
otra casilla pregunta si la pieza sigue en la anterior. Al final imprime el bloque para reemplazar
en `config.py` (10 líneas, una fila F por línea) y avisa si el cableado no resultó una grilla
(la tabla funciona igual, pero puede indicar un error de cableado).

Después de pegarlo, volver a correr `matriz` y confirmar que el tablero mapeado coincide con las
piezas reales, o mejor, `prueba_tablero recorrido`, que verifica sensores y LEDs juntos (ver
[`prueba-tablero.md`](./prueba-tablero.md)).

### Otros

**Test del reloj PvP completo** (usa `configurar_botones_reloj()` desde `io/menus_gpio.py`, no
este test standalone): ver "Modo hardware real" en `software-docs/menus.md`.

Si aparece un `PermissionError` al acceder a GPIO (primera vez que se corre código GPIO en esta
Raspberry), verificar que el usuario esté en el grupo `gpio` (`groups $USER`) — si no,
`sudo usermod -aG gpio $USER` y volver a iniciar sesión SSH. Para el puerto del Nano, el grupo es
`dialout` (ver "Si no conecta").
