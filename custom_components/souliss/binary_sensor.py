"""Souliss T1n inputs (e.g. PIR sensors) as binary sensors, via override."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity
from .helpers import T1N_ON_VALUES, slot_domain


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data
    async_add_entities(
        SoulissBinarySensor(gateway, node, slot, entry.entry_id)
        for node in gateway.nodes.values()
        for slot in node.slots.values()
        if slot_domain(entry, node.index, slot) == "binary_sensor"
    )


class SoulissBinarySensor(SoulissSlotEntity, BinarySensorEntity):
    """A read-only view of a T1n slot driven by the node itself."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    @property
    def is_on(self) -> bool:
        return self._slot.value in T1N_ON_VALUES
