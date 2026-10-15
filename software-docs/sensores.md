# `io/sensores.py`

Entradas digitales del tablero: los dos botones físicos del reloj de ajedrez (interruptores fin
de carrera / limit switches, ver `hardware-docs/componentes.md`) y la matriz de ocupación de
casillas (74HC138 + 74HC165, 64 reed switches). Los botones están verificados en hardware; la
matriz está implementada pero **todavía no se calibró ni se verificó en el prototipo** (ver
"Matriz de casillas" más abajo).

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

## Matriz de casillas

### API

| Función/clase | Qué hace |
|---|---|
| `configurar_matriz()` / `liberar_matriz()` | Configura / libera solo los 6 pines de la matriz |
| `leer_matriz()` | Un barrido completo, sin antirrebote: `MatrizCruda`, `matriz[salida Y del 138][entrada D del 165]`, `True` = reed cerrado |
| `LectorMatriz(lecturas_estables)` | Antirrebote: `.leer()` devuelve la matriz solo cuando se repitió N veces seguidas **y** cambió respecto de la última estable; si no, `None`. `.reiniciar()` olvida lo leído |
| `casilla_de(salida, entrada)` | Celda cruda → `chess.Square`, según el mapeo de `config.py` |
| `ocupacion(matriz)` | Matriz cruda → `frozenset[chess.Square]`, la `Ocupacion` que espera `logica/eventos.py` |
| `probar_selector()` / `probar_lector()` | Pruebas de cada chip por separado (CLI `selector` / `lector`), ver "Pruebas por chip" más abajo |

### Pines (BOARD, ver `config.py`)

| Constante | Pin | GPIO (BCM) | Chip |
|---|---|---|---|
| `PIN_MATRIZ_SELECTOR_A` / `_B` / `_C` | 38 / 40 / 37 | 20 / 21 / 26 | 74HC138 A/B/C |
| `PIN_MATRIZ_CARGA` | 29 | 5 | 74HC165 SH/LD |
| `PIN_MATRIZ_RELOJ` | 31 | 6 | 74HC165 CLK |
| `PIN_MATRIZ_DATOS` | 36 | 16 | 74HC165 Q7 |

### Decisiones de diseño

- **Barrido por bit-banging**: por cada fila se escribe su número en A/B/C (el 138 pone esa
  salida en LOW), se espera 0,1 ms, un pulso LOW en SH/LD carga las 8 columnas en el 165, y se
  leen 8 bits por Q7 con un flanco de CLK entre cada uno. Q7 muestra D7 primero, por eso la
  lista se invierte para indexar D0..D7 igual que el esquemático. Columna en LOW = pieza.
- **Antirrebote por repetición** (`MATRIZ_LECTURAS_ESTABLES = 3`) en vez de por tiempo: la mano
  pasando sobre el tablero y el cierre de un reed generan parpadeos de pocos ms. Si con el
  prototipo se ven cambios fantasma, es el primer parámetro a subir.
- **Mapeo con dos permutaciones, no una tabla de 64**: cada salida del 138 es una fila física y
  cada entrada del 165 una columna física, así que `FILA_DE_SALIDA_138` y
  `COLUMNA_DE_ENTRADA_165` alcanzan, y la calibración pide 15 casillas en vez de 64. En el
  esquemático las columnas no entran en orden al 165, así que los valores por defecto
  (identidad) son solo un placeholder hasta correr `calibrar`.
- **`GPIO.cleanup(lista)`**: `rpi-lgpio` acepta una lista de pines igual que `RPi.GPIO`; lo
  confirman en la Pi los botones (`liberar_botones_reloj()`) y la prueba del 165.

### Chequeos eléctricos antes de energizar

La lista pata por pata de los dos chips (con qué tiene que tener continuidad cada una, qué no, y
cómo verificar pull-ups y celdas) está en `hardware-docs/conexiones-matriz.md`. Lo crítico:

- Vcc (pata 16) de los dos chips y pull-ups a **3,3 V, nunca 5 V**: los GPIO de la Pi no toleran
  5 V.
- **Medir continuidad de todas las patas que van a un nivel fijo**, no solo las de señal. Una
  entrada suelta puede flotar hacia el nivel correcto y hacer pasar una prueba de casualidad:
  pasó con las patas 10 y 15 del 165.
- Distancia a la que el imán cierra el reed a través del espesor real del tablero.

### Imanes y reeds

- **Punto muerto**: si el eje del imán queda perpendicular al reed y justo sobre su centro, las
  dos láminas reciben el mismo polo y el reed puede no cerrar. Por eso la guía de prueba pide
  probar cada casilla con la pieza centrada y corrida hacia los bordes.
- **Polaridad**: al reed le da igual qué polo tenga cerca. Conviene igual poner todas las piezas
  con el mismo polo hacia abajo: así dos piezas vecinas se repelen en vez de atraerse.

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

La guía paso a paso para probar y mapear la matriz completa (chips, imanes, calibración y
verificación de las 64 casillas) está en `hardware-docs/checklist-prueba-matriz.md`. Acá está
el detalle de cada prueba y cómo interpretar los resultados.

#### Pruebas por chip

Separan un problema de cableado o de alimentación de un chip de un problema de las columnas,
antes de mirar la matriz completa. Salieron de diagnosticar el armado del prototipo, que tuvo
tres fallas:
- El 165 no manejaba su salida: el pin 36 quedaba flotando y `matriz` mostraba todo en `#`.
- El 138 se alimentaba de rebote por una entrada: sus salidas inactivas daban ~2,8 V.
- Las patas 10 y 15 del 165 estaban sueltas: el 165 cargaba pero no desplazaba, así que `matriz`
  solo veía la columna de D7 y marcaba la fila entera.

**`selector` (74HC138)**: activa Y0…Y7 de a una y espera Enter entre cada una, para medir con el
multímetro. No usa el 165.

```bash
uv run python -m tablero.io.sensores selector
```

En cada paso, medir contra GND la pata que indica el mensaje (~0 V) y alguna salida inactiva
(~3,3 V). Midiendo además en el cátodo de un diodo de la fila, se confirma que esa Y llega a su
fila. Patas de las salidas: Y0 = 15, Y1 = 14, Y2 = 13, Y3 = 12, Y4 = 11, Y5 = 10, Y6 = 9, Y7 = 7.

| Qué se ve | Causa probable |
|---|---|
| La activa en ~0 V y las inactivas en ~3,3 V | ✅ Bien |
| Las inactivas en **~2,8 V** | La pata 16 no llega a 3,3 V y el chip se alimenta de rebote por una entrada en HIGH (la pata 6), a través de su diodo de protección (3,3 − 0,5 V). Funciona, pero fuera de especificación: llevar la pata 16 al 3,3 V |
| Todas las Y en ~3,3 V en todos los pasos | El 138 está deshabilitado (patas 4, 5 o 6) |
| Todo en ~0 V o en valores intermedios | Al 138 le falta Vcc o GND, o está al revés |
| Dos pasos activan la misma Y | Una de las líneas A, B o C no llega (pines 38, 40, 37) |
| Cada paso activa una Y distinta, pero no la que dice el mensaje | A, B y C están cruzadas. No hace falta cambiar nada: `calibrar` lo corrige |

**`lector` (74HC165)**: con el tablero vacío, prueba el 165 sin el 138, en dos partes. Imprime las
lecturas de cada parte y un veredicto (`OK` o `FALLA: ...`).

```bash
uv run python -m tablero.io.sensores lector
```

1. **Que maneje el pin 36**: deja SH/LD en LOW (así la salida copia en vivo la entrada D7, sin
   reloj) y lee el pin primero con pull-up y después con pull-down.
2. **Que desplace**: carga las columnas y da 8 pulsos de reloj. La salida tiene que pasar de D7
   (`1` con el tablero vacío) a lo que entra por SER, que está a GND (`0`).

| Resultado | Qué significa |
|---|---|
| pull-up y pull-down todo `1`; desplazamiento `1` → `0` (`OK`) | ✅ El 165 maneja el pin, D7 está en HIGH por su pull-up y los bits se desplazan |
| pull-up → todo `1`, pull-down → todo `0` | Nadie maneja el pin 36: cable de la pata 9 → pin 36, o el 165 sin Vcc/GND (patas 16/8), al revés o dañado. Las patas 1 y 2 no causan esto: el 165 no tiene "output enable" y, alimentado, siempre maneja la pata 9 |
| pull-up y pull-down todo `0` | El 165 funciona pero D7 está en LOW: medir las entradas D0…D7 (patas 11, 12, 13, 14, 3, 4, 5, 6) contra GND, tienen que dar ~3,3 V. ~0 V = algo la lleva a GND; valor intermedio o que salta = pull-up desconectada |
| Desplazamiento `1` → `1` | El 165 carga pero no desplaza: CLK (pata 2 → pin 31) no llega, INH (pata 15) no está a GND, o SH/LD y CLK están cruzados (pines 29/31). También da esto si SER (pata 10) no está a GND. En `matriz` se ve como "solo reacciona la columna de D7 y marca la fila entera" |
| Mezcla de 0 y 1 | Falso contacto |

#### Matriz en vivo

`matriz` limpia la terminal y dibuja la matriz cruda (Y0–Y7 × D0–D7) y el tablero ya mapeado cada
vez que cambia algo, y loguea `aparece pieza en e4` / `se levanta pieza de e2`:

```bash
uv run python -m tablero.io.sensores matriz
```

Qué mirar: con el tablero vacío no tiene que haber ninguna celda `#`; al apoyar una pieza tiene
que encenderse **una sola** celda. Si con una sola pieza se encienden varias, el imán está cerrando
reeds vecinos o hay un puente de estaño: con una pieza sola los diodos no influyen. Hasta correr
`calibrar`, el tablero mapeado no significa nada.

| Qué se ve | Causa probable |
|---|---|
| Todo en `#` | El pin 36 está flotando (`lector`), el 165 sin alimentación, o faltan las pull-ups |
| Nunca se enciende nada | El 138 está deshabilitado o A/B/C mal conectados (`selector`) |
| Solo reacciona la columna de D7 y marca la fila Y entera | El 165 no desplaza: CLK (pin 31 → pata 2) o INH (pata 15) sin GND (`lector`) |
| Una columna D entera en `#` | Pull-up suelta en esa columna o columna en corto a GND |
| Celdas que parpadean sin tocar nada | Soldaduras. Si no es eso, subir `MATRIZ_LECTURAS_ESTABLES` |

Los diodos se notan recién con **varias piezas en la misma columna física**. Como el 74HC138
mantiene en HIGH (push-pull) las filas no seleccionadas, un diodo faltante, en corto o invertido no
genera la casilla fantasma clásica del ghosting. Lo que pasa es que esa fila HIGH pelea contra la
fila LOW por la columna, y las *otras* piezas de esa columna parpadean o desaparecen. Un diodo
invertido, además, hace que su casilla no se encienda nunca. La prueba es poner piezas en todas
las casillas de una columna (o las 32 en la posición inicial y después las 32 en las filas 3–6):
tienen que verse todas, estables. Si falla, no dejarlo corriendo así, porque son dos salidas del
138 en corto a través del reed.

#### Calibración

Pide una pieza sola en a1, b1, … h1 y después en a2, … a8, verifica que el cableado sea una
grilla y al final imprime las dos líneas para pegar en `config.py`:

```bash
uv run python -m tablero.io.sensores calibrar
```

Después de pegarlas, volver a correr `matriz` y confirmar que el tablero mapeado coincide con
las piezas reales.

### Otros

**Test del reloj PvP completo** (usa `configurar_botones_reloj()` desde `io/menus_gpio.py`, no
este test standalone): ver "Modo hardware real" en `software-docs/menus.md`.

Si aparece un `PermissionError` al acceder a GPIO (primera vez que se corre código GPIO en esta
Raspberry), verificar que el usuario esté en el grupo `gpio` (`groups $USER`) — si no,
`sudo usermod -aG gpio $USER` y volver a iniciar sesión SSH.
