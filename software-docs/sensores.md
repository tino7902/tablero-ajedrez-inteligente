# `io/sensores.py`

Entradas digitales del tablero: los dos botones físicos del reloj de ajedrez (interruptores fin
de carrera / limit switches, ver `hardware-docs/componentes.md`) y la matriz de ocupación de
casillas (74HC138 + 74HC165, 64 reed switches). Los botones están verificados en hardware; la
matriz está implementada pero **todavía no se probó en el prototipo** (ver "Matriz de casillas"
más abajo).

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
- **Riesgo conocido**: se asume que `GPIO.cleanup(lista)` de `rpi-lgpio` acepta una lista de
  pines, igual que `RPi.GPIO`. Si falla, es lo primero a revisar.

### Chequeos eléctricos antes de energizar

- Pull-ups de columna y Vcc de ambos chips a **3,3 V, nunca 5 V**: los GPIO de la Pi no toleran 5 V.
- 74HC165: CLK INH (pin 15) y SER (pin 10) a GND. 74HC138: E1/E2 (pines 4/5) a GND, E3 (pin 6) a Vcc.
- Orientación de los 64 diodos (cátodo hacia la línea de fila).
- Distancia y polaridad a la que el imán cierra el reed a través del espesor real del tablero.

## Fuera de alcance (todavía)

- Lógica de reloj real (cuenta de tiempo, de quién es el turno, mensaje de fin de partida): esto es
  pura detección de flanco por pin + el puente a nombre de botón — la lógica de reloj vive en
  `logica/reloj.py`, y `io/menus.py`/`io/menus_gpio.py` la usan (ver `software-docs/menus.md`).
- Integración de la matriz con `logica/eventos.py` / `logica/partida.py` en un loop de juego:
  `ocupacion()` ya produce la entrada correcta, pero nadie la consume todavía.

## Cómo probarlo

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

**Test de la matriz en vivo**: limpia la terminal y dibuja la matriz cruda (Y0–Y7 × D0–D7) y el
tablero ya mapeado cada vez que cambia algo, y loguea `aparece pieza en e4` / `se levanta pieza
de e2`:

```bash
uv run python -m tablero.io.sensores matriz
```

Qué mirar: con el tablero vacío no tiene que haber ninguna celda `#`; al apoyar una pieza tiene
que encenderse **una sola** celda (si se encienden varias de la misma columna, hay ghosting: un
diodo invertido o faltante). Si todas las celdas salen `#`, revisar que Q7 llegue al pin 36 y que
las columnas tengan pull-up.

**Calibración del mapeo**: pide una pieza sola en a1, b1, … h1 y después en a2, … a8, verifica
que el cableado sea una grilla y al final imprime las dos líneas para pegar en `config.py`:

```bash
uv run python -m tablero.io.sensores calibrar
```

Después de pegarlas, volver a correr `matriz` y confirmar que el tablero mapeado coincide con
las piezas reales.

**Test del reloj PvP completo** (usa `configurar_botones_reloj()` desde `io/menus_gpio.py`, no
este test standalone): ver "Modo hardware real" en `software-docs/menus.md`.

Si aparece un `PermissionError` al acceder a GPIO (primera vez que se corre código GPIO en esta
Raspberry), verificar que el usuario esté en el grupo `gpio` (`groups $USER`) — si no,
`sudo usermod -aG gpio $USER` y volver a iniciar sesión SSH.
