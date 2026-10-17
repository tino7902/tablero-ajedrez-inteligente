# Redes wifi en la Raspberry

Cómo agregar, priorizar y borrar redes wifi en la Raspberry Pi del tablero, sin perder la
sesión SSH mientras tanto.

## Cómo está configurada

- Sistema: Debian 13 (trixie).
- La red la maneja **NetworkManager**, con el comando `nmcli`. `dhcpcd` y `wpa_supplicant.conf`
  no se usan: editar `/etc/wpa_supplicant/wpa_supplicant.conf` no sirve de nada.
- Cada red guardada es un archivo en `/etc/NetworkManager/system-connections/`, con la clave
  adentro (solo lo lee root).
- La Pi se conecta sola a cualquier red guardada que esté al alcance. Si hay varias, elige la de
  mayor `autoconnect-priority`.
- Por SSH: `ssh magnus@magnus.local` (mDNS) o por IP. **La IP cambia según la red** (en
  `CDR FPUNA` es `192.168.8.139`).

Redes guardadas al 2026-10-17: `CDR FPUNA`, `Retamozo` (y `Wired connection 1`, el cable).

## Ver qué hay

```bash
nmcli connection show            # redes guardadas (la activa tiene DEVICE wlan0)
nmcli device                     # estado de wlan0
nmcli device wifi list           # redes que la Pi ve ahora (SSID, señal, seguridad)
```

La columna `SECURITY` de `nmcli device wifi list` dice qué tipo de red es: `WPA2` / `WPA3` es
con clave común, `WPA2 802.1X` es con usuario y contraseña (red "Enterprise", típica de
universidades).

## Agregar una red sin desconectarse

`nmcli connection add` **guarda** la red sin conectarse, así que la sesión SSH no se corta. La
Pi la va a usar sola cuando esté en su alcance.

La clave se pide con `read -s` para que no quede en el historial de la terminal ni se vea en
pantalla. Cambiá `NOMBRE DE LA RED` por el SSID exacto (mayúsculas y espacios incluidos).

### Red con clave común (WPA2/WPA3 Personal, la de una casa o un celular)

```bash
SSID='NOMBRE DE LA RED'
read -rsp 'Clave del wifi: ' PSK; echo
sudo nmcli connection add type wifi con-name "$SSID" ifname wlan0 ssid "$SSID" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" connection.autoconnect yes
unset PSK
```

### Red oculta (no aparece en `nmcli device wifi list`)

Igual que la anterior, agregando `wifi.hidden yes` al final del `nmcli connection add`.

### Red con usuario y contraseña (WPA2 Enterprise / 802.1X)

```bash
SSID='NOMBRE DE LA RED'
read -rp 'Usuario: ' USUARIO
read -rsp 'Contraseña: ' CLAVE; echo
sudo nmcli connection add type wifi con-name "$SSID" ifname wlan0 ssid "$SSID" \
    wifi-sec.key-mgmt wpa-eap 802-1x.eap peap 802-1x.phase2-auth mschapv2 \
    802-1x.identity "$USUARIO" 802-1x.password "$CLAVE" connection.autoconnect yes
unset CLAVE
```

`peap` + `mschapv2` es lo más común. Si no conecta, preguntá en la red cuál usan (a veces es
`ttls` + `pap`) y cambialo con `nmcli connection modify` (ver más abajo).

### Confirmar que se guardó

```bash
nmcli connection show
```

Tiene que aparecer la red nueva, con `DEVICE` en `--` si no está activa.

## Probarla

Conectarse a la red nueva **corta la sesión SSH**, porque la Pi deja la red actual. Dos formas:

- **Lo más seguro**: llevar la Pi a donde está la red nueva y prenderla. Se conecta sola. Si la
  clave estaba mal, no se conecta a nada y hay que entrar con teclado y pantalla (ver "Sin SSH").
- **Probar desde acá**, si la red nueva también está al alcance:

  ```bash
  sudo nmcli connection up 'NOMBRE DE LA RED'
  ```

  La sesión se cuelga. Si la notebook está en la misma red nueva, volvé a entrar con
  `ssh magnus@magnus.local`. Si la conexión falla, NetworkManager vuelve sola a otra red
  guardada al rato.

### Encontrar la Pi en la red nueva

1. `ssh magnus@magnus.local`, desde una compu en la misma red. Funciona en la mayoría de las
   redes de casa. En redes de universidad a veces está bloqueado.
2. Si no, la IP: en la página del router (lista de dispositivos, buscá `magnus`), o con teclado
   y pantalla en la Pi: `ip -4 addr show wlan0`.

Ojo: algunas redes de universidad aíslan a los dispositivos entre sí, y la notebook no ve a la
Pi aunque estén en la misma red. En ese caso, compartir internet desde el celular y conectar a
los dos ahí.

## Prioridad entre redes

Si hay varias redes guardadas al alcance, la Pi elige la de mayor prioridad (por defecto todas
tienen `0`):

```bash
sudo nmcli connection modify 'NOMBRE DE LA RED' connection.autoconnect-priority 10
nmcli -f NAME,AUTOCONNECT-PRIORITY connection show    # para revisar
```

## Cambiar o borrar una red

```bash
# Cambiar la clave
read -rsp 'Clave nueva: ' PSK; echo
sudo nmcli connection modify 'NOMBRE DE LA RED' wifi-sec.psk "$PSK"; unset PSK

# Borrarla
sudo nmcli connection delete 'NOMBRE DE LA RED'
```

**No borres la red que está activa** (la que tiene `DEVICE wlan0`) estando por SSH: se corta
la sesión y la Pi puede quedar sin ninguna red a la que conectarse.

## Sin SSH (teclado y pantalla en la Pi)

Si la Pi quedó sin ninguna red que funcione, conectale teclado y un monitor HDMI, iniciá sesión
como `magnus` y corré:

```bash
sudo nmtui
```

Es un menú en la terminal: "Activate a connection" para elegir una red, "Edit a connection"
para agregar o corregir una. Los comandos `nmcli` de arriba también funcionan desde ahí.
