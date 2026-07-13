"""Base entity for Souliss slots."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .protocol import Node, Slot, SoulissGateway


class SoulissNodeEntity(Entity):
    """Entity attached to a Souliss node (device per node, hub = gateway)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, gateway: SoulissGateway, node: Node, entry_id: str
    ) -> None:
        self._gateway = gateway
        self._node = node
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}-node{node.index}")},
            name=f"Souliss node {node.index}",
            manufacturer="Souliss",
            model=f"vNet node {node.index}",
            via_device=(DOMAIN, entry_id),
        )

    @property
    def available(self) -> bool:
        return self._gateway.connected and self._node.alive

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._node.register_callback(self._handle_update))
        self.async_on_remove(
            self._gateway.register_availability_callback(
                lambda _connected: self._handle_update()
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class SoulissSlotEntity(SoulissNodeEntity):
    """Entity representing one typical instance (a slot) of a node."""

    def __init__(
        self, gateway: SoulissGateway, node: Node, slot: Slot, entry_id: str
    ) -> None:
        super().__init__(gateway, node, entry_id)
        self._slot = slot
        self._attr_unique_id = f"{entry_id}-{node.index}-{slot.index}"
        self._attr_name = f"Slot {slot.index}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._slot.register_callback(self._handle_update))

    async def _send_command(self, command: int) -> None:
        await self._gateway.send_command(
            self._node.index, self._slot.index, bytes((command,))
        )
