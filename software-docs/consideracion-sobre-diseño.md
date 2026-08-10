# Consideraciones de diseño para la interfaz (a futuro)

Notas a tener en cuenta cuando se diseñe la interfaz real sobre la pantalla táctil (selector
de modo, configuración del reloj, indicadores de partida, etc.), recopiladas a partir de lo
que se va aprendiendo probando el hardware. No es una spec cerrada — se va a ir ampliando a
medida que aparezcan más restricciones del hardware real.

## Precisión táctil limitada → UI grande y espaciada

Al probar `probar_boton()` (ver [`pantalla.md`](./pantalla.md#precisión-táctil-a-tener-en-cuenta-en-el-diseño-de-la-ui))
se observó que el touch XPT2046 registra bien el contacto, pero la posición reportada no
siempre coincide con el punto físico tocado: hubo toques dentro del área visual de un botón
de prueba que no se contaron como tales porque la coordenada del evento cayó fuera de su
`Rect`. Todavía no se investigó la causa (calibración del panel, el `rotate=180` del overlay,
o algo inherente a este panel resistivo).

Hasta que eso se calibre o se mida el offset real, cualquier UI táctil de este proyecto debe:

- **Usar elementos grandes**, no botones chicos — el objetivo es tolerar el desfasaje
  observado, no depender de precisión de pixel.
- **Dejar separación generosa entre elementos interactivos contiguos**, para que un toque
  con offset caiga en el elemento tocado (o en ningún elemento) y no en el vecino.
- **Evitar UI densa**, por ejemplo un botón por casilla en una grilla de 8x8 sobre los
  480x320 del panel, sin antes medir cuánto es el offset real.

Esto descarta, al menos por ahora, cualquier diseño de interfaz que dependa de zonas táctiles
finas (por ejemplo, seleccionar una casilla del tablero tocándola directamente en la
pantalla). Los selectores de modo, botones de reloj, etc. deberían pensarse como pocas
opciones grandes en vez de grillas densas.
