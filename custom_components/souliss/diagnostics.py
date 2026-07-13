"""Diagnostics support for the Souliss integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SoulissConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SoulissConfigEntry
) -> dict[str, Any]:
    gateway = entry.runtime_data
    return {
        "connected": gateway.connected,
        "node_count": gateway.node_count,
        "slots_per_node": gateway.slots_per_node,
        "nodes": {
            node.index: {
                "health": node.health,
                "alive": node.alive,
                "slots": {
                    slot.index: {
                        "typical": f"0x{slot.typical:02x}",
                        "size": slot.size,
                        "raw": slot.raw.hex(),
                        "analog_value": slot.analog_value if slot.is_analog else None,
                    }
                    for slot in node.slots.values()
                },
            }
            for node in gateway.nodes.values()
        },
    }
