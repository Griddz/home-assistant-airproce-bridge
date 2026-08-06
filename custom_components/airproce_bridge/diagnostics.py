"""Diagnostics for AirProce Socket B Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AirProceBridgeConfigEntry
from .const import (
    CONF_BASE_TOPIC,
    CONF_MQTT_HOST,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_USR_HOST,
    CONF_USR_PASSWORD,
    CONF_USR_USERNAME,
)

_TO_REDACT = {
    CONF_USR_HOST,
    CONF_USR_USERNAME,
    CONF_USR_PASSWORD,
    CONF_MQTT_HOST,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    CONF_BASE_TOPIC,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: AirProceBridgeConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics with credentials removed."""
    return {
        "config_entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "runtime": entry.runtime_data.bridge.diagnostics(),
    }
