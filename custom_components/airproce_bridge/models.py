"""Data models for AirProce."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
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
)


@dataclass(slots=True, frozen=True)
class BridgeConfig:
    """Runtime configuration for one purifier."""

    device_name: str
    device_model: str
    device_id: str
    usr_host: str
    usr_web_port: int
    usr_username: str
    usr_password: str
    verify_usr_web: bool
    listen_host: str
    listen_port: int
    watchdog_silence: float
    watchdog_timeout: float

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "BridgeConfig":
        """Build runtime config from a Home Assistant config entry mapping."""
        usr_host = str(data[CONF_USR_HOST]).strip()
        raw_device_id = str(data.get(CONF_DEVICE_ID, "")).strip()
        if not raw_device_id:
            raw_device_id = f"airproce_{usr_host.replace('.', '_').replace(':', '_')}"

        return cls(
            device_name=str(data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)).strip(),
            device_model=str(data.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL)).strip(),
            device_id=_slug(raw_device_id),
            usr_host=usr_host,
            usr_web_port=int(data.get(CONF_USR_WEB_PORT, DEFAULT_USR_WEB_PORT)),
            usr_username=str(data.get(CONF_USR_USERNAME, DEFAULT_USR_USERNAME)),
            usr_password=str(data.get(CONF_USR_PASSWORD, DEFAULT_USR_PASSWORD)),
            verify_usr_web=bool(data.get(CONF_VERIFY_USR_WEB, DEFAULT_VERIFY_USR_WEB)),
            # Socket B should accept connections on any Home Assistant IPv4
            # interface. This is an implementation detail, not a user setting.
            listen_host=DEFAULT_LISTEN_HOST,
            listen_port=int(data.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT)),
            watchdog_silence=float(
                data.get(CONF_WATCHDOG_SILENCE, DEFAULT_WATCHDOG_SILENCE)
            ),
            watchdog_timeout=float(
                data.get(CONF_WATCHDOG_TIMEOUT, DEFAULT_WATCHDOG_TIMEOUT)
            ),
        )

    @property
    def configuration_url(self) -> str:
        """Return the USR web management URL without embedding credentials."""
        suffix = "" if self.usr_web_port == 80 else f":{self.usr_web_port}"
        return f"http://{self.usr_host}{suffix}/"


def _slug(value: str) -> str:
    """Return a safe stable Home Assistant identifier."""
    slug = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError("device_id must contain letters or digits")
    return slug[:96]
