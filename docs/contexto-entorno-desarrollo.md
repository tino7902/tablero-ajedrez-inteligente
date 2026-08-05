# Contexto: Entorno de Desarrollo — Tablero de Ajedrez Inteligente

Este documento complementa a `contexto-tablero-ajedrez-inteligente.md` (que cubre el diseño del producto/arquitectura) y se enfoca específicamente en el **setup del entorno de programación**, decisiones de tooling y troubleshooting realizado.

## Contexto del desarrollador

- Sistema operativo: **CachyOS Linux** (basado en Arch).
- Window manager: **niri**.
- Editor de texto: **Zed**.
- Rol en el proyecto: encargado de la parte de programación (firmware + companion). Tiene compañeros que se encargan de la parte de electrónica (carpeta `hardware/` del repo reservada para ellos).
- Preferencia declarada: usar **uv** en vez de pip/pipx para todo lo relacionado a Python, por preferencia personal de plataforma.

## Decisión: PlatformIO en vez de Arduino IDE

Se descartó Arduino IDE 2.x (versión AppImage) porque en una conversación previa se detectó un fallo de arranque por incompatibilidad entre el JIT de V8 (Electron) y el kernel hardened de CachyOS. La solución adoptada fue migrar completamente a **PlatformIO Core (CLI)** para el desarrollo de firmware del ESP32, evitando así cualquier dependencia de Electron.

Ventajas de PlatformIO sobre Arduino IDE para este proyecto:
- Genera `compile_commands.json` automáticamente, dando autocompletado real (vía clangd) en Zed.
- Manejo de dependencias por proyecto en `platformio.ini`, versionado y aislado (a diferencia de Arduino IDE que mezcla librerías globalmente).
- Soporta múltiples entornos/boards en un mismo proyecto (útil dado que el board ESP32 exacto todavía no está 100% definido por el equipo de electrónica).

## Gestión de paquetes Python: uv

Se usa **uv** (Astral) en lugar de pip/pipx en todo el proyecto:
- Instalación: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Para el companion: `uv init --package` (crea estructura de paquete Python), `uv add <paquete>` (agrega dependencias y genera `uv.lock`, que sí se versiona en git — a diferencia de `.venv/`, que no se versiona).
- Para instalar herramientas globales tipo CLI (como PlatformIO, que es un paquete de Python): `uv tool install <paquete>`, equivalente al uso que se le daría a `pipx`.

### Problema encontrado: PlatformIO + `uv tool install` sin pip

`uv tool install platformio` crea un entorno aislado sin `pip` (uv no lo necesita para sí mismo), pero PlatformIO internamente invoca `pip` para instalar algunos paquetes de sus toolchains. Esto causó una instalación a medias de `tool-esptoolpy` (error `No module named pip`, seguido de `MissingPackageManifestError`).

**Solución aplicada:**
```bash
uv tool uninstall platformio
uv tool install platformio --with pip
```
El flag `--with pip` incluye pip dentro del entorno aislado que uv le crea a PlatformIO.

## Problema encontrado: resolución DNS del mirror de PlatformIO

Al correr `pio project init --board esp32dev`, PlatformIO intentaba descargar toolchains desde un mirror de terceros (`usc1.contabostorage.com`, un proveedor de storage llamado Contabo usado como CDN/mirror por el registro de paquetes de PlatformIO) y fallaba con `NameResolutionError` / `Name not found` (NXDOMAIN) — no timeout, sino que el resolver DNS activamente no encontraba el dominio.

**Diagnóstico:**
- `resolvectl query usc1.contabostorage.com` → fallaba.
- `resolvectl query github.com` → funcionaba sin problemas.
- Conclusión: no era un problema de DNS roto en general, sino de ese dominio puntual — coincide con reportes conocidos de la comunidad de que ese dominio de Contabo queda bloqueado por algunos resolvers DNS (posiblemente por estar en listas de filtrado/seguridad, ya que fue usado en el pasado en campañas de phishing).

**Solución elegida (mínimamente invasiva, sin tocar configuración de DNS del sistema):**
1. Resolver la IP del dominio usando un DNS público sin cambiar el resolver del sistema:
   ```bash
   sudo pacman -S bind   # para tener `dig`
   dig @1.1.1.1 +short usc1.contabostorage.com
   ```
2. Agregar una entrada estática en `/etc/hosts` con la IP obtenida (cualquiera de las que devuelva `dig`, ya que son servidores balanceados equivalentes):
   ```
   <IP>    usc1.contabostorage.com
   ```
3. Limpiar el paquete que había quedado a medio instalar: `rm -rf ~/.platformio/packages`
4. Volver a correr `pio project init --board esp32dev`.

Se evaluaron pero se descartaron (por ser más invasivas) alternativas como cambiar el DNS del sistema con `resolvectl dns` o `nmcli`.

Nota para el futuro: si PlatformIO necesita otro subdominio de Contabo (ej. `sin1` o `eu2` según región), puede requerir el mismo procedimiento para ese hostname.

## Estructura del proyecto (monorepo)

```
tablero-ajedrez-inteligente/
├── firmware/                    # Proyecto PlatformIO (ESP32)
│   ├── platformio.ini           # generado por `pio project init`
│   ├── src/main.cpp             # creado a mano
│   ├── include/                 # generado
│   ├── lib/                     # generado
│   ├── test/                    # generado
│   ├── .pio/                    # generado por `pio run` — no se versiona
│   └── compile_commands.json    # generado por `pio run -t compiledb`
├── companion/                   # Servidor Python (python-chess + Stockfish)
│   ├── pyproject.toml           # generado por `uv init --package`
│   ├── .python-version          # generado por `uv init`
│   ├── uv.lock                  # generado por `uv add` — SÍ se versiona
│   ├── .venv/                   # generado por `uv add` — NO se versiona
│   ├── src/companion/           # generado por `uv init --package`
│   └── tests/                   # creado a mano
├── hardware/                    # Para el equipo de electrónica
│   └── schematics/
├── docs/                        # Documentación del proyecto (incluye este archivo y el de contexto general)
├── .gitignore
└── README.md
```

Se armó siguiendo el flujo:
```bash
mkdir tablero-ajedrez-inteligente && cd tablero-ajedrez-inteligente
mkdir -p hardware/schematics docs

mkdir firmware && cd firmware
pio project init --board esp32dev
pio run -t compiledb
cd ..

mkdir companion && cd companion
uv init --package
uv add python-chess paho-mqtt
cd ..

git init
git add .
git commit -m "Estructura inicial del proyecto"
gh repo create tablero-ajedrez-inteligente --private --source=. --remote=origin
git push -u origin main
```

## Repositorio GitHub

- Gestionado con **GitHub CLI** (`gh`), instalado vía `sudo pacman -S github-cli`, autenticado con `gh auth login`.
- Repo creado como privado con `gh repo create tablero-ajedrez-inteligente --private --source=. --remote=origin`.
- Flujo de trabajo acordado: rama `main` protegida, trabajo en ramas `feature/nombre-cosa`, un issue por componente/tarea (sensores, LEDs, reloj, comunicación, integración python-chess), pull request + review antes de mergear.

## Comunicación ESP32 ↔ Companion: MQTT

Se decidió usar **MQTT** como protocolo de comunicación entre el ESP32 y el companion device, en vez de un socket TCP simple, por dar mejor manejo de reconexión nativo y mayor flexibilidad para escalar a futuros dispositivos adicionales (ej. un posible módulo de cámara separado, o una interfaz web de estado de partida).

- **Cliente Python**: librería `paho-mqtt` (Eclipse Foundation), agregada como dependencia del companion vía `uv add paho-mqtt`.
- **Cliente en el ESP32**: librería `PubSubClient` (lado Arduino/C++), a integrar en el firmware.
- **Broker MQTT**: **Mosquitto**, corriendo localmente (`sudo pacman -S mosquitto`, `sudo systemctl enable --now mosquitto`), puerto default 1883.

Esquema de comunicación acordado (topics tentativos, sujetos a definir en detalle durante la implementación):
```
ESP32 detecta movimiento → publica en "tablero/movimiento" → { "origen": "e2", "destino": "e4" }
Companion (suscripto a "tablero/movimiento") → valida con python-chess
                                              → si es modo vs-máquina, calcula respuesta con Stockfish
                                              → publica en "tablero/led" → qué casillas encender
ESP32 (suscripto a "tablero/led") → recibe el mensaje → controla los LEDs correspondientes
```

## Permisos de puerto serie (CachyOS/Arch)

Los drivers USB-serial (CP2102/CH340, chips típicos de placas ESP32) ya vienen incluidos en el kernel de Linux (`cdc_acm`, `ch341`), no requieren instalación aparte. Solo se necesitó agregar el usuario a los grupos correspondientes para tener permisos de acceso al dispositivo:
```bash
sudo usermod -aG uucp,dialout $USER
# requiere relogueo para tomar efecto
```

## Setup del editor (Zed)

- **Para firmware/**: extensión `clangd`, que usa el `compile_commands.json` generado por `pio run -t compiledb` para dar autocompletado e IntelliSense de las librerías de Arduino/ESP-IDF. También se agregó extensión de sintaxis TOML para editar `platformio.ini`.
- **Para companion/**: extensión `Pyright`/`Python`, apuntando al intérprete del `.venv` generado por uv (`companion/.venv/bin/python`), detectado automáticamente por Zed al abrir la carpeta, o fijado explícitamente en `.zed/settings.json`.

## Lista de prerrequisitos consolidada

| Herramienta | Uso | Instalación |
|---|---|---|
| PlatformIO Core | Compilar/flashear firmware ESP32 | `uv tool install platformio --with pip` |
| uv | Gestión de Python (entornos y dependencias) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Stockfish | Motor de ajedrez (modo vs-máquina) | `sudo pacman -S stockfish` |
| Mosquitto | Broker MQTT | `sudo pacman -S mosquitto` |
| GitHub CLI (gh) | Gestión del repositorio | `sudo pacman -S github-cli` |
| bind (dig) | Diagnóstico DNS (usado para el workaround del mirror) | `sudo pacman -S bind` |

## Entregables generados en esta etapa

- `README.md` en la raíz del repo: estructura del proyecto, prerrequisitos, guía de clonado e inicio, convención de flujo de trabajo con ramas/issues.
- `docs/contexto-tablero-ajedrez-inteligente.md`: contexto de arquitectura y decisiones de diseño del producto (documento previo).
- Este documento (`contexto-entorno-desarrollo.md`): contexto del setup del entorno de desarrollo.

## Estado actual

Firmware: entorno PlatformIO ya funcionando (compilación y toolchain resueltos tras el workaround de DNS). Companion: en proceso de setup (dependencias `python-chess` y `paho-mqtt` agregadas vía uv, broker Mosquitto pendiente de dejar corriendo y probar la conexión end-to-end). No hay código de lógica de negocio implementado todavía — la etapa actual es puramente de tooling e infraestructura del proyecto.
