"""Souliss T5n analog inputs and node health as sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoulissConfigEntry
from .entity import (
    SoulissNodeEntity,
    SoulissSlotEntity,
    async_setup_slot_entities,
)
from .protocol import Node, Slot, SoulissGateway
from .protocol import const as pconst

SENSOR_META: dict[int, tuple[SensorDeviceClass | None, str | None]] = {
    pconst.T51: (None, None),
    pconst.T52: (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    pconst.T53: (SensorDeviceClass.HUMIDITY, PERCENTAGE),
    pconst.T54: (SensorDeviceClass.ILLUMINANCE, LIGHT_LUX),
    pconst.T55: (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT),
    pconst.T56: (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE),
    pconst.T57: (SensorDeviceClass.POWER, UnitOfPower.WATT),
    pconst.T58: (SensorDeviceClass.PRESSURE, UnitOfPressure.HPA),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoulissConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    gateway = entry.runtime_data
    async_add_entities(
        SoulissHealthSensor(gateway, node, entry.entry_id)
        for node in gateway.nodes.values()
    )

    def _factory(node: Node, slot: Slot) -> SoulissAnalogSensor | None:
        if slot.typical not in SENSOR_META:
            return None
        return SoulissAnalogSensor(gateway, node, slot, entry.entry_id)

    async_setup_slot_entities(entry, async_add_entities, _factory)


class SoulissAnalogSensor(SoulissSlotEntity, SensorEntity):
    """A T5n half-precision analog input."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self, gateway: SoulissGateway, node: Node, slot: Slot, entry_id: str
    ) -> None:
        super().__init__(gateway, node, slot, entry_id)
        device_class, unit = SENSOR_META[slot.typical]
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float | None:
        return self._slot.analog_value


class SoulissHealthSensor(SoulissNodeEntity, SensorEntity):
    """Diagnostic sensor exposing the gateway-reported node health byte."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"
    _attr_name = "Health"

    def __init__(self, gateway: SoulissGateway, node: Node, entry_id: str) -> None:
        super().__init__(gateway, node, entry_id)
        self._attr_unique_id = f"{entry_id}-{node.index}-health"

    @property
    def available(self) -> bool:
        # health stays readable even when the node itself is degraded
        return self._gateway.connected

    @property
    def native_value(self) -> int:
        return self._node.health
