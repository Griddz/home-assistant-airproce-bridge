"""Native sensor platform for AirProce."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AirProceRuntime
from .entity import AirProceEntity
from .protocol import PurifierState


@dataclass(frozen=True, kw_only=True)
class AirProceSensorDescription(SensorEntityDescription):
    """Description of an AirProce sensor."""

    value_fn: Callable[[PurifierState], int | float]


SENSORS: tuple[AirProceSensorDescription, ...] = (
    AirProceSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda state: state.temperature,
    ),
    AirProceSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda state: state.humidity,
    ),
    AirProceSensorDescription(
        key="pm25",
        translation_key="pm25",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="µg/m³",
        suggested_display_precision=0,
        value_fn=lambda state: state.pm25,
    ),
    AirProceSensorDescription(
        key="voc",
        translation_key="voc",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mg/m³",
        suggested_display_precision=3,
        value_fn=lambda state: state.voc,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[AirProceRuntime],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up native AirProce sensors."""
    runtime = entry.runtime_data
    async_add_entities(AirProceSensor(runtime, description) for description in SENSORS)


class AirProceSensor(AirProceEntity, SensorEntity):
    """One local AirProce measurement."""

    entity_description: AirProceSensorDescription

    def __init__(
        self,
        runtime: AirProceRuntime,
        description: AirProceSensorDescription,
    ) -> None:
        super().__init__(runtime)
        self.entity_description = description
        self._attr_unique_id = f"{runtime.config.device_id}_{description.key}"
        # Preserve the entity IDs used by the previous MQTT-backed release.
        self.entity_id = f"sensor.{runtime.config.device_id}_{description.key}"

    @property
    def native_value(self) -> int | float | None:
        state = self.runtime.state
        if state is None:
            return None
        return self.entity_description.value_fn(state)
