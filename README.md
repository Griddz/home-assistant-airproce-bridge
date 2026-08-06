# AirProce Socket B Bridge for Home Assistant

A Home Assistant custom integration for an AirProce purifier whose USR serial-to-network module exposes a second transparent TCP connection (Socket B).

The integration runs the tested Socket B bridge inside Home Assistant, publishes MQTT Discovery entities, and keeps the purifier's official Socket A/cloud connection unchanged.

> Protocol support has been verified on an AirProce AI-600. Other models may use different frames.

## Entities

- `fan` — power, six manual speeds, `auto`, and `sleep`
- temperature sensor
- humidity sensor
- PM2.5 sensor
- VOC sensor

The fan and all sensors become unavailable when Socket B is disconnected or when the watchdog detects a silent half-open TCP connection.

## Architecture

```text
Socket A -> AirProce official cloud (official app remains available)

Socket B -> Home Assistant TCP listener
             -> protocol parser and controls
             -> MQTT broker
             -> Home Assistant MQTT Discovery entities
```

This first custom-integration release deliberately preserves the MQTT bridge behavior that was tested before packaging it for Home Assistant. The resulting fan and sensor entities are MQTT-discovered entities and therefore appear under the Home Assistant MQTT integration, while this custom integration owns the Socket B listener and bridge configuration.

## Requirements

1. Home Assistant 2026.6 or later is recommended.
2. The Home Assistant MQTT integration must already be connected to the same broker entered in this integration.
3. Home Assistant must be reachable from the USR module on the configured Socket B listening port.
4. Only one program can listen on that TCP port. Stop the previous standalone bridge first.

## Installation

### HACS custom repository

After the repository is published:

1. Open HACS.
2. Add this repository as a custom repository of type **Integration**.
3. Install **AirProce Socket B Bridge**.
4. Restart Home Assistant.

### Manual installation

Copy:

```text
custom_components/airproce_bridge
```

into:

```text
/config/custom_components/airproce_bridge
```

Restart Home Assistant.

## Configuration

Open:

```text
Settings -> Devices & services -> Add integration
```

Search for **AirProce Socket B Bridge**.

The setup form contains:

### USR module and purifier

- device name
- purifier model
- stable device ID
- USR module IP address
- USR web port
- USR username and password (`admin` / `admin` defaults)
- Socket B listening address and port

The USR credentials are used only to verify access to the embedded web interface. Version 0.1.0 does **not** change USR settings automatically.

Configure Socket B manually as TCP Client:

```text
Server: <Home Assistant LAN IP>
Port:   <configured listening port, default 9001>
```

Keep Socket A pointed at the official AirProce cloud.

### MQTT broker

- broker host and port
- username and password
- base topic
- Discovery prefix

Use a unique base topic and stable device ID for every purifier.

### Watchdog

The purifier normally reports state approximately every 15 seconds. The default watchdog waits 45 seconds without a valid state frame before sending a status query. It retries once, then closes the stale Socket B session and publishes `offline`.

## Control behavior

- Manual speeds are 1 through 6.
- `auto` and `sleep` are fan preset modes.
- Setting a manual speed clears the preset mode.
- The first control byte for `auto` and `sleep` uses the latest valid fan context. This preserves the observed protocol behavior where the sleep frame depends on the current fan state.
- After a command, the bridge waits for the command ACK, immediately sends a status query, and publishes the confirmed device state.

## Migration from the standalone script

1. Stop the old script or service.
2. Confirm TCP port 9001 is free on the Home Assistant host.
3. Install and configure this integration.
4. Change USR Socket B to the Home Assistant LAN IP and the configured port.
5. Verify that the new entities update.
6. Remove any old retained MQTT Discovery topics if the previous object IDs were different.

## Privacy and security

The repository contains no private LAN addresses, MAC addresses, MQTT usernames, MQTT passwords, room names, or user-specific credentials. Credentials are stored in the Home Assistant config entry. USR/MQTT hosts, usernames, passwords, and the MQTT base topic are redacted from diagnostics.

Do not publish exported Home Assistant config entries or diagnostic files without reviewing them first.

## Known limitations

- USR parameters are not automatically changed because the embedded web form/HTTP API varies by module and firmware.
- The control frames are reverse engineered and verified on one AI-600 firmware family.
- This release creates MQTT entities rather than native platform entities to preserve the already-tested bridge behavior.

## License

MIT
