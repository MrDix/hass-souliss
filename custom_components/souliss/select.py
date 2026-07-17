"""Mode selects (off / on / auto) for T12 typicals.

A T12 output has a third state next to plain on/off: the automatic mode,
where the node itself drives the output (e.g. PIR-controlled floodlights).
The light/switch entity only covers on/off, so each T12 slot gets a
companion select exposing all three states. It is disabled by default and
meant to be enabled only for slots that actually use the automatic mode.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .helpers import MODE_SELECT_DOMAINS, T1N_ON_VALUES, slot_domain
from .protocol import Node, Slot, SoulissGateway
from .protocol import const as pconst

AUTO_STATES = (pconst.T1N_AUTO_OFF_COIL, pconst.T1N_AUTO_ON_COIL)

OPTION_OFF = "off"
OPTION_ON = "on"
OPTION_AUTO = "auto"

COMMANDS = {
    OPTION_OFF: pconst.T1N_OFF_CMD,
    OPTION_ON: pconst.T1N_ON_CMD,
    OPTION_AUTO: pconst.T1N_AUTO_CMD,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> SoulissT12ModeSelect | None:
        if slot.typical != pconst.T12:
            return None
        if slot_domain(entry, node.index, slot) not in MODE_SELECT_DOMAINS:
            return None
        return SoulissT12ModeSelect(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissT12ModeSelect(SoulissSlotEntity, SelectEntity):
    """Three-state control for a T12 output: off, on or automatic."""

    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "t12_mode"
    _attr_options = [OPTION_OFF, OPTION_ON, OPTION_AUTO]

    def __init__(
        self, gateway: SoulissGateway, node: Node, slot: Slot, entry_id: str
    ) -> None:
        super().__init__(gateway, node, slot, entry_id)
        self._attr_unique_id = f"{entry_id}-{node.index}-{slot.index}-mode"
        # fallback when no translation is loaded; translations override it
        self._attr_name = f"Slot {slot.index} mode"
        self._attr_translation_placeholders = {"slot": str(slot.index)}

    @property
    def current_option(self) -> str:
        if self._slot.value in AUTO_STATES:
            return OPTION_AUTO
        if self._slot.value in T1N_ON_VALUES:
            return OPTION_ON
        return OPTION_OFF

    async def async_select_option(self, option: str) -> None:
        await self._send_command(COMMANDS[option])
