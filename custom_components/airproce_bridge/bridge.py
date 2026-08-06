"""AirProce Socket B to MQTT bridge runtime."""

from __future__ import annotations

from dataclasses import asdict
import json
import logging
import socket
import threading
import time
from typing import Any, Final

import paho.mqtt.client as mqtt

from .const import (
    CONF_BASE_TOPIC,
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DISCOVERY_PREFIX,
    CONF_LISTEN_HOST,
    CONF_LISTEN_PORT,
    CONF_MQTT_HOST,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_USR_HOST,
    CONF_USR_PASSWORD,
    CONF_USR_USERNAME,
    CONF_USR_WEB_PORT,
    CONF_VERIFY_USR_WEB,
    CONF_WATCHDOG_SILENCE,
    CONF_WATCHDOG_TIMEOUT,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DISCOVERY_PREFIX,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_MQTT_PORT,
    DEFAULT_USR_PASSWORD,
    DEFAULT_USR_USERNAME,
    DEFAULT_USR_WEB_PORT,
    DEFAULT_VERIFY_USR_WEB,
    DEFAULT_WATCHDOG_SILENCE,
    DEFAULT_WATCHDOG_TIMEOUT,
    NAME,
    VERSION,
)
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


def _reason_code_value(reason_code: Any) -> int:
    """Return an integer Paho reason code for callback API v1 or v2."""
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


class AirProceBridge:
    """Manage Socket B, MQTT discovery, commands, state, and watchdog."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
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

        self.mqtt_connected = False
        self.mqtt = self._create_mqtt_client()

    @property
    def availability_topic(self) -> str:
        """Return availability topic."""
        return f"{self.config.base_topic}/availability"

    def _create_mqtt_client(self) -> mqtt.Client:
        client_id = f"airproce-bridge-{self.config.device_id}"
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                clean_session=True,
            )
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id=client_id, clean_session=True)

        if self.config.mqtt_username:
            client.username_pw_set(
                self.config.mqtt_username,
                self.config.mqtt_password,
            )
        client.will_set(
            self.availability_topic,
            payload="offline",
            qos=1,
            retain=True,
        )
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_mqtt_connect
        client.on_disconnect = self._on_mqtt_disconnect
        client.on_message = self._on_mqtt_message
        return client

    def _device_info(self) -> dict[str, Any]:
        return {
            "identifiers": [self.config.device_id],
            "name": self.config.device_name,
            "manufacturer": "AirProce",
            "model": self.config.device_model,
            "configuration_url": self.config.configuration_url,
            "sw_version": VERSION,
        }

    def _on_mqtt_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        code = _reason_code_value(reason_code)
        if code != 0:
            self.mqtt_connected = False
            _LOGGER.error(
                "MQTT connection rejected for %s: %s",
                self.config.device_id,
                reason_code,
            )
            return
        self.mqtt_connected = True
        _LOGGER.info("MQTT connected for %s", self.config.device_id)
        client.subscribe(f"{self.config.base_topic}/set/#", qos=1)
        self.publish_discovery()
        self.publish_availability("online" if self.device_online else "offline")
        if self.last_state is not None:
            self.publish_state(self.last_state)

    def _on_mqtt_disconnect(self, client: mqtt.Client, userdata: Any, *args: Any) -> None:
        self.mqtt_connected = False
        if not self.stop_event.is_set():
            _LOGGER.warning("MQTT disconnected for %s", self.config.device_id)

    def _on_mqtt_message(self, client: mqtt.Client, userdata: Any, msg: Any) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        _LOGGER.debug("MQTT command %s = %r", topic, payload)

        try:
            if topic.endswith("/set/power"):
                self.handle_power(payload)
            elif topic.endswith("/set/percentage"):
                self.handle_percentage(payload)
            elif topic.endswith("/set/preset"):
                self.handle_fan_preset(payload)
            elif topic.endswith("/set/speed"):
                self.handle_speed(payload)
            else:
                _LOGGER.warning("Unknown AirProce command topic: %s", topic)
        except Exception:
            _LOGGER.exception("Failed to handle AirProce MQTT command")

    def _discovery_topics(self) -> list[str]:
        prefix = self.config.discovery_prefix
        object_id = self.config.object_id
        return [
            f"{prefix}/fan/{object_id}/config",
            f"{prefix}/sensor/{object_id}_temperature/config",
            f"{prefix}/sensor/{object_id}_humidity/config",
            f"{prefix}/sensor/{object_id}_pm25/config",
            f"{prefix}/sensor/{object_id}_voc/config",
        ]

    def publish_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery configuration."""
        base = self.config.base_topic
        avail = self.availability_topic
        device = self._device_info()
        origin = {
            "name": NAME,
            "sw_version": VERSION,
            "support_url": "https://github.com/Griddz/home-assistant-airproce-bridge",
        }
        object_id = self.config.object_id

        discovery_messages = {
            f"{self.config.discovery_prefix}/fan/{object_id}/config": {
                "name": None,
                "unique_id": f"{object_id}_fan",
                "default_entity_id": f"fan.{object_id}",
                "icon": "mdi:air-purifier",
                "availability_topic": avail,
                "payload_available": "online",
                "payload_not_available": "offline",
                "command_topic": f"{base}/set/power",
                "state_topic": f"{base}/fan/state",
                "payload_on": "ON",
                "payload_off": "OFF",
                "percentage_command_topic": f"{base}/set/percentage",
                "percentage_state_topic": f"{base}/fan/percentage",
                "speed_range_min": 1,
                "speed_range_max": 6,
                "preset_modes": ["auto", "sleep"],
                "preset_mode_command_topic": f"{base}/set/preset",
                "preset_mode_state_topic": f"{base}/fan/preset",
                "payload_reset_preset_mode": "None",
                "json_attributes_topic": f"{base}/state",
                "optimistic": False,
                "retain": False,
                "device": device,
                "origin": origin,
            },
            f"{self.config.discovery_prefix}/sensor/{object_id}_temperature/config": {
                "name": "Temperature",
                "unique_id": f"{object_id}_temperature",
                "default_entity_id": f"sensor.{object_id}_temperature",
                "state_topic": f"{base}/sensor/temperature",
                "availability_topic": avail,
                "device_class": "temperature",
                "state_class": "measurement",
                "unit_of_measurement": "°C",
                "suggested_display_precision": 1,
                "device": device,
                "origin": origin,
            },
            f"{self.config.discovery_prefix}/sensor/{object_id}_humidity/config": {
                "name": "Humidity",
                "unique_id": f"{object_id}_humidity",
                "default_entity_id": f"sensor.{object_id}_humidity",
                "state_topic": f"{base}/sensor/humidity",
                "availability_topic": avail,
                "device_class": "humidity",
                "state_class": "measurement",
                "unit_of_measurement": "%",
                "suggested_display_precision": 1,
                "device": device,
                "origin": origin,
            },
            f"{self.config.discovery_prefix}/sensor/{object_id}_pm25/config": {
                "name": "PM2.5",
                "unique_id": f"{object_id}_pm25",
                "default_entity_id": f"sensor.{object_id}_pm25",
                "state_topic": f"{base}/sensor/pm25",
                "availability_topic": avail,
                "device_class": "pm25",
                "state_class": "measurement",
                "unit_of_measurement": "µg/m³",
                "suggested_display_precision": 0,
                "device": device,
                "origin": origin,
            },
            f"{self.config.discovery_prefix}/sensor/{object_id}_voc/config": {
                "name": "VOC",
                "unique_id": f"{object_id}_voc",
                "default_entity_id": f"sensor.{object_id}_voc",
                "state_topic": f"{base}/sensor/voc",
                "availability_topic": avail,
                "device_class": "volatile_organic_compounds",
                "state_class": "measurement",
                "unit_of_measurement": "mg/m³",
                "suggested_display_precision": 3,
                "device": device,
                "origin": origin,
            },
        }

        for topic, payload in discovery_messages.items():
            self.mqtt.publish(
                topic,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                qos=1,
                retain=True,
            )
        _LOGGER.info("Published MQTT discovery for %s", self.config.device_id)

    def clear_discovery(self) -> None:
        """Delete retained discovery messages for this config entry."""
        if not self.mqtt_connected:
            return
        for topic in self._discovery_topics():
            info = self.mqtt.publish(topic, payload="", qos=1, retain=True)
            try:
                info.wait_for_publish(timeout=2.0)
            except (RuntimeError, ValueError):
                _LOGGER.debug(
                    "Discovery cleanup was not confirmed for %s", topic, exc_info=True
                )

    def publish_availability(self, state: str) -> None:
        if self.mqtt_connected:
            self.mqtt.publish(self.availability_topic, state, qos=1, retain=True)

    def publish_state(self, state: PurifierState) -> None:
        if not self.mqtt_connected:
            return

        base = self.config.base_topic
        fan_state = "ON" if state.power else "OFF"
        native_speed = 0 if not state.power else (state.speed or self.last_manual_speed)
        preset = {"auto": "auto", "sleep": "sleep"}.get(state.mode, "None")

        state_payload = asdict(state)
        state_payload.update(
            {
                "fan_state": fan_state,
                "fan_native_speed": native_speed,
                "fan_preset": preset,
                "last_manual_speed": self.last_manual_speed,
            }
        )

        messages = {
            f"{base}/state": json.dumps(state_payload, ensure_ascii=False),
            f"{base}/sensor/temperature": f"{state.temperature:.1f}",
            f"{base}/sensor/humidity": f"{state.humidity:.1f}",
            f"{base}/sensor/pm25": str(state.pm25),
            f"{base}/sensor/voc": f"{state.voc:.3f}",
            f"{base}/fan/state": fan_state,
            f"{base}/fan/percentage": str(native_speed),
            f"{base}/fan/preset": preset,
        }
        for topic, payload in messages.items():
            self.mqtt.publish(topic, payload, qos=1, retain=True)

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

    def handle_power(self, payload: str) -> None:
        value = payload.strip().lower()
        if value in ("on", "1", "true"):
            self.send_command("power_on")
        elif value in ("off", "0", "false"):
            self.send_command("power_off")
        else:
            raise ValueError(f"Unsupported power payload: {payload!r}")

    def handle_percentage(self, payload: str) -> None:
        value = payload.strip().lower().replace("%", "")
        native_speed = int(round(float(value)))
        if native_speed == 0:
            self.send_command("power_off")
            return
        if native_speed not in range(1, 7):
            raise ValueError("Fan native speed must be 1..6")
        self.send_command(f"fan_{native_speed}")

    def handle_fan_preset(self, payload: str) -> None:
        value = payload.strip().lower()
        if value in ("none", "manual", ""):
            self.send_command(f"fan_{self.last_manual_speed}")
        elif value == "auto":
            self.send_command("auto", self._current_context_speed())
        elif value == "sleep":
            self.send_command("sleep", self._current_context_speed())
        else:
            raise ValueError(f"Unsupported fan preset payload: {payload!r}")

    def handle_speed(self, payload: str) -> None:
        speed = int(payload.strip().lower().replace("档", ""))
        if speed not in range(1, 7):
            raise ValueError("Fan speed must be 1..6")
        self.send_command(f"fan_{speed}")

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
        self.publish_availability("online")
        threading.Timer(0.5, self.request_state_async, args=("connect",)).start()

    def _clear_device_connection(self, conn: socket.socket) -> None:
        with self.device_lock:
            if self.device_socket is not conn:
                return
            self.device_socket = None
            self.device_address = None
            self.device_online = False
            self.device_connected_monotonic = 0.0
            self.last_rx_monotonic = 0.0
        self.publish_availability("offline")

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
                    self.publish_state(state)
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
        """Run the blocking bridge loop in its dedicated thread."""
        _LOGGER.info("Starting %s %s for %s", NAME, VERSION, self.config.device_id)
        try:
            self.mqtt.connect_async(
                self.config.mqtt_host,
                self.config.mqtt_port,
                keepalive=60,
            )
            self.mqtt.loop_start()

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
                _LOGGER.exception("AirProce bridge fatal error")
        finally:
            self.shutdown(clear_discovery=False)

    def shutdown(self, *, clear_discovery: bool) -> None:
        """Stop the bridge and close all sockets."""
        with self.shutdown_lock:
            if self.shutdown_done:
                return
            self.shutdown_done = True

        self.stop_event.set()
        self.publish_availability("offline")
        if clear_discovery:
            self.clear_discovery()

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
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

        try:
            self.mqtt.disconnect()
        except Exception:
            pass
        self.mqtt.loop_stop()

    def diagnostics(self) -> dict[str, Any]:
        """Return a non-secret runtime snapshot."""
        with self.device_lock, self.state_lock:
            state = asdict(self.last_state) if self.last_state is not None else None
            return {
                "device_online": self.device_online,
                "device_peer_port": (
                    self.device_address[1] if self.device_address is not None else None
                ),
                "mqtt_connected": self.mqtt_connected,
                "last_manual_speed": self.last_manual_speed,
                "state_counter": self.state_counter,
                "last_state": state,
            }
