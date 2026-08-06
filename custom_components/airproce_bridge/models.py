"""Data models for AirProce Socket B Bridge."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .const import (
    CONF_BASE_TOPIC,
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DISCOVERY_PREFIX,
    CONF_LISTEN_HOST,
    CONF_LISTEN_PORT,
    CONF_MQTT_HOST,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_USR_HOST,
    CONF_USR_PASSWORD,
    CONF_USR_USERNAME,
    CONF_USR_WEB_PORT,
    CONF_VERIFY_USR_WEB,
    CONF_WATCHDOG_SILENCE,
    CONF_WATCHDOG_TIMEOUT,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DISCOVERY_PREFIX,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_MQTT_PORT,
    DEFAULT_USR_PASSWORD,
    DEFAULT_USR_USERNAME,
    DEFAULT_USR_WEB_PORT,
    DEFAULT_VERIFY_USR_WEB,
    DEFAULT_WATCHDOG_SILENCE,
    DEFAULT_WATCHDOG_TIMEOUT,
)


@dataclass(slots=True, frozen=True)
class BridgeConfig:
    """Runtime configuration."""

    device_name: str
    device_model: str
    device_id: str
    usr_host: str
    usr_web_port: int
    usr_username: str
    usr_password: str
    verify_usr_web: bool
    listen_host: str
    listen_port: int
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    base_topic: str
    discovery_prefix: str
    watchdog_silence: float
    watchdog_timeout: float

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "BridgeConfig":
        """Build runtime config from a Home Assistant config entry mapping."""
        return cls(
            device_name=str(data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)).strip(),
            device_model=str(data.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL)).strip(),
            device_id=_slug(str(data[CONF_DEVICE_ID])),
            usr_host=str(data[CONF_USR_HOST]).strip(),
            usr_web_port=int(data.get(CONF_USR_WEB_PORT, DEFAULT_USR_WEB_PORT)),
            usr_username=str(data.get(CONF_USR_USERNAME, DEFAULT_USR_USERNAME)),
            usr_password=str(data.get(CONF_USR_PASSWORD, DEFAULT_USR_PASSWORD)),
            verify_usr_web=bool(data.get(CONF_VERIFY_USR_WEB, DEFAULT_VERIFY_USR_WEB)),
            listen_host=str(data.get(CONF_LISTEN_HOST, DEFAULT_LISTEN_HOST)).strip(),
            listen_port=int(data.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT)),
            mqtt_host=str(data[CONF_MQTT_HOST]).strip(),
            mqtt_port=int(data.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)),
            mqtt_username=str(data.get(CONF_MQTT_USERNAME, "")),
            mqtt_password=str(data.get(CONF_MQTT_PASSWORD, "")),
            base_topic=str(data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)).strip().strip("/"),
            discovery_prefix=str(
                data.get(CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX)
            ).strip().strip("/"),
            watchdog_silence=float(
                data.get(CONF_WATCHDOG_SILENCE, DEFAULT_WATCHDOG_SILENCE)
            ),
            watchdog_timeout=float(
                data.get(CONF_WATCHDOG_TIMEOUT, DEFAULT_WATCHDOG_TIMEOUT)
            ),
        )

    @property
    def configuration_url(self) -> str:
        """Return the USR web management URL without embedding credentials."""
        suffix = "" if self.usr_web_port == 80 else f":{self.usr_web_port}"
        return f"http://{self.usr_host}{suffix}/"

    @property
    def object_id(self) -> str:
        """Return a stable MQTT discovery object id."""
        return self.device_id


def _slug(value: str) -> str:
    """Return a safe stable identifier for MQTT object IDs and client IDs."""
    slug = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError("device_id must contain letters or digits")
    return slug[:96]
