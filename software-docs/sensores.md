# `io/sensores.py`

Entradas digitales del tablero: los dos botones físicos del reloj de ajedrez (interruptores fin
de carrera / limit switches, ver `hardware-docs/componentes.md`) y la matriz de ocupación de
casillas, con **64 sensores Hall A3144 / KY-003** barridos por un 74HC138 y un 74HC165. Los
botones están verificados en hardware. La matriz Hall está implementada pero **todavía no se
probó en el prototipo** (ver "Matriz de casillas" más abajo).

La matriz empezó con reed switches. Esa versión se conserva en `io/sensores_reed.py`, ver
[`sensores-reed.md`](./sensores-reed.md); la de Hall es la actual y la que se usa por defecto.

> **El hardware de la matriz cambió y este código todavía no.** Lo que describe este archivo
> (la Pi barriendo el 74HC138 + 74HC165 por GPIO) es la v2 del hardware, que se descartó: el 138
> no aguanta la corriente de los Hall. Desde el 2026-10-17 la arquitectura es la v3: un Arduino
> Nano barre la matriz (un NPN por fila, Hall a 5 V) y le manda el estado a la Pi por USB. Ver
> `hardware-docs/matriz-hall-nano.md` y `hardware-docs/historial-deteccion.md`. Falta escribir el
> firmware del Nano y que `io/matriz.py` lea el puerto serie en vez de manejar GPIO; `medir`,
> `calibrar` y `mapear` también hay que adaptarlas. La API de arriba (`ocupacion()`, el mapeo
> celda → casilla) debería poder mantenerse.

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

Cada Hall tiene Vcc a 3,3 V, **GND a la salida Y del 74HC138 de su fila** y su salida
(open-collector) → diodo → la columna, que es una entrada D del 74HC165 con su pull-up. El 138
pone en LOW solo la fila elegida, así que **solo los Hall de esa fila tienen alimentación**: los
demás quedan con GND y Vcc a 3,3 V, apagados. Un Hall encendido con el polo sur de un imán encima
baja la columna, y el 165 la lee como pieza presente. Conexión, pinout y riesgos eléctricos en
`hardware-docs/celdas-hall.md`.

Respecto de los reed, eso cambia tres cosas para el software:

- **Hay que esperar a que el Hall encienda** después de elegir cada fila, antes de leer. Ese
  tiempo se mide con `calibrar`.
- **Polaridad**: el A3144 solo reacciona al polo sur. Una pieza con el imán al revés no se ve.
- **Fallas eléctricas nuevas**: corriente de la fila, tensión de los Hall y nivel de la columna.
  Se diagnostican con `medir`.

### Archivos

| Archivo | Qué tiene |
|---|---|
| `io/matriz.py` | Driver común a las dos versiones de sensor (los chips son los mismos): barrido del 138 + 165, `LectorMatriz` con antirrebote, vista en vivo y las pruebas por chip |
| `io/sensores.py` | La versión Hall: espera y antirrebote de los Hall, mapeo de 64 y los comandos `medir`, `matriz`, `calibrar`, `mapear` |
| `io/sensores_reed.py` | La versión reed, la anterior (ver [`sensores-reed.md`](./sensores-reed.md)) |
| `logica/matriz.py` | Lo que se hace con las lecturas y no necesita GPIO: validación de la tabla, celda → casilla y las cuentas de `calibrar`. Testeado en `tests/test_matriz.py` |
| `io/prueba_tablero.py` | Sensores y LEDs juntos (asociar LEDs, recorrido, espejo), ver [`prueba-tablero.md`](./prueba-tablero.md) |

### API

| Función/clase | Dónde | Qué hace |
|---|---|---|
| `configurar_matriz()` / `liberar_matriz()` | `io/matriz.py`, reexportados en `io/sensores.py` | Configura / libera solo los 6 pines de la matriz |
| `leer_matriz(espera)` | `io/matriz.py` | Un barrido completo, sin antirrebote: `MatrizCruda`, `matriz[salida Y del 138][entrada D del 165]`, `True` = sensor activo. Espera `espera` segundos en cada fila antes de leer |
| `LectorMatriz(espera, lecturas_estables)` | `io/sensores.py` | Antirrebote: `.leer()` devuelve la matriz solo cuando se repitió N veces seguidas **y** cambió respecto de la última estable; si no, `None`. `.reiniciar()` olvida lo leído; `.esperar_estable()` reinicia y espera la próxima. Por defecto usa `HALL_ESPERA_ENCENDIDO` y `HALL_LECTURAS_ESTABLES` |
| `casilla_de(salida, entrada)` | `io/sensores.py` | Celda cruda → `chess.Square`, según `CASILLA_DE_CELDA_HALL` |
| `ocupacion(matriz)` | `io/sensores.py` | Matriz cruda → `frozenset[chess.Square]`, la `Ocupacion` que espera `logica/eventos.py` |
| `probar_selector()` / `probar_lector()` | `io/matriz.py` | Pruebas de cada chip por separado (CLI `selector` / `lector`), ver "Pruebas por chip" |
| `medir(objetivo)` / `probar_matriz()` / `calibrar()` / `mapear()` | `io/sensores.py` | CLI `medir` / `matriz` / `calibrar` / `mapear`, ver "Cómo probarlo" |

`io/sensores_reed.py` tiene la misma API (`LectorMatriz`, `configurar_matriz`, `liberar_matriz`,
`casilla_de`, `ocupacion`): un futuro loop de juego que use `sensores` puede volver a los reed
cambiando solo el import.

### Pines (BOARD, ver `config.py`)

| Constante | Pin | GPIO (BCM) | Chip |
|---|---|---|---|
| `PIN_MATRIZ_SELECTOR_A` / `_B` / `_C` | 38 / 40 / 37 | 20 / 21 / 26 | 74HC138 A/B/C |
| `PIN_MATRIZ_CARGA` | 29 | 5 | 74HC165 SH/LD |
| `PIN_MATRIZ_RELOJ` | 31 | 6 | 74HC165 CLK |
| `PIN_MATRIZ_DATOS` | 36 | 16 | 74HC165 Q7 |

### Configuración (`config.py`, sección "versión Hall")

| Constante | Valor por defecto | Lo genera |
|---|---|---|
| `HALL_ESPERA_ENCENDIDO` | `0.001` (1 ms por fila, generoso) | `calibrar` |
| `HALL_LECTURAS_ESTABLES` | `3` | `calibrar` |
| `CASILLA_DE_CELDA_HALL` | identidad (Y0 = fila 1, D0 = columna a) | `mapear` |

### Decisiones de diseño

- **Un driver común para las dos versiones** (`io/matriz.py`): el 138, el 165 y su cableado son
  los mismos con reed o con Hall, así que un arreglo al barrido sirve para las dos. Cada versión
  solo pone su espera por fila, su antirrebote y su mapeo.
- **Barrido por bit-banging**: por cada fila se escribe su número en A/B/C (el 138 pone esa
  salida en LOW y, con los Hall, la enciende), se espera `HALL_ESPERA_ENCENDIDO`, un pulso LOW en
  SH/LD carga las 8 columnas en el 165, y se leen 8 bits por Q7 con un flanco de CLK entre cada
  uno. Q7 muestra D7 primero, por eso la lista se invierte para indexar D0..D7 igual que el
  esquemático. Columna en LOW = pieza.
- **Espera de encendido medida, no supuesta**: cuánto tarda un Hall en dar una salida válida
  después de recibir alimentación depende del modelo y del clon, y con la fila cargada puede ser
  más. `calibrar` la mide contra una referencia tomada con 5 ms y recomienda el doble de la
  mínima que anduvo. Las esperas de menos de 0,5 ms se hacen con espera activa
  (`time.perf_counter`), porque `time.sleep` en la Pi duerme bastante más de lo pedido.
- **Tabla de 64, no dos permutaciones como los reed**: `CASILLA_DE_CELDA_HALL[y][d]` es el nombre
  de la casilla de cada sensor. Con un cambio de último momento es probable que algún Hall quede
  cableado fuera de la grilla, y la tabla lo absorbe. Además, `mapear` pide las 64 casillas, así
  que de paso prueba que cada Hall detecte. Se guardan nombres (`"e4"`) y no números para poder
  revisar la grilla a simple vista en `config.py`.
- **Validación perezosa de la tabla**: `io/sensores.py` también tiene los botones del reloj, que
  usa `io/menus_gpio.py`. Si la tabla se validara al importar, un `CASILLA_DE_CELDA_HALL` mal
  pegado rompería el reloj. Se valida la primera vez que se usa la matriz, con un error que dice
  qué celda está mal. `tests/test_matriz.py` además valida la tabla de `config.py` en la notebook.
- **Antirrebote por repetición** (`HALL_LECTURAS_ESTABLES`): el Hall no rebota como un contacto
  mecánico, pero la mano pasando sobre el tablero, un imán en el borde de la casilla o un nivel
  eléctrico al límite generan parpadeos. `calibrar` mide la racha más larga de lecturas falsas
  iguales (lo que el antirrebote dejaría pasar) y recomienda esa racha + 2, con un mínimo de 3.
- **Cuentas en `logica/matriz.py`**: la validación de la tabla, el mapeo y la elección de la
  espera y del antirrebote son funciones puras sobre `MatrizCruda`. Viven fuera de `io/` para
  testearse en cualquier máquina; `io/sensores.py` solo junta las lecturas y las imprime.
- **`GPIO.cleanup(lista)`**: `rpi-lgpio` acepta una lista de pines igual que `RPi.GPIO`; lo
  confirman en la Pi los botones (`liberar_botones_reloj()`) y la prueba del 165.

### Chequeos eléctricos antes de energizar

La lista pata por pata de los dos chips está en `hardware-docs/conexiones-matriz.md` y la de las
celdas Hall, con los riesgos, en `hardware-docs/celdas-hall.md`. Lo crítico:

- Vcc (pata 16) de los dos chips, pull-ups y Vcc de los Hall a **3,3 V, nunca 5 V**: los GPIO de
  la Pi no toleran 5 V, y un Hall a 5 V con su GND en una salida del 138 le mete corriente al
  riel de 3,3 V.
- **Medir continuidad de todas las patas que van a un nivel fijo**, no solo las de señal. Una
  entrada suelta puede flotar hacia el nivel correcto y hacer pasar una prueba de casualidad:
  pasó con las patas 10 y 15 del 165.
- **Probar una fila entera antes de soldar las 64**: los 8 A3144 de una fila consumen más de lo
  que una salida del 138 puede hundir (ver `hardware-docs/celdas-hall.md`). Se ve con `medir`.

## Fuera de alcance (todavía)

- Lógica de reloj real (cuenta de tiempo, de quién es el turno, mensaje de fin de partida): esto es
  pura detección de flanco por pin + el puente a nombre de botón — la lógica de reloj vive en
  `logica/reloj.py`, y `io/menus.py`/`io/menus_gpio.py` la usan (ver `software-docs/menus.md`).
- Integración de la matriz con `logica/eventos.py` / `logica/partida.py` en un loop de juego:
  `ocupacion()` ya produce la entrada correcta, pero nadie la consume todavía.

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

La guía paso a paso para probar y mapear la matriz Hall completa (chips, tensiones, imanes,
calibración, mapeo, LEDs y verificación de las 64 casillas) está en
`hardware-docs/checklist-prueba-hall.md`. Acá está el detalle de cada prueba y cómo interpretar
los resultados. Todo se corre desde `tablero/`, por SSH en la Raspberry:

```bash
uv run python -m tablero.io.sensores selector
uv run python -m tablero.io.sensores lector
uv run python -m tablero.io.sensores medir Y0     # o una casilla, después de mapear: medir e4
uv run python -m tablero.io.sensores matriz
uv run python -m tablero.io.sensores calibrar
uv run python -m tablero.io.sensores mapear
```

#### Pruebas por chip

Separan un problema de cableado o de alimentación de un chip de un problema de las columnas,
antes de mirar la matriz completa. Son las mismas para las dos versiones de sensor
(`sensores_reed selector` y `sensores_reed lector` corren el mismo código). Salieron de
diagnosticar el armado del prototipo, que tuvo tres fallas:
- El 165 no manejaba su salida: el pin 36 quedaba flotando y `matriz` mostraba todo en `#`.
- El 138 se alimentaba de rebote por una entrada: sus salidas inactivas daban ~2,8 V.
- Las patas 10 y 15 del 165 estaban sueltas: el 165 cargaba pero no desplazaba, así que `matriz`
  solo veía la columna de D7 y marcaba la fila entera.

**`selector` (74HC138)**: activa Y0…Y7 de a una y espera Enter entre cada una, para medir con el
multímetro. No usa el 165.

En cada paso, medir contra GND la pata que indica el mensaje (~0 V) y alguna salida inactiva
(~3,3 V). Midiendo además en el GND de un Hall de la fila, se confirma que esa Y llega a su
fila. Patas de las salidas: Y0 = 15, Y1 = 14, Y2 = 13, Y3 = 12, Y4 = 11, Y5 = 10, Y6 = 9, Y7 = 7.

| Qué se ve | Causa probable |
|---|---|
| La activa en ~0 V y las inactivas en ~3,3 V | ✅ Bien |
| La activa en **~0,3 V o más**, solo con los Hall conectados | El 138 no da abasto con la corriente de los 8 Hall de esa fila: ver `medir` y `hardware-docs/celdas-hall.md` |
| Las inactivas en **~2,8 V** | La pata 16 no llega a 3,3 V y el chip se alimenta de rebote por una entrada en HIGH (la pata 6), a través de su diodo de protección (3,3 − 0,5 V). Funciona, pero fuera de especificación: llevar la pata 16 al 3,3 V |
| Todas las Y en ~3,3 V en todos los pasos | El 138 está deshabilitado (patas 4, 5 o 6) |
| Todo en ~0 V o en valores intermedios | Al 138 le falta Vcc o GND, o está al revés |
| Dos pasos activan la misma Y | Una de las líneas A, B o C no llega (pines 38, 40, 37) |
| Cada paso activa una Y distinta, pero no la que dice el mensaje | A, B y C están cruzadas. No hace falta cambiar nada: `mapear` lo corrige |

**`lector` (74HC165)**: con el tablero vacío, prueba el 165 sin el 138, en dos partes. Imprime las
lecturas de cada parte y un veredicto (`OK` o `FALLA: ...`).

1. **Que maneje el pin 36**: deja SH/LD en LOW (así la salida copia en vivo la entrada D7, sin
   reloj) y lee el pin primero con pull-up y después con pull-down.
2. **Que desplace**: carga las columnas y da 8 pulsos de reloj. La salida tiene que pasar de D7
   (`1` con el tablero vacío) a lo que entra por SER, que está a GND (`0`).

| Resultado | Qué significa |
|---|---|
| pull-up y pull-down todo `1`; desplazamiento `1` → `0` (`OK`) | ✅ El 165 maneja el pin, D7 está en HIGH por su pull-up y los bits se desplazan |
| pull-up → todo `1`, pull-down → todo `0` | Nadie maneja el pin 36: cable de la pata 9 → pin 36, o el 165 sin Vcc/GND (patas 16/8), al revés o dañado. Las patas 1 y 2 no causan esto: el 165 no tiene "output enable" y, alimentado, siempre maneja la pata 9 |
| pull-up y pull-down todo `0` | El 165 funciona pero D7 está en LOW: medir las entradas D0…D7 (patas 11, 12, 13, 14, 3, 4, 5, 6) contra GND, tienen que dar ~3,3 V. ~0 V = algo la lleva a GND (con los Hall, también un imán cerca de esa columna); valor intermedio o que salta = pull-up desconectada |
| Desplazamiento `1` → `1` | El 165 carga pero no desplaza: CLK (pata 2 → pin 31) no llega, INH (pata 15) no está a GND, o SH/LD y CLK están cruzados (pines 29/31). También da esto si SER (pata 10) no está a GND. En `matriz` se ve como "solo reacciona la columna de D7 y marca la fila entera" |
| Mezcla de 0 y 1 | Falso contacto |

#### `medir`

Barriendo, cada fila está encendida 1/8 del tiempo y el multímetro muestra un promedio que no
sirve. `medir` deja **una fila fija** encendida hasta `Ctrl+C` y muestra en vivo qué columnas lee
el 165 en esa fila. Acepta una salida del 138 (`medir Y3`) o, ya hecho `mapear`, una casilla
(`medir e4`: elige la fila de esa casilla y dice qué pata del 165 corresponde). Imprime qué medir:

| Medición (contra GND, salvo la 2) | Tiene que dar | Si no |
|---|---|---|
| 1. La pata de la Y activa en el 138 | < 0,3 V | El 138 no da abasto con la corriente de los Hall de la fila |
| 2. Entre GND y Vcc de un Hall de la fila | ≥ 3 V | Los Hall no reciben tensión suficiente (consecuencia de la 1, o Vcc mal conectado) |
| 3. Con la pieza en una casilla de esa fila, la pata del 165 de su columna | < 0,8 V (sin pieza, ~3,3 V) | Nivel bajo al límite del umbral del 165 (~1 V a 3,3 V): la celda parpadea o no se ve. Diodo Schottky o resolver la 1 |

#### Matriz en vivo

`matriz` limpia la terminal y dibuja la matriz cruda (Y0–Y7 × D0–D7) y el tablero ya mapeado cada
vez que cambia algo, y loguea `aparece pieza en e4` / `se levanta pieza de e2`.

Qué mirar: con el tablero vacío no tiene que haber ninguna celda `#`; al apoyar una pieza tiene
que encenderse **una sola** celda. Hasta correr `mapear`, el tablero mapeado no significa nada.

| Qué se ve | Causa probable |
|---|---|
| Todo en `#` | El pin 36 está flotando (`lector`), el 165 sin alimentación, o faltan las pull-ups |
| Nunca se enciende nada | El 138 está deshabilitado o A/B/C mal conectados (`selector`). Si los chips andan: la fila no baja o los Hall no tienen tensión (`medir`, mediciones 1 y 2), o todos los imanes están con el polo norte hacia abajo |
| Solo reacciona la columna de D7 y marca la fila Y entera | El 165 no desplaza: CLK (pin 31 → pata 2) o INH (pata 15) sin GND (`lector`) |
| **Una pieza enciende la columna D entera** (las 8 Y) | El GND de ese Hall va a GND común en vez de a la salida Y de su fila: el 138 no lo puede apagar y baja la columna en todas las filas |
| Una columna D entera en `#` con el tablero vacío | Pull-up suelta en esa columna o columna en corto a GND |
| **Una pieza no se detecta y otra sí**, en la misma casilla | El imán de esa pieza está al revés: el A3144 solo ve el polo sur. Darlo vuelta y marcar el polo en todas las piezas |
| Ninguna pieza se detecta en una casilla | Hall dañado, mal soldado o al revés (ver el pinout en `hardware-docs/celdas-hall.md`), o el diodo invertido |
| Celda fija en `#` con el tablero vacío | Hall dañado o un imán cerca (uno suelto debajo del tablero), o un puente de estaño entre la salida del Hall y su GND. Hay que arreglarlo antes de `mapear`, que pide una sola celda activa |
| La celda sigue en `#` después de levantar la pieza | Ese sensor es un Hall de tipo *latch* (biestable), no un switch: se apaga solo con el polo contrario. Revisar el modelo |
| Con varias piezas en la misma fila se pierden detecciones | Corriente de la fila: en los KY-003, cada pieza además prende el LED del módulo, y esa corriente también pasa por la Y. Medir con `medir` con la fila llena |
| Celdas que parpadean sin tocar nada | Espera de encendido corta (correr `calibrar`), nivel de la columna al límite (`medir`, medición 3) o el imán en el borde de la casilla. Si no es eso, subir `HALL_LECTURAS_ESTABLES` |

Los diodos se notan con **varias piezas en la misma columna física**. Sin el diodo (o en corto),
cuando otro Hall de la columna la baja, el Hall apagado le inyecta corriente desde su fila (que
está en HIGH) a través de sus diodos de protección internos: la columna no baja bien y las piezas
de esa columna parpadean o desaparecen. Con el diodo invertido, esa casilla no se detecta nunca.
La prueba es poner piezas en todas las casillas de una columna (o las 32 en la posición inicial y
después las 32 en las filas 3–6): tienen que verse todas, estables.

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
en `config.py` (10 líneas, una salida Y por línea) y avisa si el cableado no resultó una grilla
(la tabla funciona igual, pero puede indicar un error de cableado).

Después de pegarlo, volver a correr `matriz` y confirmar que el tablero mapeado coincide con las
piezas reales, o mejor, `prueba_tablero recorrido`, que verifica sensores y LEDs juntos (ver
[`prueba-tablero.md`](./prueba-tablero.md)).

### Otros

**Test del reloj PvP completo** (usa `configurar_botones_reloj()` desde `io/menus_gpio.py`, no
este test standalone): ver "Modo hardware real" en `software-docs/menus.md`.

Si aparece un `PermissionError` al acceder a GPIO (primera vez que se corre código GPIO en esta
Raspberry), verificar que el usuario esté en el grupo `gpio` (`groups $USER`) — si no,
`sudo usermod -aG gpio $USER` y volver a iniciar sesión SSH.
