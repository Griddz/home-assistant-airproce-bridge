"""Protocol regression tests that do not require a Home Assistant install."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_PROTOCOL_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "airproce_bridge"
    / "protocol.py"
)
_SPEC = spec_from_file_location("airproce_bridge_protocol_tests", _PROTOCOL_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_PROTOCOL = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PROTOCOL
_SPEC.loader.exec_module(_PROTOCOL)

COMMANDS = _PROTOCOL.COMMANDS
CONTROL_SPEED_INDEX = _PROTOCOL.CONTROL_SPEED_INDEX
FrameParser = _PROTOCOL.FrameParser
decode_state = _PROTOCOL.decode_state


def test_panel_fan4_state() -> None:
    frame = bytes.fromhex(
        "00 1c 00 09 01 2c 00 00 00 01 9f d0 d4 20 07 "
        "00 09 00 01 01 2e 02 09 00 29 00 00 04 01 01 11 00 00 00 00"
    )
    state = decode_state(frame)
    assert state is not None
    assert state.power is True
    assert state.mode == "manual"
    assert state.speed == 4
    assert state.pm25 == 9
    assert state.temperature == 30.2
    assert state.humidity == 52.1
    assert state.voc == 0.041


def test_power_off_state() -> None:
    state_block = bytes.fromhex(
        "00 07 00 01 01 1b 01 e0 00 3c 00 00 ff 11 01 11 00 00 00 00"
    )
    frame = bytes.fromhex(
        "00 1d ff fc 0b a9 00 c8 00 00 00 00 00 01 e2 40"
    ) + state_block
    state = decode_state(frame)
    assert state is not None
    assert state.power is False
    assert state.mode == "off"
    assert state.speed == 0


def test_stream_parser_handles_concatenated_frames() -> None:
    frame1 = bytes.fromhex("00 09 ff f9 0b 96 00 c8 00 00 00 00 00 01 e2 40")
    frame2 = bytes.fromhex(
        "00 1d ff fc 0b 97 00 c8 00 00 00 00 00 01 e2 40 "
        "00 07 00 01 01 1c 01 e4 00 35 00 00 04 01 01 11 00 00 00 00"
    )
    parser = FrameParser()
    assert parser.feed((frame1 + frame2)[:19]) == [frame1]
    assert parser.feed((frame1 + frame2)[19:]) == [frame2]


def test_sleep_context_byte_is_replaceable() -> None:
    command = bytearray(COMMANDS["sleep"])
    command[CONTROL_SPEED_INDEX] = 4
    assert command[-8:] == bytes.fromhex("04 20 01 13 00 00 00 00")
