"""Local Socket B runtime for AirProce purifiers."""

from __future__ import annotations

from dataclasses import asdict
import logging
import socket
import threading
import time
from collections.abc import Callable
from typing import Any, Final

from .const import NAME, VERSION
from .models import BridgeConfig
from .protocol import (
    COMMANDS,
    CONTROL_SPEED_INDEX,
    STATUS_QUERY,
    FrameParser,
    PurifierState,
    decode_state,
)

_LOGGER = logging.getLogger(__name__)

WATCHDOG_CHECK_INTERVAL: Final = 5.0
WATCHDOG_RETRY_DELAY: Final = 2.0

StateCallback = Callable[[PurifierState], None]
AvailabilityCallback = Callable[[bool], None]


class AirProceBridge:
    """Manage Socket B, controls, state decoding, and watchdog."""

    def __init__(
        self,
        config: BridgeConfig,
        *,
        on_state: StateCallback | None = None,
        on_availability: AvailabilityCallback | None = None,
    ) -> None:
        self.config = config
        self._on_state = on_state
        self._on_availability = on_availability

        self.stop_event = threading.Event()
        self.startup_event = threading.Event()
        self.startup_error: Exception | None = None
        self.shutdown_lock = threading.Lock()
        self.shutdown_done = False

        self.listener_socket: socket.socket | None = None
        self.device_lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.command_lock = threading.Lock()
        self.pending_ack_lock = threading.Lock()
        self.pending_acks: dict[bytes, threading.Event] = {}
        self.device_socket: socket.socket | None = None
        self.device_address: tuple[str, int] | None = None
        self.device_online = False
        self.device_connected_monotonic = 0.0
        self.last_rx_monotonic = 0.0

        self.state_lock = threading.RLock()
        self.last_state: PurifierState | None = None
        self.last_state_monotonic = 0.0
        self.last_manual_speed = 1
        self.state_counter = 0
        self.state_condition = threading.Condition(self.state_lock)

    def _notify_state(self, state: PurifierState) -> None:
        callback = self._on_state
        if callback is None:
            return
        try:
            callback(state)
        except Exception:
            _LOGGER.exception("AirProce state callback failed")

    def _notify_availability(self, available: bool) -> None:
        callback = self._on_availability
        if callback is None:
            return
        try:
            callback(available)
        except Exception:
            _LOGGER.exception("AirProce availability callback failed")

    def _current_context_speed(self) -> int:
        with self.state_lock:
            state = self.last_state
            if state is not None and 1 <= state.raw_speed_code <= 6:
                return state.raw_speed_code
            return self.last_manual_speed

    def _send_raw(self, data: bytes, label: str) -> None:
        with self.device_lock:
            conn = self.device_socket
            address = self.device_address
        if conn is None:
            raise ConnectionError("Socket B is not connected")
        with self.send_lock:
            conn.sendall(data)
        _LOGGER.debug("Sent %s to %s: %s", label, address, data.hex(" "))

    def _wait_for_new_state(self, previous_counter: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.state_condition:
            while self.state_counter <= previous_counter:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self.state_condition.wait(remaining)
            return True

    def _control_worker(self, name: str, command: bytes) -> None:
        sequence = command[4:6]
        ack_event = threading.Event()

        with self.command_lock:
            with self.pending_ack_lock:
                self.pending_acks[sequence] = ack_event
            try:
                self._send_raw(command, name)
                if not ack_event.wait(timeout=2.2):
                    _LOGGER.warning("No ACK for %s; querying state anyway", name)

                with self.state_lock:
                    before_query_state = self.state_counter
                self._send_raw(STATUS_QUERY, "status_query")
                if not self._wait_for_new_state(before_query_state, timeout=1.5):
                    with self.state_lock:
                        before_retry_state = self.state_counter
                    self._send_raw(STATUS_QUERY, "status_query_retry")
                    if not self._wait_for_new_state(before_retry_state, timeout=2.0):
                        _LOGGER.error("No confirmed state after command %s", name)
            except Exception:
                _LOGGER.exception("Control sequence failed: %s", name)
            finally:
                with self.pending_ack_lock:
                    if self.pending_acks.get(sequence) is ack_event:
                        del self.pending_acks[sequence]

    def send_command(self, name: str, contextual_speed: int | None = None) -> None:
        """Send a named purifier command and confirm with a status query."""
        if name not in COMMANDS:
            raise ValueError(f"Unknown command: {name}")
        command = bytearray(COMMANDS[name])
        if name in ("auto", "sleep"):
            if contextual_speed is None:
                contextual_speed = self._current_context_speed()
            command[CONTROL_SPEED_INDEX] = max(1, min(6, int(contextual_speed)))

        with self.device_lock:
            if self.device_socket is None:
                raise ConnectionError("Socket B is not connected")

        threading.Thread(
            target=self._control_worker,
            args=(name, bytes(command)),
            name=f"airproce-control-{self.config.device_id}-{name}",
            daemon=True,
        ).start()

    def request_state_async(self, reason: str = "manual") -> None:
        """Request device state without blocking the caller."""

        def worker() -> None:
            with self.command_lock:
                try:
                    self._send_raw(STATUS_QUERY, f"status_query_{reason}")
                except Exception:
                    _LOGGER.exception("Status query failed: %s", reason)

        threading.Thread(
            target=worker,
            name=f"airproce-status-{self.config.device_id}-{reason}",
            daemon=True,
        ).start()

    def set_power(self, power: bool) -> None:
        """Turn the purifier on or off."""
        self.send_command("power_on" if power else "power_off")

    def set_speed(self, speed: int) -> None:
        """Set a manual hardware speed from 1 through 6."""
        if speed not in range(1, 7):
            raise ValueError("Fan speed must be 1..6")
        self.send_command(f"fan_{speed}")

    def set_preset(self, preset: str | None) -> None:
        """Set auto/sleep, or return to the last manual speed."""
        value = (preset or "").strip().lower()
        if value in ("", "none", "manual"):
            self.set_speed(self.last_manual_speed)
        elif value == "auto":
            self.send_command("auto", self._current_context_speed())
        elif value == "sleep":
            self.send_command("sleep", self._current_context_speed())
        else:
            raise ValueError(f"Unsupported fan preset: {preset!r}")

    # Compatibility helpers retained for callers/tests from the standalone bridge.
    def handle_power(self, payload: str) -> None:
        value = payload.strip().lower()
        if value in ("on", "1", "true"):
            self.set_power(True)
        elif value in ("off", "0", "false"):
            self.set_power(False)
        else:
            raise ValueError(f"Unsupported power payload: {payload!r}")

    def handle_percentage(self, payload: str) -> None:
        value = payload.strip().lower().replace("%", "")
        speed = int(round(float(value)))
        if speed == 0:
            self.set_power(False)
            return
        self.set_speed(speed)

    def handle_fan_preset(self, payload: str) -> None:
        self.set_preset(payload)

    def handle_speed(self, payload: str) -> None:
        speed = int(payload.strip().lower().replace("档", ""))
        self.set_speed(speed)

    def _set_device_connection(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        now = time.monotonic()
        with self.device_lock:
            old = self.device_socket
            self.device_socket = conn
            self.device_address = addr
            self.device_online = True
            self.device_connected_monotonic = now
            self.last_rx_monotonic = now
        with self.state_lock:
            self.last_state_monotonic = 0.0

        if old is not None and old is not conn:
            try:
                old.close()
            except OSError:
                pass
        self._notify_availability(True)
        timer = threading.Timer(0.5, self.request_state_async, args=("connect",))
        timer.daemon = True
        timer.start()

    def _clear_device_connection(self, conn: socket.socket) -> None:
        with self.device_lock:
            if self.device_socket is not conn:
                return
            self.device_socket = None
            self.device_address = None
            self.device_online = False
            self.device_connected_monotonic = 0.0
            self.last_rx_monotonic = 0.0
        self._notify_availability(False)

    def _close_stale_connection(self, conn: socket.socket, reason: str) -> None:
        with self.device_lock:
            if self.device_socket is not conn:
                return
        _LOGGER.error("Closing Socket B for %s: %s", self.config.device_id, reason)
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass
        self._clear_device_connection(conn)

    def _watchdog_query_once(self, expected_conn: socket.socket, label: str) -> bool:
        with self.command_lock:
            with self.device_lock:
                if self.device_socket is not expected_conn:
                    return True
            with self.state_lock:
                before_state = self.state_counter
            try:
                self._send_raw(STATUS_QUERY, label)
            except Exception:
                _LOGGER.exception("Watchdog state query failed")
                return False
            return self._wait_for_new_state(
                before_state,
                self.config.watchdog_timeout,
            )

    def watchdog_loop(self) -> None:
        """Detect silent half-open Socket B sessions."""
        while not self.stop_event.wait(WATCHDOG_CHECK_INTERVAL):
            with self.device_lock:
                conn = self.device_socket
                connected_at = self.device_connected_monotonic
            if conn is None:
                continue

            with self.state_lock:
                last_state_at = self.last_state_monotonic
            reference = last_state_at or connected_at
            if reference <= 0:
                continue

            silence = time.monotonic() - reference
            if silence < self.config.watchdog_silence:
                continue

            _LOGGER.warning(
                "No valid state for %.1fs from %s; watchdog query",
                silence,
                self.config.device_id,
            )
            if self._watchdog_query_once(conn, "status_query_watchdog"):
                continue
            if self.stop_event.wait(WATCHDOG_RETRY_DELAY):
                break
            with self.device_lock:
                if self.device_socket is not conn:
                    continue
            if self._watchdog_query_once(conn, "status_query_watchdog_retry"):
                continue
            self._close_stale_connection(conn, "two watchdog queries had no reply")

    def handle_device(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        """Handle one USR Socket B TCP connection."""
        if addr[0] != self.config.usr_host:
            _LOGGER.warning("Rejected unexpected Socket B client %s:%s", *addr)
            conn.close()
            return

        _LOGGER.info("Socket B connected from %s:%s", *addr)
        conn.settimeout(2.0)
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for option_name, value in (
            ("TCP_KEEPIDLE", 60),
            ("TCP_KEEPINTVL", 10),
            ("TCP_KEEPCNT", 3),
        ):
            option = getattr(socket, option_name, None)
            if option is not None:
                try:
                    conn.setsockopt(socket.IPPROTO_TCP, option, value)
                except OSError:
                    _LOGGER.debug("Cannot set %s", option_name, exc_info=True)

        self._set_device_connection(conn, addr)
        parser = FrameParser()
        try:
            while not self.stop_event.is_set():
                try:
                    data = conn.recv(65535)
                except socket.timeout:
                    continue
                if not data:
                    break

                with self.device_lock:
                    if self.device_socket is conn:
                        self.last_rx_monotonic = time.monotonic()

                for frame in parser.feed(data):
                    if len(frame) == 16 and frame[:4] == b"\x00\x09\xff\xf9":
                        sequence = frame[4:6]
                        with self.pending_ack_lock:
                            event = self.pending_acks.get(sequence)
                        if event is not None:
                            event.set()
                        continue

                    state = decode_state(frame)
                    if state is None:
                        continue
                    with self.state_condition:
                        self.last_state = state
                        self.last_state_monotonic = time.monotonic()
                        if state.mode == "manual" and 1 <= state.speed <= 6:
                            self.last_manual_speed = state.speed
                        self.state_counter += 1
                        self.state_condition.notify_all()
                    self._notify_state(state)
        except (ConnectionError, OSError):
            if not self.stop_event.is_set():
                _LOGGER.exception("Socket B connection error")
        finally:
            self._clear_device_connection(conn)
            try:
                conn.close()
            except OSError:
                pass
            _LOGGER.warning("Socket B disconnected from %s:%s", *addr)

    def run(self) -> None:
        """Run the blocking Socket B listener in its dedicated thread."""
        _LOGGER.info("Starting %s %s for %s", NAME, VERSION, self.config.device_id)
        try:
            threading.Thread(
                target=self.watchdog_loop,
                name=f"airproce-watchdog-{self.config.device_id}",
                daemon=True,
            ).start()

            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener_socket = listener
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.config.listen_host, self.config.listen_port))
            listener.listen(5)
            listener.settimeout(1.0)
            self.startup_event.set()

            _LOGGER.info(
                "Listening on %s:%s for USR client %s",
                self.config.listen_host,
                self.config.listen_port,
                self.config.usr_host,
            )
            while not self.stop_event.is_set():
                try:
                    conn, addr = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.stop_event.is_set():
                        break
                    raise
                threading.Thread(
                    target=self.handle_device,
                    args=(conn, addr),
                    name=f"airproce-client-{self.config.device_id}",
                    daemon=True,
                ).start()
        except Exception as exc:
            self.startup_error = exc
            self.startup_event.set()
            if not self.stop_event.is_set():
                _LOGGER.exception("AirProce listener fatal error")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Stop the bridge and close all sockets."""
        with self.shutdown_lock:
            if self.shutdown_done:
                return
            self.shutdown_done = True

        self.stop_event.set()
        self._notify_availability(False)

        listener = self.listener_socket
        self.listener_socket = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

        with self.device_lock:
            conn = self.device_socket
            self.device_socket = None
            self.device_address = None
            self.device_online = False
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def diagnostics(self) -> dict[str, Any]:
        """Return a non-secret runtime snapshot."""
        with self.device_lock, self.state_lock:
            state = asdict(self.last_state) if self.last_state is not None else None
            return {
                "device_online": self.device_online,
                "device_peer_port": (
                    self.device_address[1] if self.device_address is not None else None
                ),
                "last_manual_speed": self.last_manual_speed,
                "state_counter": self.state_counter,
                "last_state": state,
            }
