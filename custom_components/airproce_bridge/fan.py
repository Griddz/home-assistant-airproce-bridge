"""Native fan platform for AirProce."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import AirProceRuntime
from .entity import AirProceEntity

_SPEEDS = ("1", "2", "3", "4", "5", "6")
_PRESETS = ["auto", "sleep"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[AirProceRuntime],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the native AirProce fan entity."""
    async_add_entities([AirProceFan(entry.runtime_data)])


class AirProceFan(AirProceEntity, FanEntity):
    """AirProce purifier fan controls."""

    _attr_name = None
    _attr_icon = "mdi:air-purifier"
    _attr_preset_modes = _PRESETS
    _attr_speed_count = 6
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, runtime: AirProceRuntime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.config.device_id}_fan"
        # Preserve the entity IDs used by the previous MQTT-backed release.
        self.entity_id = f"fan.{runtime.config.device_id}"

    @property
    def is_on(self) -> bool | None:
        state = self.runtime.state
        return None if state is None else state.power

    @property
    def percentage(self) -> int | None:
        state = self.runtime.state
        if state is None or not state.power:
            return 0 if state is not None else None
        if state.speed not in range(1, 7):
            return None
        return ordered_list_item_to_percentage(_SPEEDS, str(state.speed))

    @property
    def preset_mode(self) -> str | None:
        state = self.runtime.state
        if state is None or state.mode not in _PRESETS:
            return None
        return state.mode

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        state = self.runtime.state
        if state is None:
            return None
        return {
            "hardware_speed": state.speed,
            "raw_speed_code": state.raw_speed_code,
            "raw_mode_code": state.raw_mode_code,
        }

    def _call_bridge(self, method: str, *args: object) -> None:
        try:
            getattr(self.runtime.bridge, method)(*args)
        except ConnectionError as exc:
            raise HomeAssistantError("AirProce Socket B is not connected") from exc
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the purifier."""
        if preset_mode is not None:
            self._call_bridge("set_preset", preset_mode)
            return
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return
        self._call_bridge("set_power", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the purifier."""
        self._call_bridge("set_power", False)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set one of the six native hardware speeds."""
        if percentage <= 0:
            self._call_bridge("set_power", False)
            return
        speed = int(percentage_to_ordered_list_item(_SPEEDS, percentage))
        self._call_bridge("set_speed", speed)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set auto or sleep mode."""
        if preset_mode not in _PRESETS:
            raise HomeAssistantError(f"Unsupported preset mode: {preset_mode}")
        self._call_bridge("set_preset", preset_mode)
