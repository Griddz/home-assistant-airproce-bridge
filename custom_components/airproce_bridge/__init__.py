"""AirProce Socket B Bridge custom integration."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
import threading

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .bridge import AirProceBridge
from .const import DOMAIN
from .models import BridgeConfig


type AirProceBridgeConfigEntry = ConfigEntry["AirProceBridgeRuntime"]


@dataclass(slots=True)
class AirProceBridgeRuntime:
    """Objects owned by a loaded config entry."""

    bridge: AirProceBridge
    thread: threading.Thread


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirProceBridgeConfigEntry,
) -> bool:
    """Set up AirProce Socket B Bridge from a config entry."""
    config = BridgeConfig.from_mapping(dict(entry.data))
    bridge = AirProceBridge(config)
    thread = threading.Thread(
        target=bridge.run,
        name=f"airproce-bridge-{config.device_id}",
        daemon=True,
    )
    thread.start()

    started = await hass.async_add_executor_job(bridge.startup_event.wait, 8.0)
    if not started:
        bridge.shutdown(clear_discovery=False)
        await hass.async_add_executor_job(thread.join, 3.0)
        raise ConfigEntryNotReady("Timed out starting the Socket B listener")
    if bridge.startup_error is not None:
        bridge.shutdown(clear_discovery=False)
        await hass.async_add_executor_job(thread.join, 3.0)
        raise ConfigEntryNotReady(
            f"Unable to start Socket B listener: {bridge.startup_error}"
        ) from bridge.startup_error

    entry.runtime_data = AirProceBridgeRuntime(bridge=bridge, thread=thread)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: AirProceBridgeConfigEntry,
) -> bool:
    """Unload a config entry and remove its MQTT discovery entities."""
    runtime = entry.runtime_data
    await hass.async_add_executor_job(
        partial(runtime.bridge.shutdown, clear_discovery=True)
    )
    await hass.async_add_executor_job(runtime.thread.join, 5.0)
    return True
