"""Building and parsing of Souliss vNet/MaCaco frames."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from .const import (
    FC_DBSTRUCT_REQ,
    FC_DISCOVER_REQ,
    FC_FORCE,
    FC_HEALTH_REQ,
    FC_PING_REQ,
    FC_POLL_REQ,
    FC_SUBSCRIBE_REQ,
    FC_TYPICAL_REQ,
    MACACO_PORT,
    VNET_MAX_FRAME,
)

HALF_FLOAT_NAN_RAW = b"\x00\xfe"  # 0xFE00, "no value yet"


class FrameError(ValueError):
    """Raised when a datagram cannot be parsed as a vNet/MaCaco frame."""


@dataclass(frozen=True, slots=True)
class MacacoFrame:
    """A parsed MaCaco frame with its vNet addressing."""

    dest: int
    source: int
    funcode: int
    putin: int
    startoffset: int
    numberof: int
    payload: bytes


def build_macaco(
    funcode: int,
    startoffset: int = 0,
    numberof: int = 0,
    payload: bytes = b"",
    putin: int = 0,
) -> bytes:
    return bytes((funcode, putin & 0xFF, putin >> 8, startoffset, numberof)) + payload


def build_vnet(dest: int, source: int, macaco: bytes) -> bytes:
    """Wrap a MaCaco frame into a vNet-over-UDP payload."""
    vnet_len = 6 + len(macaco)
    frame = (
        bytes(
            (
                vnet_len + 1,
                vnet_len,
                MACACO_PORT,
                dest & 0xFF,
                dest >> 8,
                source & 0xFF,
                source >> 8,
            )
        )
        + macaco
    )
    if len(frame) > VNET_MAX_FRAME:
        raise FrameError(f"frame too long ({len(frame)} > {VNET_MAX_FRAME})")
    return frame


def parse_vnet(data: bytes) -> MacacoFrame:
    """Parse a UDP payload into a MaCaco frame."""
    if len(data) < 12:
        raise FrameError(f"datagram too short ({len(data)} bytes)")
    if data[0] != len(data) or data[1] != len(data) - 1:
        raise FrameError("length bytes do not match datagram size")
    if data[2] != MACACO_PORT:
        raise FrameError(f"unexpected vNet port 0x{data[2]:02x}")
    numberof = data[11]
    payload = bytes(data[12 : 12 + numberof])
    return MacacoFrame(
        dest=data[3] | (data[4] << 8),
        source=data[5] | (data[6] << 8),
        funcode=data[7],
        putin=data[8] | (data[9] << 8),
        startoffset=data[10],
        numberof=numberof,
        payload=payload,
    )


def ping() -> bytes:
    return build_macaco(FC_PING_REQ)


def discover() -> bytes:
    return build_macaco(FC_DISCOVER_REQ, putin=0x0005)


def db_struct() -> bytes:
    return build_macaco(FC_DBSTRUCT_REQ, numberof=7)


def typical_request(nodes: int, startoffset: int = 0) -> bytes:
    return build_macaco(FC_TYPICAL_REQ, startoffset=startoffset, numberof=nodes)


def subscribe(nodes: int) -> bytes:
    return build_macaco(FC_SUBSCRIBE_REQ, numberof=nodes)


def poll() -> bytes:
    return build_macaco(FC_POLL_REQ)


def health_request(nodes: int) -> bytes:
    return build_macaco(FC_HEALTH_REQ, numberof=nodes)


def force(node: int, slot: int, command: bytes) -> bytes:
    """Force command bytes into a node's IN area at the given slot.

    The payload always covers slots 0..slot; leading slots are padded with
    0x00 which every typical treats as "no command".
    """
    if not command:
        raise FrameError("force requires at least one command byte")
    payload = bytes(slot) + command
    return build_macaco(FC_FORCE, startoffset=node, numberof=len(payload), payload=payload)


def encode_half_float(value: float) -> bytes:
    return struct.pack("<e", value)


def decode_half_float(raw: bytes) -> float | None:
    """Decode a little-endian binary16; None when the node published no value yet."""
    value = struct.unpack("<e", raw)[0]
    if math.isnan(value) or math.isinf(value):
        return None
    return 0.0 if value == 0.0 else value
