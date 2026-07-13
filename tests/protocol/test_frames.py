"""Tests for vNet/MaCaco frame building and parsing."""

import math
import struct

import pytest
from protocol import frames
from protocol.frames import FrameError


def test_ping_datagram_matches_reference() -> None:
    # Reference example from the OpenHAB binding: gateway 192.168.1.77 (0x004D),
    # client source user 70 / node 120 (0x4678).
    frame = frames.build_vnet(0x004D, 0x4678, frames.ping())
    assert frame == bytes.fromhex("0C 0B 17 4D 00 78 46 08 00 00 00 00")


def test_force_zero_pads_leading_slots() -> None:
    macaco = frames.force(node=2, slot=3, command=bytes([0x02]))
    assert macaco == bytes.fromhex("33 00 00 02 04 00 00 00 02")


def test_force_requires_command() -> None:
    with pytest.raises(FrameError):
        frames.force(0, 0, b"")


def test_subscribe_and_dbstruct() -> None:
    assert frames.subscribe(11) == bytes.fromhex("21 00 00 00 0B")
    assert frames.db_struct() == bytes.fromhex("26 00 00 00 07")


def test_parse_roundtrip() -> None:
    macaco = frames.build_macaco(0x31, startoffset=4, numberof=3, payload=b"\x01\x02\x03")
    data = frames.build_vnet(0x4678, 0x000A, macaco)
    parsed = frames.parse_vnet(data)
    assert parsed.dest == 0x4678
    assert parsed.source == 0x000A
    assert parsed.funcode == 0x31
    assert parsed.startoffset == 4
    assert parsed.payload == b"\x01\x02\x03"


def test_parse_rejects_bad_length() -> None:
    macaco = frames.build_macaco(0x18)
    data = bytearray(frames.build_vnet(0x4678, 0x000A, macaco))
    data[0] += 1
    with pytest.raises(FrameError):
        frames.parse_vnet(bytes(data))
    with pytest.raises(FrameError):
        frames.parse_vnet(b"\x01\x02")


def test_frame_length_limit() -> None:
    with pytest.raises(FrameError):
        frames.build_vnet(1, 2, frames.build_macaco(0x33, numberof=56, payload=bytes(56)))


def test_half_float_roundtrip() -> None:
    assert frames.decode_half_float(frames.encode_half_float(21.5)) == 21.5
    assert frames.decode_half_float(b"\x00\x80") == 0.0  # -0.0 encodes 0.0
    assert frames.decode_half_float(b"\x00\xfe") is None  # NaN = no value yet
    packed = struct.pack("<e", math.inf)
    assert frames.decode_half_float(packed) is None
