"""Souliss T1n outputs as lights (T12 default, T11 via override, T16/T19 native)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .helpers import T1N_ON_VALUES, slot_domain
from .protocol import Node, Slot
from .protocol import const as pconst
from .protocol.typicals import t16_color, t16_set_payload, t19_set_payload

AUTO_STATES = (pconst.T1N_AUTO_OFF_COIL, pconst.T1N_AUTO_ON_COIL)
# dimmable typicals also report the timed-on feedback as an on state
DIMMER_ON_VALUES = (*T1N_ON_VALUES, pconst.T1N_TIMED_ON_COIL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> LightEntity | None:
        if slot.typical == pconst.T19:
            return SoulissDimmableLight(gateway, node, slot, entry.entry_id)
        if slot.typical == pconst.T16:
            return SoulissRgbLight(gateway, node, slot, entry.entry_id)
        if slot_domain(entry, node.index, slot) != "light":
            return None
        return SoulissLight(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


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


class SoulissDimmableLight(SoulissSlotEntity, LightEntity):
    """A T19 single-channel dimmable LED (state slot + brightness slot)."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool:
        return self._slot.value in DIMMER_ON_VALUES

    @property
    def brightness(self) -> int | None:
        raw = self._slot.raw
        return raw[1] if len(raw) > 1 else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            await self._send_command(pconst.T1N_ON_CMD)
            return
        await self._gateway.send_command(
            self._node.index, self._slot.index, t19_set_payload(brightness)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_OFF_CMD)


class SoulissRgbLight(SoulissSlotEntity, LightEntity):
    """A T16 RGB strip (state slot + R/G/B slots, brightness = max channel)."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    @property
    def is_on(self) -> bool:
        return self._slot.value in DIMMER_ON_VALUES

    @property
    def brightness(self) -> int | None:
        color = t16_color(self._slot.raw)
        return color[1] if color else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        color = t16_color(self._slot.raw)
        return color[0] if color else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if rgb is None and brightness is None:
            await self._send_command(pconst.T1N_ON_CMD)
            return
        if rgb is None:
            rgb = self.rgb_color or (255, 255, 255)
        if brightness is None:
            brightness = self.brightness or 255
        await self._gateway.send_command(
            self._node.index, self._slot.index, t16_set_payload(rgb, brightness)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(pconst.T1N_OFF_CMD)
