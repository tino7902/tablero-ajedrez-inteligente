# Conexiones de la matriz de casillas (74HC138 + 74HC165)

Qué tiene que estar conectado con qué, pata por pata, y cómo verificarlo con el multímetro.
Funcionamiento de los chips en `funcionamiento_deteccion_de_casillas.md`; pruebas con la Pi
encendida en `software-docs/sensores.md`, "Cómo probarlo".

## Cómo medir

- **Pi apagada y desenchufada**, multímetro en continuidad.
- Medir **sobre la pata del chip**, no sobre la fila del protoboard o el zócalo: la pata puede no
  estar haciendo contacto aunque el cable esté bien.
- Revisar **todas** las patas, también las que van a un nivel fijo (GND o 3,3 V). Una entrada
  suelta puede flotar hacia el nivel correcto y hacer pasar una prueba de casualidad: así
  quedaron sin detectar las patas 10 y 15 del 165 hasta que la matriz solo leía una columna.

Pines de la Raspberry (número físico del header, igual que en `config.py`):

| Qué | Pines |
|---|---|
| 3,3 V | 1, 17 |
| GND | 6, 9, 14, 20, 25, 30, 34, 39 |
| 74HC138 | 37, 38, 40 |
| 74HC165 | 29, 31, 36 |

Las patas de los chips se cuentan mirándolos desde arriba con la muesca (o el punto) hacia
arriba: la pata 1 queda arriba a la izquierda, se baja por la izquierda hasta la 8 y se sube por
la derecha de la 9 a la 16.

## 74HC138 (selector de filas)

```
          ┌────╮╭────┐
   A    1 │    ╰╯    │ 16  Vcc
   B    2 │          │ 15  Y0
   C    3 │          │ 14  Y1
   E1   4 │ 74HC138  │ 13  Y2
   E2   5 │          │ 12  Y3
   E3   6 │          │ 11  Y4
   Y7   7 │          │ 10  Y5
   GND  8 │          │  9  Y6
          └──────────┘
```

| Pata | Nombre | Continuidad con | Si falla |
|---|---|---|---|
| 1 | A | Pin 38 de la Pi | Dos filas se leen iguales (`selector`: dos pasos activan la misma Y) |
| 2 | B | Pin 40 de la Pi | Ídem |
| 3 | C | Pin 37 de la Pi | Ídem |
| 4 | E1 (activa en bajo) | GND | Suelta puede flotar a LOW y funcionar de casualidad |
| 5 | E2 (activa en bajo) | GND | Ídem |
| 6 | E3 (activa en alto) | 3,3 V | Todas las Y quedan en HIGH: nunca se detecta nada |
| 7 | Y7 | Una fila del tablero | Esa fila no se detecta |
| 8 | GND | GND de la Pi | |
| 9 | Y6 | Una fila del tablero | Esa fila no se detecta |
| 10 | Y5 | Una fila del tablero | Ídem |
| 11 | Y4 | Una fila del tablero | Ídem |
| 12 | Y3 | Una fila del tablero | Ídem |
| 13 | Y2 | Una fila del tablero | Ídem |
| 14 | Y1 | Una fila del tablero | Ídem |
| 15 | Y0 | Una fila del tablero | Ídem |
| 16 | Vcc | 3,3 V (**nunca 5 V**) | El chip se alimenta de rebote por la pata 6 y las salidas inactivas dan ~2,8 V en vez de 3,3 V |

Los nombres de las patas 4, 5 y 6 cambian según el fabricante: Texas Instruments les dice G2A,
G2B y G1, y el esquemático de Proteus del proyecto las rotula E2, E3 y E1. Lo que importa es el
número: **4 y 5 a GND, 6 a 3,3 V**.

**Filas:** cada salida Y tiene continuidad con los cátodos (el lado de la banda) de los 8 diodos
de una fila del tablero. El orden no importa, porque lo resuelve `calibrar`, pero cada Y tiene que
ir a una fila distinta y ninguna fila puede quedar sin su Y.

## 74HC165 (lector de columnas)

```
            ┌────╮╭────┐
  SH/LD   1 │    ╰╯    │ 16  Vcc
  CLK     2 │          │ 15  CLK INH
  D4      3 │          │ 14  D3
  D5      4 │ 74HC165  │ 13  D2
  D6      5 │          │ 12  D1
  D7      6 │          │ 11  D0
  QH̄      7 │          │ 10  SER
  GND     8 │          │  9  QH
            └──────────┘
```

| Pata | Nombre | Continuidad con | Si falla |
|---|---|---|---|
| 1 | SH/LD | Pin 29 de la Pi (y **no** con GND) | Si queda fija en LOW, siempre se lee D7 |
| 2 | CLK | Pin 31 de la Pi | No desplaza: solo se ve la columna de D7 y marca la fila entera |
| 3 | D4 | Una columna del tablero | Esa columna no se detecta, o queda siempre ocupada |
| 4 | D5 | Una columna del tablero | Ídem |
| 5 | D6 | Una columna del tablero | Ídem |
| 6 | D7 | Una columna del tablero | Ídem |
| 7 | QH̄ (salida invertida) | **Nada** | Si se lee de acá en vez de la 9, todo sale invertido |
| 8 | GND | GND de la Pi | La salida queda sin manejar: `matriz` muestra todo en `#` |
| 9 | QH | Pin 36 de la Pi | Ídem |
| 10 | SER | GND | `lector` falla el desplazamiento. En `matriz` no influye, pero una entrada suelta mete ruido |
| 11 | D0 | Una columna del tablero | Esa columna no se detecta, o queda siempre ocupada |
| 12 | D1 | Una columna del tablero | Ídem |
| 13 | D2 | Una columna del tablero | Ídem |
| 14 | D3 | Una columna del tablero | Ídem |
| 15 | CLK INH | GND | Suelta bloquea el reloj: igual que la pata 2 |
| 16 | Vcc | 3,3 V (**nunca 5 V**) | La salida queda sin manejar. Con 5 V, la pata 9 le manda 5 V a la Pi |

Las patas 2 y 15 del 165 son intercambiables (el chip las combina internamente), así que si
están cruzadas entre sí funciona igual. Las patas 1 y 2 no: si los cables de los pines 29 y 31
están cruzados, siempre se lee D7.

**Columnas:** cada entrada D tiene continuidad con una pata de cada uno de los 8 reeds de una
columna del tablero. El orden no importa, porque lo resuelve `calibrar`. En el esquemático, la
columna de más a la izquierda entra en D7 y la de más a la derecha, en D0.

## Resistencias pull-up (8 × 10 kΩ)

Cada una tiene una punta a 3,3 V y la otra a una columna (una entrada D del 165).

**Verificación:** con el multímetro en resistencia, entre cada pata D del 165 y el 3,3 V tiene que
dar **~10 kΩ**. Si da infinito, la pull-up de esa columna está suelta y la entrada flota.

## Celdas (reed + diodo)

Cada casilla es un reed en serie con un diodo: **columna → reed → diodo → fila**. El cátodo del
diodo (la banda) va hacia la fila, es decir, hacia la salida Y del 138.

**Verificación de una celda:** multímetro en modo diodo, punta roja en la columna (pata D del 165)
y punta negra en la fila (pata Y del 138):

| Medición | Tiene que dar | Si no |
|---|---|---|
| Sin imán | `OL` | Lo mismo que con imán: el reed quedó cerrado (pegado) o hay un puente de estaño. Un poco más que con imán y variando (por ejemplo 0,9–1 V): el reed cierra a medias o hay una fuga sobre él, y en `matriz` esa celda parpadea |
| Con el imán sobre el reed | ~0,6–0,8 V (en el prototipo, 0,775 V) | `OL`: el reed no cierra o el diodo está al revés. ~0 V: el diodo está en corto o falta |
| Con el imán y las puntas invertidas | `OL` | ~0,6–0,8 V: el diodo está al revés. ~0 V: el diodo está en corto o falta |

Si una celda da mal, medir el reed solo: en resistencia, directo entre sus dos patas. Sin imán
tiene que dar `OL` y con imán ~0 Ω. Una de sus patas solo va a su diodo, así que los chips no
influyen en esta medición.

## Lo que **no** tiene que tener continuidad

En modo continuidad, con la Pi apagada y sin imanes cerca, no tiene que sonar en ninguno de estos
casos:

- [ ] 3,3 V con GND.
- [ ] Dos salidas Y del 138 entre sí.
- [ ] Dos columnas (entradas D del 165) entre sí.
- [ ] La pata 1 del 165 con GND.
- [ ] La pata 7 del 165 con cualquier cosa.
- [ ] El pin 31 de la Pi con la pata 1 del 165, porque eso significa que SH/LD y CLK están cruzados.
