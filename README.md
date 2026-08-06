# AirProce Socket B Bridge for Home Assistant

**English** | [简体中文](README.zh-CN.md)

A Home Assistant custom integration for AirProce air purifiers whose internal USR serial-to-network module exposes a second transparent TCP connection (Socket B).

The integration keeps the official Socket A/cloud connection and AirProce app working, while Socket B provides local state reporting and control through Home Assistant.

AirProce product website: [https://airproce.net/](https://airproce.net/)

Verified models:

- **AI-300**
- **AI-600**

Other models may use different protocol frames and have not yet been verified.

## Essential prerequisite

> **This integration can only be used when the purifier's internal USR transparent-transmission management page is accessible.**

Before installing the integration, open the following address in a browser:

```text
http://<PURIFIER_IP>:80
```

Common default credentials are:

```text
Username: admin
Password: admin
```

After login, the page should show a USR IoT transparent-transmission interface containing both Socket A and Socket B settings. If this page cannot be opened, the credentials are unknown, or Socket B is not available, this integration cannot use the method documented here.

The following privacy-safe illustration is redrawn from a verified USR management page. The exact layout may vary slightly by firmware version:

![USR transparent transmission web interface](docs/usr-web-interface.svg)

## Entities

The integration creates the following entities through MQTT Discovery:

- `fan` — power, six manual speeds, `auto`, and `sleep`
- temperature sensor
- humidity sensor
- PM2.5 sensor
- VOC sensor

The fan and all sensors become unavailable when Socket B disconnects or when the watchdog detects a silent half-open TCP connection.

## Architecture

```text
Socket A -> AirProce official cloud
             official app remains available

Socket B -> Home Assistant TCP listener
             -> protocol parser and controls
             -> MQTT broker
             -> Home Assistant MQTT Discovery entities
```

This custom integration preserves the MQTT bridge behavior that was verified in the previous standalone bridge. The custom integration owns the Socket B listener, USR/MQTT configuration, and bridge process. The resulting fan and sensor entities are MQTT-discovered entities and therefore appear under Home Assistant's MQTT integration.

## Requirements

1. Home Assistant 2026.6 or later is recommended.
2. The Home Assistant MQTT integration must already be connected to the same broker entered in this integration.
3. The USR module must be able to reach the Home Assistant LAN address and configured Socket B listening port.
4. Only one process can listen on a TCP port. Stop the previous standalone bridge before installing this integration.
5. You must be able to log in to the purifier's USR management page and configure Socket B manually.

## Installation

### HACS custom repository

1. Open HACS.
2. Add the following custom repository and select **Integration** as the category:

```text
https://github.com/Griddz/home-assistant-airproce-bridge
```

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

Search for:

```text
AirProce Socket B Bridge
```

### USR module and purifier

The setup form contains:

- device name
- purifier model
- stable device ID
- USR module IP address
- USR web port
- USR username and password, commonly `admin` / `admin`
- Socket B listening address and port

The USR credentials are used only to verify access to the embedded web interface. Version 0.1.0 does **not** change USR settings automatically.

Configure Socket B manually as:

```text
Protocol: TCP-Client
Server:   <HOME_ASSISTANT_LAN_IP>
Port:     <configured listening port, default 9001 for the first purifier>
```

Keep Socket A pointed at the official AirProce cloud, for example:

```text
Protocol: TCP-Client
Server:   d2.airproce.com
Port:     8800
```

### MQTT broker

The form also contains:

- broker host and port
- MQTT username and password
- MQTT base topic
- Discovery prefix

Every purifier must use a unique MQTT base topic and a unique stable device ID.

### Watchdog

The purifier normally reports state approximately every 15 seconds. The default watchdog waits 45 seconds without a valid state frame before sending a status query. It retries once and, if no valid reply arrives, closes the suspected stale Socket B session and publishes `offline`.

## Adding a second or additional purifier

For every additional purifier, the following four values **must be different**:

| Setting | First purifier example | Second purifier example |
|---|---|---|
| Stable device ID | `airproce_ai600_bedroom` | `airproce_ai300_livingroom` |
| USR module IP | `192.168.1.112` | `192.168.1.113` |
| Socket B listening port | `9001` | `9002` |
| MQTT base topic | `airproce/bedroom` | `airproce/livingroom` |

Multiple purifiers may share:

- the same Home Assistant LAN address
- the same MQTT broker
- the same MQTT username and password
- the same Discovery prefix
- the same default USR username and password

Configure the second purifier's Socket B as:

```text
Protocol: TCP-Client
Server:   <THE_SAME_HOME_ASSISTANT_LAN_IP>
Port:     9002
```

Do not reuse the same Socket B listening port or MQTT base topic. A duplicate port prevents the second integration instance from starting; a duplicate base topic causes states and commands from both purifiers to overwrite each other.

Use distinct device names such as `AirProce Bedroom` and `AirProce Living Room`. Avoid changing a stable device ID after setup because Home Assistant may then create a new set of entities.

## Control and state behavior

- Manual speeds are 1 through 6.
- `auto` and `sleep` are fan preset modes.
- Setting a manual speed clears the preset mode.
- The first control byte for `auto` and `sleep` uses the latest valid fan context. This preserves the observed protocol behavior where the sleep command frame depends on the current fan state.
- After a command, the bridge waits for the command ACK, immediately sends a status query, and publishes the confirmed device state.

## Migration from the standalone script

1. Stop the old Python script or systemd service.
2. Confirm that TCP port `9001`, or the selected listening port, is free on the Home Assistant host.
3. Install and configure this integration.
4. Change USR Socket B to the Home Assistant LAN address and configured port.
5. Verify that the fan and sensors update promptly.
6. Remove old retained MQTT Discovery topics if the previous object IDs were different.

## Privacy and security

The repository contains no private LAN addresses, MAC addresses, real MQTT usernames or passwords, room names, or user-specific paths. Credentials are stored in the Home Assistant config entry. USR/MQTT hosts, usernames, passwords, and the MQTT base topic are redacted from diagnostics.

Review exported Home Assistant config entries and diagnostic files before publishing them.

## Known limitations

- USR parameters are not changed automatically because the embedded web form and HTTP interface vary by USR module and firmware.
- The control frames are reverse engineered and currently verified on AirProce AI-300 and AI-600 purifiers.
- This release creates MQTT Discovery entities rather than native Home Assistant platform entities to preserve the already-tested bridge behavior.

## Code generation disclosure

All code in this repository was generated by **ChatGPT 5.6**.

## License

MIT
