"""Souliss T31 temperature control as climate entities."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .protocol import Node, Slot
from .protocol import const as pconst
from .protocol.typicals import T31State, t31_setpoint_payload

FAN_LEVELS = {0: FAN_OFF, 1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH}
FAN_COMMANDS = {
    FAN_OFF: pconst.T3N_FAN_OFF_CMD,
    FAN_LOW: pconst.T3N_FAN_LOW_CMD,
    FAN_MEDIUM: pconst.T3N_FAN_MED_CMD,
    FAN_HIGH: pconst.T3N_FAN_HIGH_CMD,
}
# the node processes one IN command per logic cycle; give it a moment
# between the fan-manual command and the requested speed
COMMAND_GAP = 0.3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> SoulissClimate | None:
        if slot.typical != pconst.T31:
            return None
        return SoulissClimate(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissClimate(SoulissSlotEntity, ClimateEntity):
    """A T31 heating/cooling controller (bitfield + measured + setpoint)."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_fan_modes = [FAN_AUTO, FAN_OFF, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5

    @property
    def _state(self) -> T31State:
        return T31State.from_raw(self._slot.raw)

    @property
    def hvac_mode(self) -> HVACMode:
        state = self._state
        if not state.system_on:
            return HVACMode.OFF
        return HVACMode.COOL if state.cooling_mode else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        state = self._state
        if not state.system_on:
            return HVACAction.OFF
        if state.heating_active:
            return HVACAction.HEATING
        if state.cooling_active:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self._state.measured

    @property
    def target_temperature(self) -> float | None:
        return self._state.setpoint

    @property
    def fan_mode(self) -> str:
        state = self._state
        if state.fan_auto:
            return FAN_AUTO
        return FAN_LEVELS[state.fan_level]

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self._gateway.send_command(
            self._node.index, self._slot.index, t31_setpoint_payload(temperature)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._send_command(pconst.T3N_SHUTDOWN_CMD)
        elif hvac_mode == HVACMode.COOL:
            await self._send_command(pconst.T3N_COOLING_CMD)
        else:
            await self._send_command(pconst.T3N_HEATING_CMD)

    async def async_turn_on(self) -> None:
        # any mode command also sets the system-on bit; keep the current mode
        mode = HVACMode.COOL if self._state.cooling_mode else HVACMode.HEAT
        await self.async_set_hvac_mode(mode)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if fan_mode == FAN_AUTO:
            await self._send_command(pconst.T3N_FAN_AUTO_CMD)
            return
        await self._send_command(pconst.T3N_FAN_MANUAL_CMD)
        await asyncio.sleep(COMMAND_GAP)
        await self._send_command(FAN_COMMANDS[fan_mode])
