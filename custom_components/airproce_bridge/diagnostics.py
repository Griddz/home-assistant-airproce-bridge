"""Diagnostics for AirProce."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AirProceConfigEntry
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_USR_HOST,
    CONF_USR_PASSWORD,
    CONF_USR_USERNAME,
    VERSION,
)

_TO_REDACT = {
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_USR_HOST,
    CONF_USR_USERNAME,
    CONF_USR_PASSWORD,
    # Protect credentials from a pre-0.2 config entry if diagnostics are
    # requested before migration has completed.
    "mqtt_host",
    "mqtt_username",
    "mqtt_password",
    "base_topic",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: AirProceConfigEntry,
) -> dict[str, Any]:
    """Return a privacy-safe diagnostics snapshot for one purifier."""
    return {
        "integration_version": VERSION,
        "config_entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "runtime": entry.runtime_data.bridge.diagnostics(),
    }
