# `firmware/matriz-nano/` (firmware del Arduino Nano)

Firmware del Arduino Nano que barre la matriz de 64 sensores Hall en la v3 de la detección de
casillas (cableado en `hardware-docs/matriz-hall-nano.md`, por qué un Nano en
`hardware-docs/historial-deteccion.md`). Es un solo archivo, `matriz-nano.ino`.

**Estado:** probado en el Nano real con la matriz completa, en el cableado normal (plan A,
columnas digitales): desde el monitor serie de la notebook detecta las 64 casillas. Del lado Pi,
`io/matriz.py` ya le habla por el puerto serie (ver "Del lado Pi: `io/matriz.py`"), pero
**todavía no se probó con el Nano enchufado a la Pi** (ver "Qué falta").

## Por qué un Nano "tonto"

El Nano no hace nada por su cuenta: espera un comando por el puerto serie, lo ejecuta y contesta
una línea. El antirrebote (`LectorMatriz`), la calibración (`calibrar`), el mapeo celda → casilla
(`CASILLA_DE_CELDA_HALL`) y todo lo demás siguen en Python, donde ya estaban escritos y testeados.
Cada comando equivale a una función de `io/matriz.py` (ver "Correspondencia con `io/matriz.py`"),
así que el lado Pi cambia poco.

Además, como los comandos son texto, el mismo firmware sirve para probar el hardware a mano desde
el monitor serie (`V` muestra la grilla en vivo, `F` deja una fila fija para el multímetro, `A`
mide el nivel de las columnas) y para la partida: no hay sketch de prueba aparte ni hay que volver
a flashear.

Se descartaron un Nano que manda cada barrido sin que se lo pidan (la Pi necesitaría un hilo que
vacíe el buffer, y `calibrar`/`medir` igual necesitan comandos) y uno que hace el antirrebote y
solo avisa los cambios (pasa lógica a C++, donde no la cubre pytest, y duplica `LectorMatriz`).

## Compilar y subir

Desde la raíz del repo (no desde `tablero/`), en la notebook, con el Nano por USB. Los clones con
CH340 aparecen como `/dev/ttyUSB0`; otros, como `/dev/ttyACM0` (`arduino-cli board list` lo dice).

```bash
# Solo compilar (no necesita el Nano):
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 firmware/matriz-nano

# Compilar y subir:
arduino-cli compile --upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328 firmware/matriz-nano

# Monitor serie para escribirle comandos (Ctrl+C sale):
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
```

- `cpu=atmega328` es el bootloader nuevo (Optiboot, sube a 115200), el que tiene el Nano del
  proyecto: verificado el 2026-10-17 leyendo la firma del chip (`1E 95 0F`, ATmega328P, bootloader
  4.4). Con `cpu=atmega328old` (bootloader viejo, 57600) ese Nano no contesta y la subida falla
  con `not in sync`. Si algún día se cambia el Nano y con `cpu=atmega328` da `not in sync`, ese
  tiene el bootloader viejo: usar `cpu=atmega328old`.
- Si da `Permission denied` sobre el puerto: `sudo usermod -aG uucp $USER` (en CachyOS/Arch el
  puerto es del grupo `uucp`) y volver a iniciar sesión.
- El monitor no se puede usar mientras se sube: cerrarlo antes.
- Con el Arduino IDE: abrir `firmware/matriz-nano/matriz-nano.ino`, placa `Arduino Nano`,
  procesador `ATmega328P` (no el `Old Bootloader`), monitor serie a 115200 con fin de línea
  "Nueva línea".

Compilado con `arduino-cli` 1.5.1 y el core `arduino:avr` 1.8.8: usa ~4,2 kB de flash (13 %) y
239 bytes de RAM (11 %).

## Protocolo v1

- **Conexión:** USB serie a 115200 baudios, 8N1. Texto ASCII, una línea por comando y una línea
  por respuesta (salvo `V`, ver abajo).
- **Fin de línea:** el Nano termina sus líneas con `\r\n`. Lo que le llega puede terminar en
  `\n`, `\r` o `\r\n`; las líneas vacías o con solo espacios se ignoran.
- **Comandos:** una letra, en mayúscula o minúscula, y a veces un número, con o sin espacio en el
  medio (`F3` = `F 3` = ` f 3 `). Máximo 15 caracteres por línea.
- **Arranque:** abrir el puerto resetea el Nano (por la señal DTR del USB). Tarda 1–2 s en
  arrancar; al hacerlo apaga todas las filas y manda `LISTO matriz-nano 1`. Quien abre el puerto
  tiene que esperar esa línea antes de mandar nada (lo que llegue antes se pierde). Antes del `LISTO`
  el Nano manda una línea vacía: con el reset suele entrar basura por el USB (se vio `�1�X�`), y
  así queda sola en su propia línea. Quien lee tiene que descartar todo lo que llegue antes de una
  línea igual a `LISTO matriz-nano 1`. El `1` es la
  versión del protocolo: si cambia de forma incompatible, se sube.

| Comando | Respuesta | Qué hace |
|---|---|---|
| `?` | `LISTO matriz-nano 1` | Ping: confirma que del otro lado está este firmware y qué versión de protocolo habla |
| `L` / `L <µs>` | `M b0 b1 b2 b3 b4 b5 b6 b7` | Barrido completo: enciende F0..F7 de a una, espera `<µs>` microsegundos en cada fila (0–50000; sin número, 1000, igual que `HALL_ESPERA_ENCENDIDO`) y lee las 8 columnas. Al terminar quedan todas las filas apagadas |
| `F <k>` | `OK F<k>` | Enciende fija la fila k (0–7) y apaga las demás, hasta el próximo `F`, `X`, `L` o `V`. Para medir con el multímetro: barriendo, cada fila está encendida 1/8 del tiempo y el multímetro marca un promedio |
| `C` | `C bb` | Lee las 8 columnas ahora, sin tocar las filas (después de `F k`: las casillas de la fila k) |
| `X` | `OK X` | Apaga todas las filas |
| `A` | `A v0 v1 … v7` | Lectura analógica cruda (0–1023) de cada columna, con la fila que esté encendida; `-` en las columnas que no son analógicas (C0–C2 en el cableado normal, que están en D10–D12) |
| `V` / `V <µs>` | grilla, cada 500 ms | Vista en vivo para una persona en el monitor serie (no para la Pi): barre con esa espera e imprime la grilla de `#`/`.`. Cualquier línea nueva la corta y se procesa normalmente |
| otro | `ERR comando` | Comando desconocido |
| | `ERR argumento` | Número fuera de rango (`F 9`, `L 60000`), que falta (`F`), que sobra (`C 3`, `X 1`) o que no es un número |
| | `ERR largo` | Línea de más de 15 caracteres (se descarta entera) |

No hay checksum: USB ya verifica los datos. Quien lee valida el formato de la respuesta y, si
llega algo mal formado, repite el comando.

### La respuesta de `L` y `C`

Cada `bk` es un byte en hexadecimal (dos dígitos, mayúsculas) con la fila Fk: el bit c es la
columna Ck, y **1 = imán** sobre esa casilla. La polaridad eléctrica (imán = columna en LOW) la
resuelve el firmware. Fk y Ck son los números de cable de `matriz-hall-nano.md`, los mismos que
Yk/Dk del 74HC138/74HC165, así que `matriz[k][c]` de la `MatrizCruda` de `logica/matriz.py` es
`bool(bk >> c & 1)` y `CASILLA_DE_CELDA_HALL` sigue valiendo.

| Situación | Respuesta |
|---|---|
| Tablero vacío | `M 00 00 00 00 00 00 00 00` |
| Posición inicial, si F0, F1, F6 y F7 son las filas del tablero llenas | `M FF FF 00 00 00 00 FF FF` |
| Una sola pieza en F2 / C3 | `M 00 00 08 00 00 00 00 00` |
| `C` con `F 5` encendida y piezas en C0 y C7 | `C 81` |

### La respuesta de `A`

Son lecturas del ADC del Nano: 0 = 0 V y 1023 = la tensión del USB (~5 V). Sirve para ver qué tan
abajo queda una columna con pieza, que es el riesgo principal de la v3: el Nano tiene garantizado
leer LOW por debajo de 0,3 × Vcc (**307**) y HIGH por encima de 0,6 × Vcc (614); en el medio no
está definido. Sin fila encendida, o sin pieza, las columnas dan ~1020 por la pull-up.

En el cableado normal solo C3–C7 (A0–A4) son analógicas; C0–C2 están en D10–D12 y salen como
`-`. Con el plan B salen las 8.

### La vista `V`

```
   01234567
F0 ##......
F1 ........
F2 ........
F3 ........
F4 ........
F5 ........
F6 ........
F7 ........
```

Una línea por fila (F0..F7) y un carácter por columna (C0..C7, de izquierda a derecha): `#` =
imán, `.` = vacío. Para cortarla alcanza con escribir cualquier cosa; por ejemplo `x`, que además
apaga las filas y contesta `OK X`.

### Tiempos

Un `L` con la espera por defecto tarda ~9 ms en barrer y ~2 ms en mandar la respuesta: alcanza
para unas 90 lecturas por segundo. Con el plan B cada columna se lee dos veces con el ADC (ver
abajo) y baja a unas 40. `L 50000` tarda 0,4 s.

## Del lado Pi: `io/matriz.py`

`io/matriz.py` habla con el firmware por el puerto serie (`pyserial`), con la misma API que tenía
el driver GPIO de la v2. Armar los comandos y decodificar las respuestas está en
`logica/matriz.py` ("Protocolo del Nano"), testeado en `tests/test_matriz.py`. Detalle (puerto,
errores, reintentos) en [`sensores.md`](./sensores.md).

| Función de `io/matriz.py` | Comando del Nano |
|---|---|
| `configurar_matriz()` | Abre el puerto a 115200 y descarta todo hasta `LISTO matriz-nano 1` (3 s; si no llega, `?` y 1 s más) |
| `liberar_matriz()` | `X` y cierra el puerto |
| `elegir_fila(k)` | `F k`, espera `OK Fk` |
| `leer_columnas()` | `C` |
| `leer_analogico()` | `A` |
| `apagar_filas()` | `X`, espera `OK X` |
| `leer_matriz(espera)` | `L <espera en µs, redondeada>` y decodifica los 8 bytes |
| `LectorMatriz`, `mostrar_en_vivo` | Ningún comando propio: usan `leer_matriz` |

`V` no lo usa la Pi: es solo para una persona en el monitor serie. Cada respuesta tiene plazo
(0,3 s más lo que tarda el barrido); si no llega o llega mal formada, se repite el comando hasta
3 veces. `medir` usa `F` una vez y `C` + `A` en bucle; `calibrar` y `mapear` solo usan
`leer_matriz` y `LectorMatriz`.

## Plan B: columnas analógicas

Si en la prueba con un driver la columna con pieza queda por encima de ~1,3 V
(`matriz-hall-nano.md`, "Plan B"), se recablean C0–C2 a A5–A7 y se compila con `PLAN_B=1`:

```bash
arduino-cli compile --upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328 \
  --build-property "compiler.cpp.extra_flags=-DPLAN_B=1" firmware/matriz-nano
```

(Con el Arduino IDE: cambiar `#define PLAN_B 0` por `1` al principio del sketch.) Así las 8
columnas se leen con `analogRead` y cuentan como imán por debajo de `UMBRAL_PLAN_B` (512, ~2,5 V,
por defecto). El protocolo no cambia.

Para elegir el umbral: llenar una fila, `F k` y `A`. El umbral va entre el valor más alto de las
columnas con pieza y el más bajo de las vacías; se cambia sumando `-DUMBRAL_PLAN_B=<valor>` a las
mismas flags (`"compiler.cpp.extra_flags=-DPLAN_B=1 -DUMBRAL_PLAN_B=450"`).

Cada lectura analógica se hace dos veces y se descarta la primera: el ADC carga un capacitor a
través de la pull-up (~35 kΩ, mucho para el ADC), y la primera lectura después de cambiar de
columna arrastra algo de la anterior. A6 y A7 no tienen pull-up interna (la guía les pone una de
10 kΩ externa) y el firmware no les hace `pinMode`.

## Prueba con el Nano suelto

Se puede hacer ya, sin nada armado: solo el Nano y el USB. Con un cable se simula una pieza
uniendo un pin de columna a GND (con las filas sin conectar, esa columna aparece "ocupada" en las
8 filas). **El cable a GND solo en pines de columna (D10, D11, D12, A0–A4), nunca en D2–D9**: son
salidas y con `F` o `L` quedan en 5 V; contra GND se quemaría el pin.

Subir el firmware, abrir el monitor y comprobar:

| Qué hacer | Tiene que dar |
|---|---|
| Abrir el monitor | `LISTO matriz-nano 1` (si no aparece, escribir `?`) |
| `?` | `LISTO matriz-nano 1` |
| `L` | `M 00 00 00 00 00 00 00 00` |
| Cable de D10 a GND, `L` | `M 01 01 01 01 01 01 01 01` |
| Cable de A4 a GND, `L` | `M 80 80 80 80 80 80 80 80` |
| Cable de A0 a GND, `C` | `C 08` |
| Sin cable, `A` | `A - - -` y cinco valores cerca de 1023 |
| Cable de A1 a GND, `A` | El segundo de los cinco valores cerca de 0 |
| `F 2`, multímetro entre D4 y GND | `OK F2`; D4 ≈ 5 V, D2 y D3 ≈ 0 V |
| `X` | `OK X`; D4 ≈ 0 V |
| `V`, y mover el cable entre columnas | Una grilla cada medio segundo que sigue al cable (la columna con cable, `#` en las 8 filas) |
| `x` | La vista se corta y contesta `OK X` |
| `z` | `ERR comando` |
| `F 9`, `F`, `C 3`, `L 60000` | `ERR argumento` |
| `L 12345678901234567` | `ERR largo` |
| `L 0` y `L 50000` | `M 00 …` (el segundo tarda casi medio segundo) |

Después viene la prueba con la matriz real, con un solo driver (F0), en
`hardware-docs/matriz-hall-nano.md`.

## Qué falta

- Probarlo enchufado a la Pi: `sensores matriz`, `medir`, `calibrar` y `mapear` (ver "Cómo
  probarlo" en [`sensores.md`](./sensores.md)). Con el Nano alimentado por el USB de la Pi,
  comparar los valores de `A` con los que daba en la notebook.
