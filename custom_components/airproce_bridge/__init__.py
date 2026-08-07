"""AirProce local Home Assistant integration."""

from __future__ import annotations

from collections.abc import Callable
import logging
import threading

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .bridge import AirProceBridge
from .const import (
    CONF_DEVICE_ID,
    LEGACY_MQTT_KEYS,
    PLATFORMS,
)
from .models import BridgeConfig
from .protocol import PurifierState

_LOGGER = logging.getLogger(__name__)

type AirProceConfigEntry = ConfigEntry["AirProceRuntime"]


class AirProceRuntime:
    """Bridge runtime and push-state dispatcher for one purifier."""

    def __init__(self, hass: HomeAssistant, config: BridgeConfig) -> None:
        self.hass = hass
        self.config = config
        self.state: PurifierState | None = None
        self.available = False
        self._listeners: set[Callable[[], None]] = set()
        self.bridge = AirProceBridge(
            config,
            on_state=self._bridge_state_received,
            on_availability=self._bridge_availability_received,
        )
        self.thread = threading.Thread(
            target=self.bridge.run,
            name=f"airproce-bridge-{config.device_id}",
            daemon=True,
        )

    def _bridge_state_received(self, state: PurifierState) -> None:
        """Marshal a state update from the bridge thread to the HA event loop."""
        try:
            self.hass.loop.call_soon_threadsafe(self._async_set_state, state)
        except RuntimeError:
            _LOGGER.debug("Home Assistant loop is closing; state update ignored")

    def _bridge_availability_received(self, available: bool) -> None:
        """Marshal availability from the bridge thread to the HA event loop."""
        try:
            self.hass.loop.call_soon_threadsafe(
                self._async_set_availability, available
            )
        except RuntimeError:
            _LOGGER.debug("Home Assistant loop is closing; availability ignored")

    @callback
    def _async_set_state(self, state: PurifierState) -> None:
        self.state = state
        self.available = True
        self._async_notify_listeners()

    @callback
    def _async_set_availability(self, available: bool) -> None:
        self.available = available
        if not available:
            self.state = None
        self._async_notify_listeners()

    @callback
    def _async_notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity push-update callback."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener


async def _async_clear_legacy_discovery_topics(
    hass: HomeAssistant,
    topics: tuple[str, ...],
) -> bool:
    """Clear retained v0.1 Discovery topics when MQTT is available."""
    if not hass.services.has_service("mqtt", "publish"):
        return False

    for topic in topics:
        try:
            await hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": "",
                    "qos": 1,
                    "retain": True,
                },
                blocking=True,
            )
        except Exception:
            _LOGGER.warning(
                "Could not clear legacy retained MQTT Discovery topic %s",
                topic,
                exc_info=True,
            )
            return False
    return True


async def _async_cleanup_legacy_mqtt(
    hass: HomeAssistant,
    data: dict[str, object],
) -> None:
    """Best-effort cleanup of v0.1 MQTT Discovery entities during migration."""
    device_id = str(data.get(CONF_DEVICE_ID, "")).strip().lower()
    if not device_id:
        return

    prefix = str(data.get("discovery_prefix", "homeassistant")).strip().strip("/")
    discovery_topics = (
        f"{prefix}/fan/{device_id}/config",
        f"{prefix}/sensor/{device_id}_temperature/config",
        f"{prefix}/sensor/{device_id}_humidity/config",
        f"{prefix}/sensor/{device_id}_pm25/config",
        f"{prefix}/sensor/{device_id}_voc/config",
    )

    cleared = await _async_clear_legacy_discovery_topics(hass, discovery_topics)
    if not cleared:
        @callback
        def cleanup_after_start(_event: object) -> None:
            hass.async_create_task(
                _async_clear_legacy_discovery_topics(hass, discovery_topics)
            )

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, cleanup_after_start)

    registry = er.async_get(hass)
    legacy_entities = (
        ("fan", f"{device_id}_fan"),
        ("sensor", f"{device_id}_temperature"),
        ("sensor", f"{device_id}_humidity"),
        ("sensor", f"{device_id}_pm25"),
        ("sensor", f"{device_id}_voc"),
    )
    for domain, unique_id in legacy_entities:
        entity_id = registry.async_get_entity_id(domain, "mqtt", unique_id)
        if entity_id is not None:
            registry.async_remove(entity_id)


async def async_migrate_entry(hass: HomeAssistant, entry: AirProceConfigEntry) -> bool:
    """Migrate MQTT-backed v0.1 entries to native Home Assistant entities."""
    if entry.version >= 2:
        return True

    data = dict(entry.data)
    await _async_cleanup_legacy_mqtt(hass, data)
    for key in LEGACY_MQTT_KEYS:
        data.pop(key, None)

    config = BridgeConfig.from_mapping(data)
    data[CONF_DEVICE_ID] = config.device_id
    hass.config_entries.async_update_entry(entry, data=data, version=2)
    _LOGGER.info("Migrated AirProce config entry %s to native entities", entry.title)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirProceConfigEntry,
) -> bool:
    """Set up AirProce from a config entry."""
    config = BridgeConfig.from_mapping(dict(entry.data))
    runtime = AirProceRuntime(hass, config)
    runtime.thread.start()

    started = await hass.async_add_executor_job(runtime.bridge.startup_event.wait, 8.0)
    if not started:
        runtime.bridge.shutdown()
        await hass.async_add_executor_job(runtime.thread.join, 3.0)
        raise ConfigEntryNotReady("Timed out starting the Socket B listener")
    if runtime.bridge.startup_error is not None:
        runtime.bridge.shutdown()
        await hass.async_add_executor_job(runtime.thread.join, 3.0)
        raise ConfigEntryNotReady(
            f"Unable to start Socket B listener: {runtime.bridge.startup_error}"
        ) from runtime.bridge.startup_error

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: AirProceConfigEntry,
) -> bool:
    """Unload an AirProce config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = entry.runtime_data
    await hass.async_add_executor_job(runtime.bridge.shutdown)
    await hass.async_add_executor_job(runtime.thread.join, 5.0)
    return True
