"""Souliss T21/T22 motorized devices as covers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity
from .protocol import const as pconst


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data
    async_add_entities(
        SoulissCover(gateway, node, slot, entry.entry_id)
        for node in gateway.nodes.values()
        for slot in node.slots.values()
        if slot.typical in (pconst.T21, pconst.T22)
    )


class SoulissCover(SoulissSlotEntity, CoverEntity):
    """A T22 motorized device (shutter, marquee, screen)."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    @property
    def is_opening(self) -> bool:
        return self._slot.value == pconst.T2N_COIL_OPEN

    @property
    def is_closing(self) -> bool:
        return self._slot.value == pconst.T2N_COIL_CLOSE

    @property
    def is_closed(self) -> bool | None:
        state = self._slot.value
        if state == pconst.T2N_STATE_CLOSE:
            return True
        if state == pconst.T2N_STATE_OPEN:
            return False
        # stopped mid-way or position unknown
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T2N_OPEN_CMD)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T2N_CLOSE_CMD)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T2N_STOP_CMD)
