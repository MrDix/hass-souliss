"""Souliss inputs as binary sensors (T13 native, T11/T12 via override, T1A, T42)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .helpers import T1N_ON_VALUES, slot_domain
from .protocol import Node, Slot, SoulissGateway
from .protocol import const as pconst
from .protocol.typicals import t1a_bit


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> Entity | list[Entity] | None:
        if slot.typical == pconst.T1A:
            return [
                SoulissT1AInput(gateway, node, slot, entry.entry_id, bit)
                for bit in range(8)
            ]
        if slot.typical == pconst.T42:
            return SoulissT42AlarmSensor(gateway, node, slot, entry.entry_id)
        if slot_domain(entry, node.index, slot) != "binary_sensor":
            return None
        return SoulissBinarySensor(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissBinarySensor(SoulissSlotEntity, BinarySensorEntity):
    """A read-only view of a T1n slot driven by the node itself."""

    def __init__(
        self, gateway: SoulissGateway, node: Node, slot: Slot, entry_id: str
    ) -> None:
        super().__init__(gateway, node, slot, entry_id)
        if slot.typical != pconst.T13:
            # T11/T12 mapped to a binary sensor are PIR inputs in practice;
            # a native T13 is a generic digital input, no class assumed
            self._attr_device_class = BinarySensorDeviceClass.MOTION

    @property
    def is_on(self) -> bool:
        return self._slot.value in T1N_ON_VALUES


class SoulissT1AInput(SoulissSlotEntity, BinarySensorEntity):
    """One of the eight digital inputs bundled in a T1A slot."""

    def __init__(
        self,
        gateway: SoulissGateway,
        node: Node,
        slot: Slot,
        entry_id: str,
        bit: int,
    ) -> None:
        super().__init__(gateway, node, slot, entry_id)
        self._bit = bit
        self._attr_unique_id = f"{entry_id}-{node.index}-{slot.index}-bit{bit}"
        self._attr_name = f"Slot {slot.index} input {bit + 1}"

    @property
    def is_on(self) -> bool:
        return t1a_bit(self._slot.raw, self._bit)


class SoulissT42AlarmSensor(SoulissSlotEntity, BinarySensorEntity):
    """A T42 anti-theft peer: latched alarm state, cleared by a chain rearm."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    @property
    def is_on(self) -> bool:
        return self._slot.value == pconst.T42_STATE_ALARM
