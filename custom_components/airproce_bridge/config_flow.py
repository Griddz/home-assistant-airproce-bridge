"""Config flow for AirProce."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_LISTEN_HOST,
    CONF_LISTEN_PORT,
    CONF_USR_HOST,
    CONF_USR_PASSWORD,
    CONF_USR_USERNAME,
    CONF_USR_WEB_PORT,
    CONF_VERIFY_USR_WEB,
    CONF_WATCHDOG_SILENCE,
    CONF_WATCHDOG_TIMEOUT,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_USR_PASSWORD,
    DEFAULT_USR_USERNAME,
    DEFAULT_USR_WEB_PORT,
    DEFAULT_VERIFY_USR_WEB,
    DEFAULT_WATCHDOG_SILENCE,
    DEFAULT_WATCHDOG_TIMEOUT,
    DOMAIN,
)
from .models import BridgeConfig
from .validation import CannotConnectUsr, InvalidUsrAuth, validate_config

_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD)
)


def _build_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}

    basic_schema = vol.Schema(
        {
            vol.Required(
                CONF_DEVICE_NAME,
                default=defaults.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
            ): cv.string,
            vol.Required(
                CONF_DEVICE_MODEL,
                default=defaults.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL),
            ): cv.string,
            vol.Required(
                CONF_USR_HOST,
                default=defaults.get(CONF_USR_HOST, ""),
            ): cv.string,
            vol.Required(
                CONF_LISTEN_PORT,
                default=defaults.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT),
            ): cv.port,
        }
    )

    advanced_schema = vol.Schema(
        {
            vol.Required(
                CONF_USR_WEB_PORT,
                default=defaults.get(CONF_USR_WEB_PORT, DEFAULT_USR_WEB_PORT),
            ): cv.port,
            vol.Required(
                CONF_USR_USERNAME,
                default=defaults.get(CONF_USR_USERNAME, DEFAULT_USR_USERNAME),
            ): cv.string,
            vol.Required(
                CONF_USR_PASSWORD,
                default=defaults.get(CONF_USR_PASSWORD, DEFAULT_USR_PASSWORD),
            ): _PASSWORD_SELECTOR,
            vol.Required(
                CONF_VERIFY_USR_WEB,
                default=defaults.get(CONF_VERIFY_USR_WEB, DEFAULT_VERIFY_USR_WEB),
            ): cv.boolean,
            vol.Required(
                CONF_WATCHDOG_SILENCE,
                default=defaults.get(
                    CONF_WATCHDOG_SILENCE, DEFAULT_WATCHDOG_SILENCE
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=30,
                    max=300,
                    step=5,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Required(
                CONF_WATCHDOG_TIMEOUT,
                default=defaults.get(
                    CONF_WATCHDOG_TIMEOUT, DEFAULT_WATCHDOG_TIMEOUT
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=2,
                    max=30,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )

    return vol.Schema(
        {
            vol.Required("basic"): data_entry_flow.section(
                basic_schema, {"collapsed": False}
            ),
            vol.Required("advanced"): data_entry_flow.section(
                advanced_schema, {"collapsed": True}
            ),
        }
    )


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        **user_input.get("basic", {}),
        **user_input.get("advanced", {}),
    }


def _apply_internal_defaults(
    data: dict[str, Any],
    *,
    existing_device_id: str | None = None,
) -> dict[str, Any]:
    """Apply internal settings that should not be exposed in the UI."""
    result = dict(data)
    result[CONF_LISTEN_HOST] = DEFAULT_LISTEN_HOST
    if existing_device_id:
        result[CONF_DEVICE_ID] = existing_device_id
    return result


class AirProceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle AirProce configuration."""

    VERSION = 2

    def _listen_port_is_unique(
        self,
        config: BridgeConfig,
        *,
        exclude_entry_id: str | None = None,
    ) -> bool:
        """Return whether another AirProce entry already uses this listener."""
        for entry in self._async_current_entries():
            if entry.entry_id == exclude_entry_id:
                continue
            try:
                other = BridgeConfig.from_mapping(dict(entry.data))
            except (KeyError, TypeError, ValueError):
                continue
            if other.listen_port == config.listen_port:
                return False
        return True

    async def _validate(
        self,
        data: dict[str, Any],
        *,
        exclude_entry_id: str | None = None,
    ) -> tuple[dict[str, str], BridgeConfig | None]:
        errors: dict[str, str] = {}
        try:
            config = BridgeConfig.from_mapping(data)
            if not self._listen_port_is_unique(
                config, exclude_entry_id=exclude_entry_id
            ):
                errors["base"] = "listen_port_in_use"
                return errors, None
            await self.hass.async_add_executor_job(validate_config, config)
        except InvalidUsrAuth:
            errors["base"] = "invalid_usr_auth"
            return errors, None
        except CannotConnectUsr:
            errors["base"] = "cannot_connect_usr"
            return errors, None
        except (KeyError, TypeError, ValueError):
            errors["base"] = "invalid_config"
            return errors, None
        return errors, config

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        suggested: dict[str, Any] | None = None

        if user_input is not None:
            data = _apply_internal_defaults(_flatten(user_input))
            errors, config = await self._validate(data)
            suggested = data
            if not errors and config is not None:
                data[CONF_DEVICE_ID] = config.device_id
                await self.async_set_unique_id(config.device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=config.device_name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(suggested),
            errors=errors,
        )

    @override
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update connection and device settings."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        defaults = dict(entry.data)

        if user_input is not None:
            existing_device_id = str(entry.data.get(CONF_DEVICE_ID, "")).strip() or None
            data = _apply_internal_defaults(
                _flatten(user_input),
                existing_device_id=existing_device_id,
            )
            errors, config = await self._validate(
                data, exclude_entry_id=entry.entry_id
            )
            defaults = data
            if not errors and config is not None:
                data[CONF_DEVICE_ID] = config.device_id
                await self.async_set_unique_id(config.device_id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                if entry.title != config.device_name:
                    self.hass.config_entries.async_update_entry(
                        entry, title=config.device_name
                    )
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_schema(defaults),
            errors=errors,
        )
