"""The Souliss integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONF_LOCAL_PORT, CONF_NODE_INDEX, CONF_USER_INDEX, DOMAIN, PLATFORMS
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SoulissConfigEntry) -> bool:
    """Unload the config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
