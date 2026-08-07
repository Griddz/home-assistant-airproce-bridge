"""Constants for the AirProce integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "airproce_bridge"
NAME = "AirProce"
VERSION = "0.2.0"

CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_MODEL = "device_model"
CONF_DEVICE_ID = "device_id"
CONF_USR_HOST = "usr_host"
CONF_USR_WEB_PORT = "usr_web_port"
CONF_USR_USERNAME = "usr_username"
CONF_USR_PASSWORD = "usr_password"
CONF_VERIFY_USR_WEB = "verify_usr_web"
CONF_LISTEN_HOST = "listen_host"
CONF_LISTEN_PORT = "listen_port"
CONF_WATCHDOG_SILENCE = "watchdog_silence"
CONF_WATCHDOG_TIMEOUT = "watchdog_timeout"

DEFAULT_DEVICE_NAME = "AirProce Air Purifier"
DEFAULT_DEVICE_MODEL = "AI-600"
DEFAULT_USR_WEB_PORT = 80
DEFAULT_USR_USERNAME = "admin"
DEFAULT_USR_PASSWORD = "admin"
DEFAULT_VERIFY_USR_WEB = True
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 9001
DEFAULT_WATCHDOG_SILENCE = 45
DEFAULT_WATCHDOG_TIMEOUT = 5

PLATFORMS: tuple[Platform, ...] = (Platform.FAN, Platform.SENSOR)

# Version 0.1.x stored these values in the config entry. They are removed when
# the entry is migrated to the native Home Assistant implementation.
LEGACY_MQTT_KEYS: frozenset[str] = frozenset(
    {
        "mqtt_host",
        "mqtt_port",
        "mqtt_username",
        "mqtt_password",
        "base_topic",
        "discovery_prefix",
    }
)
