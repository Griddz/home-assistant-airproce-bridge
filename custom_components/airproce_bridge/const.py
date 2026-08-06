"""Constants for the AirProce Socket B bridge integration."""

from __future__ import annotations

DOMAIN = "airproce_bridge"
NAME = "AirProce Socket B Bridge"
VERSION = "0.1.0"

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
CONF_MQTT_HOST = "mqtt_host"
CONF_MQTT_PORT = "mqtt_port"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_BASE_TOPIC = "base_topic"
CONF_DISCOVERY_PREFIX = "discovery_prefix"
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
DEFAULT_MQTT_PORT = 1883
DEFAULT_BASE_TOPIC = "airproce/purifier"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_WATCHDOG_SILENCE = 45
DEFAULT_WATCHDOG_TIMEOUT = 5

PLATFORMS: tuple[str, ...] = ()
