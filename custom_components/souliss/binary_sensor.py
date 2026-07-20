"""Souliss T1n inputs (e.g. PIR sensors) as binary sensors, via override."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .helpers import T1N_ON_VALUES, slot_domain
from .protocol import Node, Slot, SoulissGateway
from .protocol import const as pconst


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> SoulissBinarySensor | None:
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
