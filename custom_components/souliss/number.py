"""Souliss T6n analog setpoints as number entities."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .protocol import Node, Slot
from .protocol import const as pconst


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> SoulissSetpoint | None:
        if slot.typical not in pconst.ANALOG_SETPOINT_TYPICALS:
            return None
        return SoulissSetpoint(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissSetpoint(SoulissSlotEntity, NumberEntity):
    """A T6n writable half-precision analog value."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    @property
    def native_value(self) -> float | None:
        return self._slot.analog_value

    async def async_set_native_value(self, value: float) -> None:
        await self._gateway.send_setpoint(self._node.index, self._slot.index, value)
