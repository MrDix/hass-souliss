"""Pure state/command helpers for multi-slot typicals (T16, T19, T31, T32, T1A).

Kept free of Home Assistant imports so the logic is unit-testable together
with the rest of the protocol package; the entity platforms are thin wrappers
around these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    T1N_SET_CMD,
    T3N_COOLING_MODE,
    T3N_COOLING_ON,
    T3N_FAN1_ON,
    T3N_FAN2_ON,
    T3N_FAN3_ON,
    T3N_FAN_AUTO_STATE,
    T3N_HEATING_ON,
    T3N_SET_TEMP_CMD,
    T3N_SYSTEM_ON,
    T32_POWER_OFF,
    T32_POWER_ON,
    T32_POWER_SAVE,
    T32_SWIRL_BIT,
    T32_TEMP_CODES,
)
from .frames import decode_half_float, encode_half_float

T32_TEMP_BY_CODE = {code: temp for temp, code in T32_TEMP_CODES.items()}


def t19_set_payload(brightness: int) -> bytes:
    """Set command for a T19: brightness 0-255 into the second slot."""
    if not 0 <= brightness <= 255:
        raise ValueError(f"brightness out of range: {brightness}")
    return bytes((T1N_SET_CMD, brightness))


def t16_set_payload(rgb: tuple[int, int, int], brightness: int) -> bytes:
    """Set command for a T16: RGB scaled by brightness into slots +1..+3.

    A T16 has no separate brightness channel; the firmware derives it as
    max(R, G, B), so the brightness is folded into the color bytes here.
    """
    if not 0 <= brightness <= 255:
        raise ValueError(f"brightness out of range: {brightness}")
    if any(not 0 <= channel <= 255 for channel in rgb):
        raise ValueError(f"rgb out of range: {rgb}")
    scaled = (round(channel * brightness / 255) for channel in rgb)
    return bytes((T1N_SET_CMD, *scaled))


def t16_color(raw: bytes) -> tuple[tuple[int, int, int], int] | None:
    """Split T16 raw state into (normalized RGB, brightness).

    Returns None while the strip is black (no color information to report).
    """
    if len(raw) < 4:
        return None
    red, green, blue = raw[1], raw[2], raw[3]
    peak = max(red, green, blue)
    if peak == 0:
        return None
    normalized = tuple(round(channel * 255 / peak) for channel in (red, green, blue))
    return normalized, peak


def t31_setpoint_payload(value: float) -> bytes:
    """Set-temperature command for a T31.

    The firmware copies IN slot+3/+4 into the setpoint on 0x0C; the two padding
    bytes land in the measured-value input slots where zeros are ignored.
    """
    return bytes((T3N_SET_TEMP_CMD, 0x00, 0x00)) + encode_half_float(value)


def t1a_bit(raw: bytes, bit: int) -> bool:
    """State of one of the eight inputs in a T1A slot (bit 0-7)."""
    if not 0 <= bit <= 7:
        raise ValueError(f"bit out of range: {bit}")
    if not raw:
        return False
    return bool(raw[0] & (1 << bit))


def t32_command(
    *,
    power: bool | None,
    mode: int,
    fan: int,
    temperature: int,
    eco: bool = False,
    swirl: bool = False,
) -> bytes:
    """Build the two-byte T32 command word 0xABCD.

    power True/False sets the on/off flag; None leaves the power state
    untouched (used to change fan/temperature without a power cycle).
    """
    if temperature not in T32_TEMP_CODES:
        raise ValueError(f"temperature out of range 16-30: {temperature}")
    flags = 0x0
    if power is True:
        flags |= T32_POWER_ON
    elif power is False:
        flags |= T32_POWER_OFF
    if eco:
        flags |= T32_POWER_SAVE
    byte0 = (flags << 4) | (T32_SWIRL_BIT if swirl else 0) | (fan & 0x7)
    byte1 = ((mode & 0xF) << 4) | T32_TEMP_CODES[temperature]
    return bytes((byte0, byte1))


@dataclass(frozen=True, slots=True)
class T32State:
    """Decoded two-byte T32 OUT area (echo of the last command word)."""

    power_on: bool
    eco: bool
    swirl: bool
    fan_code: int
    mode_code: int
    temperature: int | None

    @classmethod
    def from_raw(cls, raw: bytes) -> T32State:
        if len(raw) < 2:
            return cls(False, False, False, 0, 0, None)
        flags = raw[0] >> 4
        return cls(
            power_on=bool(flags & T32_POWER_ON),
            eco=bool(flags & T32_POWER_SAVE),
            swirl=bool(raw[0] & T32_SWIRL_BIT),
            fan_code=raw[0] & 0x7,
            mode_code=raw[1] >> 4,
            temperature=T32_TEMP_BY_CODE.get(raw[1] & 0x0F),
        )


@dataclass(frozen=True, slots=True)
class T31State:
    """Decoded 5-byte T31 OUT area (bitfield + two half-floats)."""

    bits: int
    measured: float | None
    setpoint: float | None

    @classmethod
    def from_raw(cls, raw: bytes) -> T31State:
        if len(raw) < 5:
            return cls(0, None, None)
        return cls(
            bits=raw[0],
            measured=decode_half_float(raw[1:3]),
            setpoint=decode_half_float(raw[3:5]),
        )

    @property
    def system_on(self) -> bool:
        return bool(self.bits & T3N_SYSTEM_ON)

    @property
    def cooling_mode(self) -> bool:
        """True = cooling mode, False = heating mode (bit 0x80)."""
        return bool(self.bits & T3N_COOLING_MODE)

    @property
    def heating_active(self) -> bool:
        return bool(self.bits & T3N_HEATING_ON)

    @property
    def cooling_active(self) -> bool:
        return bool(self.bits & T3N_COOLING_ON)

    @property
    def fan_auto(self) -> bool:
        return bool(self.bits & T3N_FAN_AUTO_STATE)

    @property
    def fan_level(self) -> int:
        """Manual fan level 0-3 derived from the three fan bits."""
        if self.bits & T3N_FAN3_ON:
            return 3
        if self.bits & T3N_FAN2_ON:
            return 2
        if self.bits & T3N_FAN1_ON:
            return 1
        return 0
