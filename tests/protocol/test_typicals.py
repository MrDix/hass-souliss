"""Tests for the T16/T19/T31 state and command helpers."""

import pytest
from protocol import const
from protocol.frames import decode_half_float, encode_half_float
from protocol.typicals import (
    T31State,
    T32State,
    t1a_bit,
    t16_color,
    t16_set_payload,
    t19_set_payload,
    t31_setpoint_payload,
    t32_command,
)


def test_t19_set_payload() -> None:
    assert t19_set_payload(0) == bytes((const.T1N_SET_CMD, 0))
    assert t19_set_payload(255) == bytes((const.T1N_SET_CMD, 255))
    with pytest.raises(ValueError):
        t19_set_payload(256)
    with pytest.raises(ValueError):
        t19_set_payload(-1)


def test_t16_set_payload_scales_by_brightness() -> None:
    assert t16_set_payload((255, 128, 0), 255) == bytes(
        (const.T1N_SET_CMD, 255, 128, 0)
    )
    assert t16_set_payload((255, 128, 0), 128) == bytes(
        (const.T1N_SET_CMD, 128, 64, 0)
    )
    assert t16_set_payload((10, 10, 10), 0) == bytes((const.T1N_SET_CMD, 0, 0, 0))
    with pytest.raises(ValueError):
        t16_set_payload((256, 0, 0), 255)
    with pytest.raises(ValueError):
        t16_set_payload((0, 0, 0), 300)


def test_t16_color_normalizes_and_reports_peak() -> None:
    # full red at half brightness
    assert t16_color(bytes((const.T1N_ON_COIL, 128, 0, 0))) == ((255, 0, 0), 128)
    # white at full brightness
    assert t16_color(bytes((const.T1N_ON_COIL, 255, 255, 255))) == (
        (255, 255, 255),
        255,
    )
    # black strip carries no color information
    assert t16_color(bytes((const.T1N_OFF_COIL, 0, 0, 0))) is None
    # short raw (typical not yet published)
    assert t16_color(b"\x00") is None


def test_t16_roundtrip() -> None:
    payload = t16_set_payload((255, 0, 0), 128)
    raw = bytes((const.T1N_ON_COIL,)) + payload[1:]
    assert t16_color(raw) == ((255, 0, 0), 128)


def test_t31_setpoint_payload_layout() -> None:
    payload = t31_setpoint_payload(21.5)
    assert payload[0] == const.T3N_SET_TEMP_CMD
    # measured-value input slots stay zero so the node ignores them
    assert payload[1:3] == b"\x00\x00"
    assert decode_half_float(payload[3:5]) == 21.5
    assert len(payload) == 5


def test_t31_state_decoding() -> None:
    raw = (
        bytes(
            (
                const.T3N_SYSTEM_ON
                | const.T3N_HEATING_ON
                | const.T3N_FAN1_ON
                | const.T3N_FAN2_ON,
            )
        )
        + encode_half_float(20.5)
        + encode_half_float(22.0)
    )
    state = T31State.from_raw(raw)
    assert state.system_on
    assert not state.cooling_mode
    assert state.heating_active
    assert not state.cooling_active
    assert not state.fan_auto
    assert state.fan_level == 2
    assert state.measured == 20.5
    assert state.setpoint == 22.0


def test_t31_state_cooling_and_auto_fan() -> None:
    bits = (
        const.T3N_SYSTEM_ON
        | const.T3N_COOLING_MODE
        | const.T3N_COOLING_ON
        | const.T3N_FAN_AUTO_STATE
        | const.T3N_FAN3_ON
    )
    state = T31State.from_raw(bytes((bits, 0, 0, 0, 0)))
    assert state.cooling_mode
    assert state.cooling_active
    assert state.fan_auto
    assert state.fan_level == 3


def test_t31_state_short_raw() -> None:
    state = T31State.from_raw(b"\x00")
    assert not state.system_on
    assert state.measured is None
    assert state.setpoint is None


def test_t1a_bit() -> None:
    raw = bytes((0b1010_0001,))
    assert t1a_bit(raw, 0)
    assert not t1a_bit(raw, 1)
    assert t1a_bit(raw, 5)
    assert t1a_bit(raw, 7)
    assert not t1a_bit(b"", 0)
    with pytest.raises(ValueError):
        t1a_bit(raw, 8)


def test_t32_command_word_layout() -> None:
    word = t32_command(
        power=True,
        mode=const.T32_MODE_COOL,
        fan=const.T32_FAN_HIGH,
        temperature=21,
    )
    # A=on(0x8), B=fan high(0x2), C=cool(0x7), D=21°C code(0x05)
    assert word == bytes((0x82, 0x75))

    off = t32_command(
        power=False,
        mode=const.T32_MODE_COOL,
        fan=const.T32_FAN_HIGH,
        temperature=21,
    )
    assert off[0] >> 4 == const.T32_POWER_OFF

    neutral = t32_command(
        power=None,
        mode=const.T32_MODE_HEAT,
        fan=const.T32_FAN_AUTO,
        temperature=30,
        eco=True,
        swirl=True,
    )
    assert neutral[0] >> 4 == const.T32_POWER_SAVE
    assert neutral[0] & const.T32_SWIRL_BIT
    assert neutral[0] & 0x7 == const.T32_FAN_AUTO
    assert neutral[1] == (const.T32_MODE_HEAT << 4) | const.T32_TEMP_CODES[30]

    with pytest.raises(ValueError):
        t32_command(
            power=True, mode=const.T32_MODE_AUTO, fan=const.T32_FAN_AUTO,
            temperature=15,
        )


def test_t32_roundtrip() -> None:
    word = t32_command(
        power=True,
        mode=const.T32_MODE_HEAT,
        fan=const.T32_FAN_LOW,
        temperature=26,
        eco=True,
    )
    state = T32State.from_raw(word)
    assert state.power_on
    assert state.eco
    assert not state.swirl
    assert state.fan_code == const.T32_FAN_LOW
    assert state.mode_code == const.T32_MODE_HEAT
    assert state.temperature == 26


def test_t32_state_off_and_short() -> None:
    off_echo = t32_command(
        power=False, mode=const.T32_MODE_COOL, fan=const.T32_FAN_AUTO,
        temperature=24,
    )
    assert not T32State.from_raw(off_echo).power_on
    blank = T32State.from_raw(b"\x00")
    assert not blank.power_on
    assert blank.temperature is None


def test_t32_temp_codes_complete() -> None:
    assert sorted(const.T32_TEMP_CODES) == list(range(16, 31))
    # hardware encoding is a bijection
    assert len(set(const.T32_TEMP_CODES.values())) == 15
