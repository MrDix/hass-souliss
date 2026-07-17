"""The Souliss integration."""

from __future__ import annotations

import asyncio
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_LOCAL_PORT, CONF_NODE_INDEX, CONF_USER_INDEX, DOMAIN, PLATFORMS
from .helpers import MODE_SELECT_DOMAINS, OVERRIDABLE_DOMAINS, slot_domain
from .protocol import SoulissError, SoulissGateway
from .protocol.const import DEFAULT_LOCAL_PORT, DEFAULT_NODE_INDEX, DEFAULT_USER_INDEX

type SoulissConfigEntry = ConfigEntry[SoulissGateway]


async def async_setup_entry(hass: HomeAssistant, entry: SoulissConfigEntry) -> bool:
    """Connect to the Souliss gateway and set up all platforms."""
    gateway = SoulissGateway(
        entry.data[CONF_HOST],
        local_port=entry.data.get(CONF_LOCAL_PORT, DEFAULT_LOCAL_PORT),
        user_index=entry.data.get(CONF_USER_INDEX, DEFAULT_USER_INDEX),
        node_index=entry.data.get(CONF_NODE_INDEX, DEFAULT_NODE_INDEX),
    )
    try:
        await gateway.connect()
    except SoulissError as err:
        raise ConfigEntryNotReady(
            f"Cannot reach Souliss gateway at {entry.data[CONF_HOST]}: {err}"
        ) from err

    entry.runtime_data = gateway
    entry.async_on_unload(gateway.close)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Souliss gateway ({entry.data[CONF_HOST]})",
        manufacturer="Souliss",
        model="Gateway",
    )

    _async_remove_stale_entities(hass, entry, gateway)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SoulissConfigEntry) -> bool:
    """Unload the config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data.close()
        # let the event loop actually release the UDP socket so an immediate
        # reload (e.g. after an options change) can bind the same port again
        await asyncio.sleep(0.2)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: SoulissConfigEntry) -> None:
    """Reload the entry when the slot overrides change."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_remove_stale_entities(
    hass: HomeAssistant, entry: SoulissConfigEntry, gateway: SoulissGateway
) -> None:
    """Drop registry entries whose platform no longer matches the overrides."""
    registry = er.async_get(hass)
    slot_id = re.compile(rf"{re.escape(entry.entry_id)}-(\d+)-(\d+)")
    mode_id = re.compile(rf"{re.escape(entry.entry_id)}-(\d+)-(\d+)-mode")
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain in OVERRIDABLE_DOMAINS:
            match = slot_id.fullmatch(reg_entry.unique_id)
            if match is None:
                continue
            node = gateway.nodes.get(int(match[1]))
            slot = node.slots.get(int(match[2])) if node else None
            if slot is not None and slot_domain(entry, node.index, slot) != reg_entry.domain:
                registry.async_remove(reg_entry.entity_id)
        elif reg_entry.domain == "select":
            match = mode_id.fullmatch(reg_entry.unique_id)
            if match is None:
                continue
            node = gateway.nodes.get(int(match[1]))
            slot = node.slots.get(int(match[2])) if node else None
            if slot is not None and slot_domain(entry, node.index, slot) not in MODE_SELECT_DOMAINS:
                registry.async_remove(reg_entry.entity_id)
