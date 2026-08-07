"""Shared entity support for AirProce."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from . import AirProceRuntime
from .const import DOMAIN


class AirProceEntity(Entity):
    """Base class for native AirProce entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: AirProceRuntime) -> None:
        self.runtime = runtime
        config = runtime.config
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config.device_id)},
            name=config.device_name,
            manufacturer="AirProce",
            model=config.device_model,
            configuration_url=config.configuration_url,
        )

    @property
    def available(self) -> bool:
        """Return whether a current device state is available."""
        return self.runtime.available and self.runtime.state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to local push updates."""
        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
