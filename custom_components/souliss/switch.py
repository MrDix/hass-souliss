"""Souliss T1n on/off outputs as switches (T11 default, T12 via override)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .helpers import T1N_ON_VALUES, slot_domain
from .protocol import Node, Slot
from .protocol import const as pconst


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> SoulissSwitch | None:
        if slot_domain(entry, node.index, slot) != "switch":
            return None
        return SoulissSwitch(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissSwitch(SoulissSlotEntity, SwitchEntity):
    """A T1n digital output."""

    @property
    def is_on(self) -> bool:
        return self._slot.value in T1N_ON_VALUES

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_ON_CMD)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_OFF_CMD)
