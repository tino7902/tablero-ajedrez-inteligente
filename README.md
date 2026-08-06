# Tablero de Ajedrez Inteligente

Tablero de ajedrez físico con sensores por casilla y LEDs, controlado íntegramente
por una **Raspberry Pi 3B**. Valida movimientos, mantiene el estado de la partida
y puede jugar contra Stockfish en modo vs-máquina — todo corriendo en un único
dispositivo, sin hardware ni proceso adicional.

## Estructura del proyecto
```
tablero-ajedrez-inteligente/
├── tablero/ # Paquete Python (gestionado con uv)
│ └── src/tablero/
│ ├── main.py # Entry point / orquestador
│ ├── config.py # Pines GPIO y configuración general
│ ├── io/ # Lectura de sensores (74HC165) y control de LEDs (WS2812B)
│ ├── logica/ # Reglas del juego y estado del tablero (python-chess)
│ ├── motor/ # Integración con Stockfish (modo vs-máquina)
│ └── web/ # Dashboard/API de estado (a futuro)
├── hardware/ # Esquemáticos y documentación de electrónica
│ └── schematics/
└── docs/ # Documentación adicional del proyecto
```

## Prerrequisitos

| Herramienta | Uso |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Gestión de Python (entornos y dependencias) |
| Git | Control de versiones |
| [GitHub CLI (gh)](https://cli.github.com/) | Gestión del repositorio (opcional) |
| Stockfish | Motor de ajedrez para el modo vs-máquina |

> Los módulos de `tablero/src/tablero/io/` (sensores y LEDs) requieren acceso a
> GPIO real y solo funcionan corriendo en la Raspberry Pi. El resto del proyecto
> (`logica/`, `motor/`) se puede desarrollar y testear en cualquier máquina.

## Instalación

### Linux

```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Stockfish
sudo apt install stockfish        # Debian/Ubuntu (Raspberry Pi OS)
# o, en Arch/CachyOS:
sudo pacman -S stockfish

# GitHub CLI (opcional)
sudo apt install gh               # Debian/Ubuntu
# o
sudo pacman -S github-cli         # Arch/CachyOS
gh auth login
```

### Windows

```powershell
# uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Stockfish
winget install Stockfish.Stockfish
# o descargar el binario desde https://stockfishchess.org/download/ y agregarlo al PATH

# GitHub CLI (opcional)
winget install --id GitHub.cli
gh auth login
```

## Puesta en marcha

```bash
git clone https://github.com/<tu-usuario>/tablero-ajedrez-inteligente.git
cd tablero-ajedrez-inteligente/tablero
uv sync
uv run tablero
```
