"""Diagnostics for AirProce."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AirProceConfigEntry
from .const import CONF_USR_HOST, CONF_USR_PASSWORD, CONF_USR_USERNAME

_TO_REDACT = {
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
    """Return diagnostics with credentials removed."""
    return {
        "config_entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "runtime": entry.runtime_data.bridge.diagnostics(),
    }
