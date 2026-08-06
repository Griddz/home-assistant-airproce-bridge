"""Connection validation helpers for AirProce Socket B Bridge."""

from __future__ import annotations

import socket
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPBasicAuthHandler,
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    build_opener,
)

import paho.mqtt.client as mqtt

from .models import BridgeConfig


class CannotConnectUsr(Exception):
    """Raised when the USR web interface cannot be reached."""


class InvalidUsrAuth(Exception):
    """Raised when USR credentials are rejected."""


class CannotConnectMqtt(Exception):
    """Raised when the MQTT broker cannot be reached."""


class InvalidMqttAuth(Exception):
    """Raised when MQTT credentials are rejected."""


def validate_usr(config: BridgeConfig) -> None:
    """Validate USR reachability and, optionally, web credentials."""
    try:
        with socket.create_connection(
            (config.usr_host, config.usr_web_port), timeout=4
        ):
            pass
    except OSError as exc:
        raise CannotConnectUsr from exc

    if not config.verify_usr_web:
        return

    password_manager = HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(
        None,
        config.configuration_url,
        config.usr_username,
        config.usr_password,
    )
    opener = build_opener(
        HTTPBasicAuthHandler(password_manager),
        HTTPDigestAuthHandler(password_manager),
    )
    try:
        response = opener.open(config.configuration_url, timeout=5)
        response.close()
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise InvalidUsrAuth from exc
        # A reachable embedded web server can legitimately use a non-root path.
        if exc.code >= 500:
            raise CannotConnectUsr from exc
    except (URLError, OSError) as exc:
        raise CannotConnectUsr from exc


def _reason_code_value(reason_code: Any) -> int:
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def validate_mqtt(config: BridgeConfig) -> None:
    """Validate MQTT network access and credentials."""
    connected = threading.Event()
    result: dict[str, int] = {"code": -1}

    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"airproce-config-check-{config.device_id}",
            clean_session=True,
        )
    except (AttributeError, TypeError):
        client = mqtt.Client(
            client_id=f"airproce-config-check-{config.device_id}",
            clean_session=True,
        )

    if config.mqtt_username:
        client.username_pw_set(config.mqtt_username, config.mqtt_password)

    def on_connect(
        client_obj: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        result["code"] = _reason_code_value(reason_code)
        connected.set()

    client.on_connect = on_connect

    try:
        client.connect(config.mqtt_host, config.mqtt_port, keepalive=10)
        client.loop_start()
        if not connected.wait(5):
            raise CannotConnectMqtt
        if result["code"] in (4, 5, 134, 135):
            raise InvalidMqttAuth
        if result["code"] != 0:
            raise CannotConnectMqtt
    except InvalidMqttAuth:
        raise
    except (OSError, mqtt.MQTTException) as exc:
        raise CannotConnectMqtt from exc
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass


def validate_config(config: BridgeConfig) -> None:
    """Validate all external endpoints."""
    validate_usr(config)
    validate_mqtt(config)
