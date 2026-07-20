"""Souliss T31 temperature control and T32 air conditioners as climate entities."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import SoulissSlotEntity, async_setup_slot_entities
from .protocol import Node, Slot
from .protocol import const as pconst
from .protocol.typicals import (
    T31State,
    T32State,
    t31_setpoint_payload,
    t32_command,
)

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

T32_MODE_TO_HVAC = {
    pconst.T32_MODE_AUTO: HVACMode.AUTO,
    pconst.T32_MODE_COOL: HVACMode.COOL,
    pconst.T32_MODE_DRY: HVACMode.DRY,
    pconst.T32_MODE_FAN: HVACMode.FAN_ONLY,
    pconst.T32_MODE_HEAT: HVACMode.HEAT,
}
T32_HVAC_TO_MODE = {hvac: code for code, hvac in T32_MODE_TO_HVAC.items()}
T32_FAN_TO_HA = {
    pconst.T32_FAN_AUTO: FAN_AUTO,
    pconst.T32_FAN_LOW: FAN_LOW,
    pconst.T32_FAN_MED: FAN_MEDIUM,
    pconst.T32_FAN_HIGH: FAN_HIGH,
}
T32_HA_TO_FAN = {ha: code for code, ha in T32_FAN_TO_HA.items()}
T32_DEFAULT_TEMP = 24


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data

    def _factory(node: Node, slot: Slot) -> Entity | None:
        if slot.typical == pconst.T31:
            return SoulissClimate(gateway, node, slot, entry.entry_id)
        if slot.typical == pconst.T32:
            return SoulissAirConditioner(gateway, node, slot, entry.entry_id)
        return None

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


class SoulissAirConditioner(SoulissSlotEntity, ClimateEntity):
    """A T32 air-conditioner remote (two-byte command word, state = echo).

    The typical is a pass-through remote: the node maps the command word to
    the appliance (usually via IR), and the OUT area only echoes the last
    word sent — there is no feedback from the appliance itself.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.HEAT,
    ]
    _attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_preset_modes = [PRESET_NONE, PRESET_ECO]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = 16.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 1.0

    @property
    def _state(self) -> T32State:
        return T32State.from_raw(self._slot.raw)

    @property
    def hvac_mode(self) -> HVACMode:
        state = self._state
        if not state.power_on:
            return HVACMode.OFF
        return T32_MODE_TO_HVAC.get(state.mode_code, HVACMode.AUTO)

    @property
    def target_temperature(self) -> float | None:
        temperature = self._state.temperature
        return float(temperature) if temperature is not None else None

    @property
    def fan_mode(self) -> str:
        return T32_FAN_TO_HA.get(self._state.fan_code, FAN_AUTO)

    @property
    def preset_mode(self) -> str:
        return PRESET_ECO if self._state.eco else PRESET_NONE

    async def _send_word(
        self,
        *,
        power: bool | None,
        hvac_mode: HVACMode | None = None,
        fan_mode: str | None = None,
        temperature: int | None = None,
        eco: bool | None = None,
    ) -> None:
        """Re-encode the full command word from current state plus changes."""
        state = self._state
        if hvac_mode is not None:
            mode_code = T32_HVAC_TO_MODE[hvac_mode]
        elif state.mode_code in T32_MODE_TO_HVAC:
            mode_code = state.mode_code
        else:
            mode_code = pconst.T32_MODE_AUTO
        fan_code = (
            T32_HA_TO_FAN[fan_mode]
            if fan_mode is not None
            else (state.fan_code if state.fan_code in T32_FAN_TO_HA else pconst.T32_FAN_AUTO)
        )
        await self._gateway.send_command(
            self._node.index,
            self._slot.index,
            t32_command(
                power=power,
                mode=mode_code,
                fan=fan_code,
                temperature=temperature
                if temperature is not None
                else (state.temperature or T32_DEFAULT_TEMP),
                eco=state.eco if eco is None else eco,
                swirl=state.swirl,
            ),
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._send_word(power=False)
            return
        await self._send_word(power=True, hvac_mode=hvac_mode)

    async def async_turn_on(self) -> None:
        await self._send_word(power=True)

    async def async_turn_off(self) -> None:
        await self._send_word(power=False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        # no power flag: adjust without cycling the appliance
        await self._send_word(
            power=True if self._state.power_on else None,
            temperature=round(temperature),
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._send_word(
            power=True if self._state.power_on else None, fan_mode=fan_mode
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._send_word(
            power=True if self._state.power_on else None,
            eco=preset_mode == PRESET_ECO,
        )
