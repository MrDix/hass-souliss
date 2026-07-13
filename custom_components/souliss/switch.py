"""Souliss T11 on/off outputs as switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity
from .protocol import const as pconst

ON_STATES = (
    pconst.T1N_ON_COIL,
    pconst.T1N_ON_FEEDBACK,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data
    async_add_entities(
        SoulissSwitch(gateway, node, slot, entry.entry_id)
        for node in gateway.nodes.values()
        for slot in node.slots.values()
        if slot.typical == pconst.T11
    )


class SoulissSwitch(SoulissSlotEntity, SwitchEntity):
    """A T11 digital output."""

    @property
    def is_on(self) -> bool:
        return self._slot.value in ON_STATES

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_ON_CMD)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_OFF_CMD)
