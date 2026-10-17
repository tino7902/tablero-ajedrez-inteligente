# Matriz Hall con Arduino Nano (versión actual)

Cómo se arma la detección de casillas: 64 sensores Hall en una matriz de 8 × 8, leídos por un
Arduino Nano que le pasa el estado del tablero a la Raspberry Pi por USB. Un NPN por fila maneja
la corriente. Reemplaza al 74HC138 y al 74HC165 de las versiones anteriores; por qué se cambió y
qué se descartó, en `historial-deteccion.md`.

**Estado:** decidida el 2026-10-17. **No está armada ni probada todavía**, y el firmware del Nano
y el lector del lado Pi tampoco están escritos (ver "Software" al final).

Versión web de esta guía, con esquemas dibujados y checklist para tildar, para el equipo de
hardware: https://claude.ai/artifact/Y4zNzHhxoWoaWzvcRwRLkU

## Cómo funciona

```
 Raspberry Pi ── USB ── Arduino Nano ── D2…D9 ──► 8 × NPN ──► GND de cada fila ─┐
                          │   ▲                                                 │
                          │   └── D10 D11 D12 A0…A4 ◄── 8 columnas (diodos) ◄── Matriz Hall 8 × 8
                          └── 5V ──────────────────────────────────────────────► Vcc de los 64 Hall
```

El Nano enciende una fila por vez (pone su pin en HIGH, el NPN conecta a GND el bus de GND de esa
fila), espera ~1 ms a que los Hall arranquen, lee las 8 columnas y pasa a la siguiente. Una
columna en LOW es un imán sobre esa casilla. Le manda la matriz a la Pi por el puerto serie.

| Estado | Pin del Nano | NPN | Bus GND de la fila |
|---|---|---|---|
| Fila elegida | HIGH (5 V) | conduce (~4 mA de base) | ~0,1 V: fila encendida |
| Fila no elegida | LOW | cortado | flota: fila apagada |

En una fila apagada, la pull-up del KY-003 deja OUT en 5 V y el diodo no conduce, así que esa
fila no carga las columnas.

## Materiales

| Componente | Cantidad | Detalle |
|---|---|---|
| Arduino Nano (ATmega328P) | 1 | Original o clon, con su cable USB |
| Transistor NPN | 8 | BC547, BC337, 2N3904, 2N2222 o S8050 |
| Resistencia 1 kΩ | 8 | Base de cada NPN |
| Resistencia 10 kΩ | 8 | Entre base y GND de cada NPN |
| Hall A3144 / KY-003 | 64 | Ya están |
| Diodo | 64 | Ya están (1N4148). Si hay que comprar, mejor Schottky: BAT85, BAT43, 1N5819 |
| Resistencia 10 kΩ (opcional) | 8 | Pull-up externa de cada columna a 5 V, si las internas no alcanzan |

Salen de la placa: el 74HC138, el 74HC165 y las 8 pull-ups de 10 kΩ que iban a 3,3 V.

## Driver de una fila

```
 pin del Nano ──[ 1 kΩ ]──┬── B ┐
                          │      NPN    C ── bus GND de los 8 Hall de la fila
                       [10 kΩ]          E ── GND del Nano
                          │
                         GND
```

- La de 1 kΩ limita la corriente del pin a ~4 mA. **Sin ella se quema el pin o el transistor.**
- La de 10 kΩ deja el NPN apagado mientras el Nano arranca o si se desconecta.
- Por fila pasan como mucho ~60 mA (Hall + LEDs de los KY-003); todos los NPN de la tabla
  aguantan 100 mA o más.

## Una celda

Es la misma celda de la v2 (`celdas-hall.md`). Cambian dos cosas: el Vcc va a 5 V y el GND va al
bus de su fila en vez de a la pata del 138.

```
                     ┌─────────┐
  5 V del Nano ─ Vcc ┤         │
                     │  A3144  ├─ OUT ──┤◄── columna Ck (pin del Nano)
  bus GND fila ─ GND ┤         │
                     └─────────┘
  Diodo: la banda (cátodo) hacia OUT, el ánodo hacia la columna.
```

Pinout, polaridad (solo detecta el polo sur, cara con letras hacia arriba) y sensores que no
sirven: igual que en `celdas-hall.md`, "Pinout".

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

El pin del Nano va por la de 1 kΩ a la base del NPN de esa fila; su colector, al bus GND de la fila.

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
| 5V | Riel de Vcc de los 64 Hall (y las pull-ups externas, si se usan) |
| GND | Emisores de los 8 NPN y las 8 resistencias de 10 kΩ de base |
| USB | A un puerto USB de la Pi: alimenta el Nano y transmite los datos |
| D13, A5 | Libres (D13 tiene el LED de la placa: no usarlo como entrada) |
| D0, D1 | **No conectar**: los usa el USB |
| A6, A7 | No sirven: solo analógicos |

## Transistores

El orden de las patas cambia según el modelo (cara plana al frente, patas abajo, de izquierda a
derecha):

| Modelo | Patas |
|---|---|
| BC547, BC548, BC337 | C · B · E |
| 2N3904, 2N2222A (TO-92), S8050 | E · B · C |

**Medir siempre antes de soldar** (hay clones con otro orden). Multímetro en modo diodo: la base
es la pata que, con la punta roja, marca ~0,6–0,7 V contra las otras dos (si pasa con la negra, es
PNP y no sirve). De las otras dos, la que marca unas centésimas más es el emisor.

## Pasos de armado

1. **Desconectar la matriz de la Raspberry**: sacar los cables a los pines 29, 31, 36, 37, 38 y
   40 de la Pi y el de 3,3 V de los Hall. Al terminar, la Pi solo se conecta al Nano por USB.
2. **Sacar el 138, el 165 y sus 8 pull-ups**, marcando antes cada cable de fila (F0–F7) y de
   columna (C0–C7) con la tabla de arriba.
3. **Pasar el riel de Vcc de los Hall al pin 5V del Nano.** Nada queda conectado a 3,3 V.
4. **Armar los 8 drivers NPN**, midiendo las patas de cada transistor antes de soldarlo.
5. **Conectar cada bus de GND de fila al colector de su NPN.**
6. **Montar el Nano** (mejor en zócalo o tira hembra) y conectar filas y columnas.
7. **Unir los GND**: emisores y resistencias de 10 kΩ al GND del Nano.
8. **Verificar sin alimentar** antes de enchufar el USB.

**No hacer:** conectar los Hall o las columnas a pines de la Pi (los 5 V pueden quemarla);
conectar una base sin su resistencia de 1 kΩ; usar D0 o D1; conectar el GND de los Hall directo
a GND (esa fila quedaría siempre encendida); alimentar el Nano por VIN con el USB conectado.

## Verificación sin alimentar

USB desenchufado, multímetro en continuidad o modo diodo.

| Medición | Tiene que dar | Si no |
|---|---|---|
| Cables de la matriz ↔ pines de la Pi | Ninguno conectado | Desconectarlos |
| Vcc de cada Hall ↔ 5V del Nano | Continuidad | El Hall no tiene alimentación |
| GND de cada Hall ↔ colector del NPN de su fila | Continuidad | Ese Hall no se enciende con su fila |
| GND de cada Hall ↔ GND del Nano | **Sin** continuidad | Ese Hall está a GND directo: su fila nunca se apaga |
| Colector de cada NPN ↔ colectores de las otras filas | Sin continuidad | Buses de fila unidos |
| Emisor de cada NPN ↔ GND del Nano | Continuidad | Ese NPN nunca conduce |
| Pin D2–D9 ↔ base de su NPN | ~1 kΩ | Falta o está mal la resistencia |
| Base de cada NPN ↔ GND | ~10 kΩ (algo menos) | Falta la pull-down |
| Modo diodo, roja en la columna, negra en OUT de un Hall | ~0,5–0,7 V (1N4148) o ~0,2–0,4 V (Schottky) | `OL`: diodo al revés o cortado |
| Mismas puntas invertidas | `OL` | ~0,5 V: diodo al revés |
| 5V ↔ GND del Nano | Sin corto | Corto en el riel de alimentación |

## Prueba con una fila

Primero con **una sola fila** armada (F0, en D2), antes de soldar las 8. Sketch de prueba para
el Arduino IDE (placa `Arduino Nano`; en los clones, procesador `ATmega328P (Old Bootloader)` si
no sube con el normal), monitor serie a 115200 baudios:

```cpp
// Prueba de la matriz Hall con el Nano: imprime 8 líneas (F0..F7) de 8 caracteres (C0..C7).
// '#' = imán detectado, '.' = vacío.
const uint8_t FILAS[8] = {2, 3, 4, 5, 6, 7, 8, 9};
const uint8_t COLUMNAS[8] = {10, 11, 12, A0, A1, A2, A3, A4};
const unsigned int ESPERA_ENCENDIDO_US = 1000;  // igual que HALL_ESPERA_ENCENDIDO

void setup() {
  Serial.begin(115200);
  for (uint8_t f = 0; f < 8; f++) {
    pinMode(FILAS[f], OUTPUT);
    digitalWrite(FILAS[f], LOW);
  }
  for (uint8_t c = 0; c < 8; c++) pinMode(COLUMNAS[c], INPUT_PULLUP);
}

void loop() {
  for (uint8_t f = 0; f < 8; f++) {
    digitalWrite(FILAS[f], HIGH);
    delayMicroseconds(ESPERA_ENCENDIDO_US);
    for (uint8_t c = 0; c < 8; c++) {
      Serial.print(digitalRead(COLUMNAS[c]) == LOW ? '#' : '.');
    }
    digitalWrite(FILAS[f], LOW);
    Serial.println();
  }
  Serial.println();
  delay(500);
}
```

(No está compilado todavía.) Para medir con el multímetro, dejar F0 fija: en `loop()`, solo
`digitalWrite(FILAS[0], HIGH);` y la lectura de columnas.

| Medición con F0 encendida (negra en GND del Nano) | Tiene que dar | Si no |
|---|---|---|
| Pin D2 | ~5 V | El sketch no corre o D2 está en corto |
| Base del NPN de F0 | ~0,7 V | 0 V: falta la de 1 kΩ. ~5 V: transistor mal puesto |
| Colector del NPN (bus GND de F0) | < 0,3 V | Patas cambiadas o falta corriente de base |
| Entre GND y Vcc de un Hall de F0 | ≥ 4,5 V | Riel de 5 V mal, o el colector no baja |
| Columna de una casilla de F0, sin pieza | ~5 V | Columna en corto o Hall dañado |
| La misma columna, con pieza | < 1,5 V | Diodo al revés, imán con el norte abajo o Hall de cara |

Repetir la última **con la fila llena de piezas** (cada LED de KY-003 suma corriente).

## Problemas frecuentes

| Síntoma en el monitor serie | Causa probable |
|---|---|
| Una fila siempre en `########` | El bus GND de esa fila toca GND directo, o el NPN está en corto |
| Una columna siempre en `#` | La columna toca GND, o un Hall de esa columna tiene el GND a GND directo |
| Una fila nunca detecta | NPN con las patas cambiadas, falta la de 1 kΩ, o el bus no llega al colector |
| Una casilla nunca detecta | Diodo al revés o cortado, Hall de cara, o imán con el norte abajo |
| Una pieza aparece también en otra fila | Falta el diodo de algún Hall de esa columna |
| Casillas que parpadean | Imán débil o lejos. Con cables largos, pull-ups externas de 10 kΩ a 5 V. Si con pieza queda cerca de 1,5 V, diodos Schottky |
| Todo en `........` | Falta el 5 V en el riel, o la unión de GND entre emisores y Nano |
| Nada en el monitor serie | Velocidad distinta de 115200, puerto equivocado, o falta el driver CH340 del clon |

## Software (pendiente)

Nada de esto está escrito todavía:

- **Firmware del Nano**: barre las 8 filas y manda la matriz a la Pi por el puerto serie
  (`/dev/ttyUSB0` en los clones con CH340, `/dev/ttyACM0` en otros).
- **Lado Pi**: `io/matriz.py` deja de manejar GPIO y pasa a leer el puerto serie (con `pyserial`
  como dependencia nueva). Si entrega la matriz en el mismo formato, `io/sensores.py` y
  `logica/matriz.py` casi no cambian.
- **Herramientas**: `medir`, `calibrar` y `mapear` de `io/sensores.py` manejan los pines
  directamente; hay que adaptarlas o moverlas al firmware.
- **`config.py`**: los `PIN_MATRIZ_*` quedan sin uso cuando cambie `io/matriz.py`.
