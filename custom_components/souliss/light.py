"""Souliss T1n on/off outputs as lights (T12 default, T11 via override)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity
from .helpers import T1N_ON_VALUES, slot_domain
from .protocol import const as pconst

AUTO_STATES = (pconst.T1N_AUTO_OFF_COIL, pconst.T1N_AUTO_ON_COIL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data
    async_add_entities(
        SoulissLight(gateway, node, slot, entry.entry_id)
        for node in gateway.nodes.values()
        for slot in node.slots.values()
        if slot_domain(entry, node.index, slot) == "light"
    )


class SoulissLight(SoulissSlotEntity, LightEntity):
    """A T1n on/off output, with the T12 automatic mode as an attribute."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def is_on(self) -> bool:
        return self._slot.value in T1N_ON_VALUES

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"auto_mode": self._slot.value in AUTO_STATES}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_ON_CMD)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_OFF_CMD)
