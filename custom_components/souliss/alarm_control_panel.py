"""Souliss T41 anti-theft as alarm control panel."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .protocol import Node, Slot
from .protocol import const as pconst

STATE_MAP = {
    pconst.T4N_STATE_DISARMED: AlarmControlPanelState.DISARMED,
    pconst.T4N_STATE_ARMED: AlarmControlPanelState.ARMED_AWAY,
    pconst.T4N_STATE_IN_ALARM: AlarmControlPanelState.TRIGGERED,
    pconst.T4N_STATE_REARMING: AlarmControlPanelState.ARMING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> SoulissAlarmPanel | None:
        if slot.typical != pconst.T41:
            return None
        return SoulissAlarmPanel(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissAlarmPanel(SoulissSlotEntity, AlarmControlPanelEntity):
    """A T41 anti-theft main logic."""

    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY
    _attr_code_arm_required = False

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        return STATE_MAP.get(self._slot.value)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._send_command(pconst.T4N_ARM_CMD)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._send_command(pconst.T4N_DISARM_CMD)
