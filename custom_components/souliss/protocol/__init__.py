"""Standalone Souliss vNet/MaCaco protocol client (no Home Assistant imports)."""

from .gateway import (
    SoulissConnectionError,
    SoulissError,
    SoulissGateway,
    discover_gateways,
)
from .models import Node, Slot

__all__ = [
    "Node",
    "Slot",
    "SoulissConnectionError",
    "SoulissError",
    "SoulissGateway",
    "discover_gateways",
]
