# `logica/registro.py` — registro de partidas

Deja rastro de lo que se juega, en dos niveles y con dos ventanas distintas:

- **Últimas 15 partidas**: un PGN estándar por partida, con los movimientos legales de
  cada jugador y el resultado.
- **Últimas 5 partidas**: además, un log detallado de *todo* lo que pasó — qué movimiento
  intentó cada jugador y cuándo, si se aceptó o se bloqueó y por qué, cada pulsación del
  botón del reloj y cómo quedó el reloj en cada cambio de turno.

Los límites viven en `config.py` (`MAX_PARTIDAS_REGISTRADAS`, `MAX_DETALLES_REGISTRADOS`).

Lo alimenta [`logica/partida.py`](./partida.md), no la interfaz, así que registra
por igual las partidas simuladas por terminal ([`simulacion.md`](./simulacion.md)) y las
que juegue el tablero físico el día que la pantalla pase por `Partida`. Por eso el módulo
vive en `logica/` y no depende de hardware.

## Archivos

Todo cuelga de `config.DIRECTORIO_REGISTROS` (= `tablero/registros/`), que está en
`.gitignore`: son datos de ejecución, igual que la calibración táctil.

```
tablero/registros/
├── partidas/20260830-201455.pgn   ← 15 más recientes
└── detalle/20260830-201455.log    ← 5 más recientes
```

El id es la fecha y hora de inicio (`AAAAMMDD-HHMMSS`); dos partidas del mismo segundo se
desambiguan con un sufijo (`-2`). Un archivo por partida, así rotar es simplemente borrar
los más viejos (por fecha de modificación) y no hay que reescribir un archivo compartido.

Para verlas todas juntas en un visor de ajedrez (Lichess, SCID, ChessBase), la
concatenación de PGNs ya es un PGN multi-partida válido:

```bash
cat tablero/registros/partidas/*.pgn > partidas.pgn
```

## Formato del PGN

```
[Event "Simulación por terminal"]
[Site "Tablero de ajedrez inteligente"]
[Date "2026.08.30"]
[Round "-"]
[White "Blancas"]
[Black "Negras"]
[Result "1-0"]
[TimeControl "180"]
[Termination "jaque mate"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
```

- `Event` sale del modo (`simulacion`, `pvp`, `vs_magnus`).
- `TimeControl` es el tiempo por jugador en segundos.
- `Termination` es `jaque mate`, `tablas`, `tiempo` o `abandonada`.
- Los movimientos van en SAN inglés, que es lo que define el estándar PGN, aunque se hayan
  tipeado en español.
- Una partida sin terminar queda con `Result "*"` y `Termination "abandonada"`.

## Formato del log detallado

```
[2026-08-30 20:14:55.123] partida iniciada — modo=simulacion tiempo=5min notacion=es
[2026-08-30 20:14:58.001] (t+00:03) blancas intenta 'e4' → ACEPTADO e4 (peón e2→e4) ⏱ B 04:57 · N 05:00
[2026-08-30 20:15:01.400] (t+00:06) negras  intenta 'Cf6' → BLOQUEADO (BLOQUEADO_FALTA_RELOJ): blancas todavía no presionaron su botón del reloj
[2026-08-30 20:15:02.100] (t+00:07) botón negras → IGNORADO (IGNORADO_COLOR): el botón de negras no hace nada: el turno es de blancas
[2026-08-30 20:15:03.000] (t+00:08) botón blancas → TURNO PASADO a negras ⏱ B 04:53 · N 05:00
[2026-08-30 20:19:55.000] (t+05:00) tiempo agotado: blancas ⏱ B 00:00 · N 04:12
[2026-08-30 20:19:55.010] partida finalizada — 0-1 (tiempo)
```

Cada línea lleva la hora absoluta y `t+MM:SS` desde el inicio de la partida. El estado del
reloj (`⏱ B … · N …`) se anota en cada movimiento aceptado, en cada cambio de turno y
cuando se acaba el tiempo.

## API

| Método | Qué hace |
|---|---|
| `RegistroPartida(directorio, *, modo, segundos_por_jugador, max_partidas, max_detalles, id_partida, extras_cabecera)` | Crea los dos archivos, rota los viejos y escribe la cabecera |
| `.anotar_jugada(resultado, reloj, board)` | Una línea de log; si la jugada fue aceptada, reescribe también el PGN |
| `.anotar_boton(resultado, reloj)` | Una línea de log por pulsación (haya pasado el turno o no) |
| `.anotar_tiempo_agotado(reloj)` | Una línea de log cuando se acaba el tiempo |
| `.cerrar(resultado, motivo, board)` | Resultado final en el PGN y en el log; idempotente |
| `.ruta_pgn` / `.ruta_log` / `.id` | Dónde quedó todo |

`anotar_*` recibe los mismos `ResultadoJugada`/`ResultadoBoton` que devuelve `Partida`,
así el formateo vive acá y `Partida` solo avisa lo que pasó.

## Decisiones de diseño

- **Escritura incremental**: el log se anexa línea por línea y el PGN se reescribe entero
  después de cada movimiento aceptado (son unos pocos KB). Un `Ctrl+C`, un cierre a mitad
  de partida o un corte de luz en la Raspberry dejan el registro completo hasta la última
  jugada, no un archivo vacío.
- **Un archivo por partida, no uno consolidado**: hace trivial tanto la escritura
  incremental como la rotación, y `cat` reconstruye la vista consolidada cuando hace falta.
- **PGN en vez de un formato propio**: lo genera `chess.pgn` (ya es dependencia), se abre
  en cualquier visor de ajedrez y no hay que mantener un parser propio.
- **Se rota después de crear los archivos de la partida nueva**, no antes: rotar primero
  puede liberar el id que se acaba de descartar por colisión y hacer que dos partidas se
  pisen.

## Tests

`tablero/tests/test_registro.py` — sin hardware, todo sobre el `tmp_path` de pytest.
Cubre el PGN releído con `chess.pgn.read_game`, el detalle del log, la escritura
incremental, la partida abandonada y la rotación 15/5. Ver [`testing.md`](./testing.md).
