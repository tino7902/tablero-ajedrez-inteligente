# Matriz Hall con Arduino Nano (versión actual)

Cómo se arma la detección de casillas: 64 sensores Hall A3144 en una matriz de 8 × 8, leídos por
un Arduino Nano que le pasa el estado del tablero a la Raspberry Pi por USB. Un NPN por fila
maneja la corriente. Reemplaza al 74HC138 y al 74HC165 de las versiones anteriores; por qué se
cambió y qué se descartó, en `historial-deteccion.md`.

**Estado:** decidida el 2026-10-17. Armada y probada: con el cableado normal (plan A, columnas
digitales) y el firmware de `firmware/matriz-nano/`, el Nano detecta las 64 casillas desde el
monitor serie de la notebook. El lector del lado Pi (`io/matriz.py`) está escrito pero todavía
no se probó con el Nano enchufado a la Pi (ver "Software" al final).

Versión web de esta guía, con esquemas dibujados y checklist para tildar, para el equipo de
hardware: https://claude.ai/artifact/Y4zNzHhxoWoaWzvcRwRLkU (su fuente es `matriz-hall-nano.html`,
en esta misma carpeta; si se cambia uno, cambiar el otro).

## Cómo funciona

```
 Raspberry Pi ── USB ── Arduino Nano ── D2…D9 ──► 8 × NPN ──► bus de cada fila ──┐
                          │   ▲                                                  │
                          │   └── D10 D11 D12 A0…A4 ◄── 8 columnas (salidas directas) ◄── Matriz Hall 8 × 8
                          └── 5V ───────────────────────────────────────────────► Vcc de los 64 Hall
```

El Nano enciende una fila por vez (pone su pin en HIGH y el NPN conecta a GND el bus de esa fila),
espera ~1 ms a que los Hall arranquen, lee las 8 columnas y pasa a la siguiente. Una columna en
LOW es un imán sobre esa casilla. Hace ese recorrido cada vez que la Pi se lo pide (muchas veces por
segundo) y le contesta la matriz por el puerto serie.

| Estado | Pin del Nano | NPN | Bus de la fila |
|---|---|---|---|
| Fila elegida | HIGH (5 V) | conduce (~9 mA de base) | ~0,1–0,3 V: fila encendida |
| Fila no elegida | LOW | cortado | flota: fila apagada |

## Materiales

| Componente | Cantidad | Detalle |
|---|---|---|
| Arduino Nano (ATmega328P) | 1 | Original o clon, con su cable USB |
| Transistor NPN | 8 | **BC337, 2N2222 o S8050.** No BC547, BC548 ni 2N3904 (ver "Transistores") |
| Resistencia 470 Ω | 8 | Base de cada NPN |
| Resistencia 10 kΩ | 8 | Entre base y GND de cada NPN |
| A3144 + diodo | 64 | Ya soldados, con el diodo en el GND de cada Hall |

Salen de la placa: el 74HC138, el 74HC165 y las 8 pull-ups de 10 kΩ que iban a 3,3 V. Las
columnas usan las pull-ups internas del Nano.

## Una celda: así están soldadas

Las 64 celdas ya están armadas así y **no se cambian**:

```
                     ┌─────────┐
  5 V del Nano ─ Vcc ┤         │
                     │  A3144  ├─ OUT ── columna Ck (directo al pin del Nano)
                 GND ┤         │
                     └────┬────┘
                          ▼  diodo: ánodo en el GND del Hall,
                          │  banda (cátodo) hacia el bus de fila
                   bus de fila Fk ── colector del NPN de la fila
```

Esto es distinto de lo que planteaba la primera versión de esta guía (diodo en la salida, GND
directo al bus). Qué implica:

| Efecto | Valor | Consecuencia |
|---|---|---|
| El diodo suma ~0,6–0,8 V en el GND de cada Hall | ~4,3 V; ~3,9 V con la fila llena | Tensión de cada Hall, por debajo de los 4,5 V del A3144 original. Los clones suelen funcionar igual: **hay que comprobarlo** en la prueba |
| Los otros 7 Hall de la columna le pasan corriente al que detecta | ~20 mA | En las filas apagadas, el GND de cada Hall flota y su consumo sale por un diodo interno hacia su salida, que está unida a la columna. Dentro de lo que aguanta la salida del A3144 (~25 mA), pero obliga a usar un NPN más fuerte |
| Nivel bajo de la columna con pieza | ~1,1–1,3 V | El Nano tiene garantizado leer LOW hasta 1,5 V. Si queda más alto, plan B |
| Piezas fantasma | no hay | El diodo del GND impide que un Hall de una fila apagada encuentre camino a GND |

Pinout (cara plana con letras al frente, patas abajo, de izquierda a derecha): **1 Vcc, 2 GND,
3 OUT**. Solo detecta el **polo sur** contra la cara con letras: esa cara va hacia arriba y todos
los imanes con el sur hacia abajo. **No puentear el diodo del GND**: sin él aparecerían piezas
fantasma.

## Driver de una fila

```
 pin del Nano ──[ 470 Ω ]──┬── B ┐
                           │      NPN    C ── bus de la fila (cátodos de sus 8 diodos)
                        [10 kΩ]          E ── GND del Nano
                           │
                          GND
```

- **Hasta ~200 mA por fila:** los 8 Hall consumen ~35 mA, y cada Hall que detecta recibe ~20 mA
  de los otros 7 de su columna, que también bajan por el NPN. Con la fila llena (posición
  inicial): 35 + 8 × 20 ≈ 200 mA.
- La de 470 Ω deja pasar ~9 mA del pin del Nano (máximo recomendado: 20 mA), lo necesario para
  saturar el NPN con 200 mA. **Sin ella se quema el pin o el transistor.**
- La de 10 kΩ deja el NPN apagado mientras el Nano arranca o si se desconecta.

## Tabla de conexiones

Cada fila y columna **conserva el número que tenía con el 138 y el 165**, para que el mapeo
celda → casilla del software (`CASILLA_DE_CELDA_HALL` en `config.py`) siga valiendo.

| Fila | Pin del Nano | Antes iba a |
|---|---|---|
| F0 | D2 | Y0 del 138 (pata 15) |
| F1 | D3 | Y1 (pata 14) |
| F2 | D4 | Y2 (pata 13) |
| F3 | D5 | Y3 (pata 12) |
| F4 | D6 | Y4 (pata 11) |
| F5 | D7 | Y5 (pata 10) |
| F6 | D8 | Y6 (pata 9) |
| F7 | D9 | Y7 (pata 7) |

El pin del Nano va por la de 470 Ω a la base del NPN de esa fila; su colector, al bus de la fila.

| Columna | Pin del Nano | Antes iba a |
|---|---|---|
| C0 | D10 | D0 del 165 (pata 11) |
| C1 | D11 | D1 (pata 12) |
| C2 | D12 | D2 (pata 13) |
| C3 | A0 | D3 (pata 14) |
| C4 | A1 | D4 (pata 3) |
| C5 | A2 | D5 (pata 4) |
| C6 | A3 | D6 (pata 5) |
| C7 | A4 | D7 (pata 6) |

| Otros pines del Nano | Conexión |
|---|---|
| 5V | Riel de Vcc de los 64 Hall |
| GND | Emisores de los 8 NPN y las 8 resistencias de 10 kΩ de base |
| USB | A un puerto USB de la Pi: alimenta el Nano y transmite los datos |
| D13 | Libre (tiene el LED de la placa: no usarlo como entrada) |
| A5, A6, A7 | Libres; se usan en el plan B |
| D0, D1 | **No conectar**: los usa el USB |

## Transistores

| Modelo | Corriente máxima | ¿Sirve? | Patas (cara plana al frente, patas abajo) |
|---|---|---|---|
| BC337 | 800 mA | Sí | C · B · E |
| 2N2222A (TO-92) | 600 mA | Sí | E · B · C |
| S8050 | 500 mA o más | Sí | E · B · C |
| BC547, BC548 | 100 mA | **No** | — |
| 2N3904 | 200 mA | **No**: al límite | — |

**Medir siempre antes de soldar** (hay clones con otro orden). Multímetro en modo diodo: la base
es la pata que, con la punta roja, marca ~0,6–0,7 V contra las otras dos (si pasa con la negra, es
PNP y no sirve). De las otras dos, la que marca unas centésimas más es el emisor.

## Pasos de armado

1. **Desconectar la matriz de la Raspberry**: sacar los cables a los pines 29, 31, 36, 37, 38 y
   40 de la Pi y el de 3,3 V de los Hall. Al terminar, la Pi solo se conecta al Nano por USB.
2. **Sacar el 138, el 165 y sus 8 pull-ups**, marcando antes cada cable de fila (F0–F7) y de
   columna (C0–C7) con la tabla de arriba.
3. **Pasar el riel de Vcc de los Hall al pin 5V del Nano.** Nada queda conectado a 3,3 V.
4. **Armar los 8 drivers NPN** (BC337, 2N2222 o S8050, con 470 Ω), midiendo las patas de cada
   transistor antes de soldarlo.
5. **Conectar cada bus de fila al colector de su NPN.**
6. **Montar el Nano** (mejor en zócalo o tira hembra) y conectar filas y columnas.
7. **Unir los GND**: emisores y resistencias de 10 kΩ al GND del Nano.
8. **Verificar sin alimentar** antes de enchufar el USB.

**No hacer:** conectar los Hall o las columnas a pines de la Pi (los 5 V pueden quemarla); usar
BC547, BC548 o 2N3904; conectar una base sin su resistencia; agregar pull-ups externas en las
columnas (le suman corriente al Hall que detecta); alimentar los Hall con más de 5 V (sus salidas
van directo al Nano); usar D0 o D1; conectar el bus de una fila directo a GND; alimentar el Nano
por VIN con el USB conectado.

## Verificación sin alimentar

USB desenchufado, multímetro en continuidad o modo diodo.

| Medición | Tiene que dar | Si no |
|---|---|---|
| Cables de la matriz ↔ pines de la Pi | Ninguno conectado | Desconectarlos |
| Vcc de cada Hall ↔ 5V del Nano | Continuidad | El Hall no tiene alimentación |
| Modo diodo: roja en el GND de un Hall, negra en el colector del NPN de su fila | ~0,5–0,7 V | `OL`: diodo cortado o al revés. ~0 V: diodo en corto |
| Mismas puntas invertidas | `OL` | ~0,5 V: diodo al revés |
| GND de cada Hall ↔ GND del Nano | **Sin** continuidad | Ese Hall está a GND directo |
| OUT de cada Hall ↔ pin del Nano de su columna | Continuidad | Columna cortada |
| Cada columna ↔ otras columnas y ↔ GND | Sin continuidad | Columnas en corto |
| Colector de cada NPN ↔ colectores de las otras filas | Sin continuidad | Buses de fila unidos |
| Emisor de cada NPN ↔ GND del Nano | Continuidad | Ese NPN nunca conduce |
| Pin D2–D9 ↔ base de su NPN | ~470 Ω | Falta o está mal la resistencia |
| Base de cada NPN ↔ GND | ~10 kΩ (algo menos) | Falta la pull-down |
| 5V ↔ GND del Nano | Sin corto | Corto en el riel de alimentación |

## Prueba con un solo driver

Primero con **un solo driver** (F0, en D2), antes de soldar los otros 7. La medición que decide
si el plan sirve es la de la **fila llena de piezas**.

Se usa el firmware definitivo del Nano (`firmware/matriz-nano/` del repo), que también sirve para
las pruebas: se le escriben comandos desde el monitor serie y contesta. Cómo subirlo, todos los
comandos y una prueba previa con el Nano suelto (sin matriz) en `software-docs/firmware-nano.md`;
si el equipo de hardware no tiene el repo, el de software le pasa el Nano ya cargado. Monitor
serie a 115200 baudios; al abrirlo tiene que aparecer `LISTO matriz-nano 1`.

Para esta prueba alcanza con tres comandos:

| Comando | Qué hace |
|---|---|
| `V` | Muestra la grilla en vivo cada medio segundo: una línea por fila (F0..F7), un carácter por columna (C0..C7), `#` = imán. Se corta escribiendo cualquier cosa |
| `F 0` | Deja F0 encendida fija para medir con el multímetro (barriendo, cada fila está encendida 1/8 del tiempo y el multímetro marca un promedio). `X` la apaga |
| `A` | Con `F 0` puesta: el nivel de las columnas C3–C7 de 0 (0 V) a 1023 (~5 V). Por debajo de 307 el Nano lee el imán sin dudar. C0–C2 salen como `-` (sus pines no miden tensión): esas se miden con el multímetro |

Llenar F0 con 8 piezas y escribir `F 0`:

| Medición con F0 llena (negra en GND del Nano) | Tiene que dar | Si no |
|---|---|---|
| Pin D2 | ~5 V | No se escribió `F 0`, el firmware no está cargado o D2 está en corto |
| Base del NPN de F0 | ~0,7–0,9 V | 0 V: falta la de 470 Ω. ~5 V: transistor mal puesto |
| Colector del NPN (bus de F0) | < 0,3 V | No se satura: revisar modelo, patas y la de 470 Ω |
| Entre GND (negra) y Vcc (roja) de un Hall de F0 | ≥ 3,8 V | Riel de 5 V mal o el colector no baja. Si da bien y no detecta, ese Hall no arranca con esa tensión |
| Una columna de F0, con pieza (o `A`, C3–C7) | < 1,3 V (`A`: < 270) | 1,3–1,5 V (`A`: 270–307): funciona justo. Más de 1,5 V (`A`: más de 307): plan B |
| La misma columna, sin pieza | ~5 V (`A`: ~1020) | Columna en corto o Hall dañado |
| `C` | `C FF` (las 8 columnas de F0 con imán) | Ver "Problemas frecuentes" |

Después `X` y `V`: tiene que aparecer `F0 ########` y las otras filas en `........`. Si todo da
bien, armar los otros 7 drivers y repetir con cada fila llena (`F 1`, `F 2`, …).

## Plan B: columnas como entradas analógicas

Solo si la columna con pieza queda por encima de ~1,3 V. Con `analogRead`, el umbral lo elige el
firmware en vez de depender del umbral de la entrada digital:

- Recablear 3 columnas: C0 de D10 a **A5**, C1 de D11 a **A6**, C2 de D12 a **A7**. C3–C7 quedan
  en A0–A4.
- Agregar una pull-up de 10 kΩ a 5 V en A6 y en A7 (no tienen pull-up interna).
- Volver a subir el firmware compilado con `PLAN_B=1` (comando en `software-docs/firmware-nano.md`;
  con el Arduino IDE, cambiar `#define PLAN_B 0` por `1` al principio del sketch). No hay que
  tocar nada más del código.
- El umbral por defecto es 512 (~2,5 V). Para ajustarlo: llenar una fila, `F k` y `A` (con el
  plan B mide las 8 columnas); va entre el valor más alto con pieza y el más bajo sin pieza.
- El barrido baja a unas 40 lecturas del tablero por segundo, que alcanza.

## Problemas frecuentes

| Síntoma en el monitor serie (con `V`) | Causa probable |
|---|---|
| Una fila siempre en `########` | El bus de esa fila toca GND directo, o el NPN está en corto |
| Una columna siempre en `#` | El cable de columna toca GND |
| Una fila nunca detecta | NPN con las patas cambiadas, falta la de 470 Ω, o el bus no llega al colector |
| Una casilla nunca detecta | Diodo del GND cortado o al revés, Hall de cara, imán con el norte abajo, o ese Hall no arranca con ~4 V |
| Una pieza aparece también en otra fila | El diodo de algún Hall de esa columna está en corto o puenteado |
| Con una pieza detecta, con la fila llena falla | El NPN no se satura (modelo débil o base mayor a 470 Ω), o el LOW de la columna supera el umbral: plan B |
| Casillas que parpadean | Imán débil o lejos, o la columna con pieza queda cerca de 1,5 V: plan B |
| Todo en `........` | Falta el 5 V en el riel, o la unión de GND entre emisores y Nano |
| Nada en el monitor serie | Velocidad distinta de 115200, puerto equivocado, o falta el driver CH340 del clon |
| No aparece `LISTO matriz-nano 1` al abrir el monitor | Escribir `?`. Si contesta, el monitor se abrió después del arranque; si no, el firmware no está cargado |
| `ERR comando` o `ERR argumento` | El comando se escribió mal (por ejemplo `F 8`: las filas van de 0 a 7) |

## Software

- **Firmware del Nano** (`firmware/matriz-nano/`): probado con la matriz completa. Barre las
  filas cuando la Pi se lo pide y contesta la matriz por el puerto serie (`/dev/ttyUSB0` en los
  clones con CH340, `/dev/ttyACM0` en otros). Protocolo, comandos y cómo subirlo en
  `software-docs/firmware-nano.md`.
- **Lado Pi**: `io/matriz.py` habla con el firmware por el puerto serie (`pyserial`) y entrega la
  matriz en el mismo formato que en la v2. `sensores matriz`, `calibrar` y `mapear` siguen igual;
  `medir F0` deja una fila fija con el comando `F` y muestra `C` y `A` en vivo. El puerto se
  autodetecta (o se fija en `NANO_PUERTO` de `config.py`) y el usuario tiene que estar en el grupo
  `dialout`. Detalle en `software-docs/sensores.md`; falta probarlo enchufado a la Pi.
