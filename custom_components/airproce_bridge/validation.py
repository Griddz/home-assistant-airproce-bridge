"""Connection validation helpers for AirProce."""

from __future__ import annotations

import socket
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPBasicAuthHandler,
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    build_opener,
)

from .models import BridgeConfig


class CannotConnectUsr(Exception):
    """Raised when the USR web interface cannot be reached."""


class InvalidUsrAuth(Exception):
    """Raised when USR credentials are rejected."""


def validate_usr(config: BridgeConfig) -> None:
    """Validate USR reachability and, optionally, web credentials."""
    try:
        with socket.create_connection(
            (config.usr_host, config.usr_web_port), timeout=4
        ):
            pass
    except OSError as exc:
        raise CannotConnectUsr from exc

    if not config.verify_usr_web:
        return

    password_manager = HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(
        None,
        config.configuration_url,
        config.usr_username,
        config.usr_password,
    )
    opener = build_opener(
        HTTPBasicAuthHandler(password_manager),
        HTTPDigestAuthHandler(password_manager),
    )
    try:
        response = opener.open(config.configuration_url, timeout=5)
        response.close()
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise InvalidUsrAuth from exc
        # A reachable embedded web server can legitimately use a non-root path.
        if exc.code >= 500:
            raise CannotConnectUsr from exc
    except (URLError, OSError) as exc:
        raise CannotConnectUsr from exc


def validate_config(config: BridgeConfig) -> None:
    """Validate the external endpoint used by the integration."""
    validate_usr(config)
