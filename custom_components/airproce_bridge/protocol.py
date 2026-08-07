"""Reverse-engineered AirProce AI-600 protocol primitives."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Final

_LOGGER = logging.getLogger(__name__)
DEBUG_FRAME_MAX_BYTES: Final = 64

# Captured CLOUD_TO_DEVICE control frames. The dynamic sequence and timestamp
# bytes are not validated by the tested AI-600 firmware and can be replayed.
# The first control byte of auto/sleep is replaced with the current fan context.
_COMMAND_HEX: Final = {
    "fan_1": "00 10 00 07 0b a4 1e 00 00 01 9f d0 e9 bd ee 01 01 01 13 00 00 00 00",
    "fan_2": "00 10 00 07 0b 91 7c 00 00 01 9f d0 e7 22 9a 02 01 01 13 00 00 00 00",
    "fan_3": "00 10 00 07 0b 93 9f 00 00 01 9f d0 e7 4b 87 03 01 01 13 00 00 00 00",
    "fan_4": "00 10 00 07 0b 96 95 00 00 01 9f d0 e7 80 f3 04 01 01 13 00 00 00 00",
    "fan_5": "00 10 00 07 0b af 59 00 00 01 9f d0 ea 5b ea 05 01 01 13 00 00 00 00",
    "fan_6": "00 10 00 07 0b 9b b0 00 00 01 9f d0 e7 f3 e4 06 01 01 13 00 00 00 00",
    "auto": "00 10 00 07 0b 9e 28 00 00 01 9f d0 e8 5c df 06 02 01 13 00 00 00 00",
    "sleep": "00 10 00 07 0b a1 1d 00 00 01 9f d0 e8 dd 20 06 20 01 13 00 00 00 00",
    "power_off": "00 10 00 07 0b a8 c1 00 00 01 9f d0 e9 f1 a6 01 10 01 13 00 00 00 00",
    "power_on": "00 10 00 07 0b ab 27 00 00 01 9f d0 ea 20 92 01 00 01 13 00 00 00 00",
}
COMMANDS: Final = {name: bytes.fromhex(value) for name, value in _COMMAND_HEX.items()}
CONTROL_SPEED_INDEX: Final = 15
STATUS_QUERY: Final = bytes.fromhex(
    "00 08 00 04 0b 97 25 00 00 01 9f d0 e7 81 af"
)


def _debug_frame(frame: bytes) -> None:
    """Log one bounded RX frame only while HA debug logging is enabled."""
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return
    sample = frame[:DEBUG_FRAME_MAX_BYTES]
    suffix = " ..." if len(frame) > DEBUG_FRAME_MAX_BYTES else ""
    _LOGGER.debug(
        "RX frame len=%d: %s%s",
        len(frame),
        sample.hex(" "),
        suffix,
    )


@dataclass(slots=True)
class PurifierState:
    """Decoded purifier state."""

    power: bool
    mode: str
    speed: int
    pm25: int
    temperature: float
    humidity: float
    voc: float
    raw_mode_code: int
    raw_speed_code: int


class FrameParser:
    """Parse the AirProce TCP stream using total length = header length + 7."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Feed bytes and return complete protocol frames."""
        self.buffer.extend(data)
        frames: list[bytes] = []

        while True:
            if len(self.buffer) < 2:
                break
            if self.buffer[0] != 0x00:
                del self.buffer[0]
                continue

            payload_length = int.from_bytes(self.buffer[0:2], "big")
            total_length = payload_length + 7
            if total_length < 8 or total_length > 4096:
                del self.buffer[0]
                continue
            if len(self.buffer) < total_length:
                break

            frame = bytes(self.buffer[:total_length])
            frames.append(frame)
            _debug_frame(frame)
            del self.buffer[:total_length]

        return frames


def decode_state(frame: bytes) -> PurifierState | None:
    """Decode a confirmed 20-byte state block at the end of a frame."""
    if len(frame) < 20:
        return None

    state = frame[-20:]
    if state[2:4] != b"\x00\x01":
        return None
    if state[10:12] != b"\x00\x00":
        return None
    if state[14] != 0x01 or state[16:20] != b"\x00\x00\x00\x00":
        return None

    pm25 = int.from_bytes(state[0:2], "big")
    temperature = int.from_bytes(state[4:6], "big") / 10.0
    humidity = int.from_bytes(state[6:8], "big") / 10.0
    voc = int.from_bytes(state[8:10], "big") / 1000.0
    speed_code = state[12]
    mode_code = state[13]

    if not (0 <= pm25 <= 5000):
        return None
    if not (-40.0 <= temperature <= 100.0):
        return None
    if not (0.0 <= humidity <= 100.0):
        return None
    if not (0.0 <= voc <= 65.535):
        return None

    if speed_code == 0xFF and mode_code == 0x11:
        power = False
        mode = "off"
        speed = 0
    elif mode_code == 0x02:
        power = True
        mode = "auto"
        speed = speed_code if 1 <= speed_code <= 6 else 0
    elif mode_code in (0x20, 0x21, 0x22):
        power = True
        mode = "sleep"
        speed = speed_code if 1 <= speed_code <= 6 else 0
    elif mode_code == 0x01 and 1 <= speed_code <= 6:
        power = True
        mode = "manual"
        speed = speed_code
    else:
        power = speed_code != 0xFF
        mode = "unknown"
        speed = speed_code if 1 <= speed_code <= 6 else 0

    decoded = PurifierState(
        power=power,
        mode=mode,
        speed=speed,
        pm25=pm25,
        temperature=temperature,
        humidity=humidity,
        voc=voc,
        raw_mode_code=mode_code,
        raw_speed_code=speed_code,
    )
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "Decoded state: power=%s mode=%s speed=%d pm25=%d temp=%.1f humidity=%.1f voc=%.3f raw_mode=0x%02x raw_speed=0x%02x",
            decoded.power,
            decoded.mode,
            decoded.speed,
            decoded.pm25,
            decoded.temperature,
            decoded.humidity,
            decoded.voc,
            decoded.raw_mode_code,
            decoded.raw_speed_code,
        )
    return decoded
