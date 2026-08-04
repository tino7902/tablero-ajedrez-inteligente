# Tablero de Ajedrez Inteligente

Tablero de ajedrez electrónico que detecta movimientos mediante sensores de final de carrera bajo cada casilla, indica movimientos legales con LEDs, funciona como reloj de ajedrez configurable, y permite jugar humano vs humano o humano vs máquina.

Ver `docs/contexto-tablero-ajedrez-inteligente.md` para el detalle completo de arquitectura y decisiones de diseño.

## Estructura del proyecto

```
tablero-ajedrez-inteligente/
├── firmware/          # Proyecto PlatformIO (ESP32) — sensores, LEDs, reloj, comunicación
│   ├── platformio.ini
│   ├── src/
│   ├── include/
│   └── lib/
├── companion/         # Servidor Python — python-chess (legalidad) + Stockfish (motor)
│   ├── pyproject.toml
│   ├── uv.lock
│   └── src/companion/
├── hardware/          # Esquemáticos, PCB y BOM (a cargo del equipo de electrónica)
│   └── schematics/
└── docs/              # Documentación del proyecto
```

## Prerrequisitos

| Herramienta | Uso | Instalación (Arch/CachyOS) |
|---|---|---|
| [PlatformIO Core](https://platformio.org/) | Compilar y flashear el firmware del ESP32 | `uv tool install platformio --with pip` |
| [uv](https://docs.astral.sh/uv/) | Gestión de entorno y dependencias de Python | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Stockfish](https://stockfishchess.org/) | Motor de ajedrez para el modo vs-máquina | `sudo pacman -S stockfish` |
| [Mosquitto](https://mosquitto.org/) | Broker MQTT para la comunicación ESP32 ↔ companion | `sudo pacman -S mosquitto` |
| [GitHub CLI](https://cli.github.com/) | Gestión del repositorio | `sudo pacman -S github-cli` |

También necesitás permisos sobre el puerto serie del ESP32:
```bash
sudo usermod -aG uucp,dialout $USER
# relogueate para que tome efecto
```

## Cómo empezar

### 1. Cloná el repositorio

```bash
git clone https://github.com/<tu-usuario>/tablero-ajedrez-inteligente.git
cd tablero-ajedrez-inteligente
```

### 2. Setup del firmware (ESP32)

```bash
cd firmware
pio run                    # compila y descarga dependencias/toolchain
pio run -t compiledb       # genera compile_commands.json para autocompletado (clangd)
pio run -t upload          # flashea al ESP32 conectado por USB
pio device monitor         # abre el monitor serie
```

### 3. Setup del companion (Python)

```bash
cd companion
uv sync                    # instala las dependencias desde uv.lock
sudo systemctl enable --now mosquitto   # levanta el broker MQTT local
uv run python -m companion   # (ajustar según el entry point definido)
```

### 4. Editor (Zed)

Instalá las extensiones `clangd` (para `firmware/`) y `Pyright`/`Python` (para `companion/`) desde el panel de extensiones de Zed. Con `compile_commands.json` generado y el `.venv` de uv detectado, el autocompletado debería andar en ambas partes del proyecto.

## Flujo de trabajo

- `main` protegida — el trabajo se hace en ramas `feature/nombre-cosa` (ej. `feature/lectura-sensores`, `feature/reloj-ajedrez`).
- Un issue por componente/tarea en GitHub Issues.
- Pull request + review antes de mergear a `main`.
