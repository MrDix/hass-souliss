"""Souliss T1n slots as momentary buttons (e.g. node reboot), via override."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity
from .helpers import slot_domain
from .protocol import const as pconst


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data
    async_add_entities(
        SoulissButton(gateway, node, slot, entry.entry_id)
        for node in gateway.nodes.values()
        for slot in node.slots.values()
        if slot_domain(entry, node.index, slot) == "button"
    )


class SoulissButton(SoulissSlotEntity, ButtonEntity):
    """Sends the T1n ON command once; used for reboot/pulse slots."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self._send_command(pconst.T1N_ON_CMD)
