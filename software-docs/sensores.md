# `io/sensores.py`

Entradas digitales del tablero. Por ahora cubre únicamente los dos botones físicos del reloj de
ajedrez (interruptores fin de carrera / limit switches, ver `hardware-docs/componentes.md`). La
matriz de ocupación de casillas (74HC165 + 74HC138, 64 reed switches) todavía no está
implementada acá.

## Por qué existe este módulo

Es el punto de entrada de GPIO real del proyecto (primera vez que se usa `rpi-lgpio` en este
repo). Aísla al resto del código de los detalles de `RPi.GPIO`/`rpi-lgpio`: cualquier lógica de
reloj futura (`logica/`) solo necesitará reaccionar a "se presionó boton_1/boton_2", no a pines ni
flancos.

## API

| Función | Qué hace |
|---|---|
| `probar_botones_reloj()` | Loguea cada presión de `boton_1` (pin 33) o `boton_2` (pin 35). Test manual, corre hasta `Ctrl+C`. No implementa lógica de reloj (tiempo, turnos) — eso queda para `logica/` a futuro. |

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

## Fuera de alcance (todavía)

- Lógica de reloj real: cuenta de tiempo, de quién es el turno, cambio de turno al presionar. Esto
  es pura detección de flanco por pin.
- Matriz de ocupación de casillas (74HC165 + 74HC138, 64 reed switches) — pines ya documentados en
  `hardware-docs/componentes.md` pero sin código todavía.
- Integración con `logica/eventos.py` / `logica/estado_tablero.py`.

## Cómo probarlo

Por SSH, en la Raspberry, con los dos botones cableados a sus pines y GND dedicados:

```bash
cd tablero
uv run python -m tablero.io.sensores
```

Debería loguear primero la línea de espera, y luego una línea por cada presión, identificando cuál
botón fue:

```
... INFO Esperando presiones en boton_1 (pin 33) o boton_2 (pin 35) (Ctrl+C para salir)...
... INFO boton_1 presionado (pin físico 33)
... INFO boton_2 presionado (pin físico 35)
```

Con `Ctrl+C` debería salir limpio (sin traceback), logueando `GPIO liberado, saliendo.`.

Si aparece un `PermissionError` al acceder a GPIO (primera vez que se corre código GPIO en esta
Raspberry), verificar que el usuario esté en el grupo `gpio` (`groups $USER`) — si no,
`sudo usermod -aG gpio $USER` y volver a iniciar sesión SSH.
