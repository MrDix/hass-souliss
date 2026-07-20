"""Config flow for the Souliss integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.components.network import async_get_enabled_source_ips
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ENTITY_TYPE,
    CONF_LOCAL_PORT,
    CONF_NODE_INDEX,
    CONF_OVERRIDES,
    CONF_SLOT,
    CONF_SLOT_OVERRIDES,
    CONF_USER_INDEX,
    DOMAIN,
)
from .helpers import DEFAULT_DOMAIN, OVERRIDABLE_DOMAINS, override_key
from .protocol import SoulissError, SoulissGateway, discover_gateways
from .protocol.const import DEFAULT_LOCAL_PORT, DEFAULT_NODE_INDEX, DEFAULT_USER_INDEX
from .protocol.gateway import SoulissBindError


def _int_box(minimum: int, maximum: int) -> vol.All:
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX)
        ),
        vol.Coerce(int),
    )


def _user_schema(discovered: list[str]) -> vol.Schema:
    """The gateway form; discovered IPs become a dropdown with free entry."""
    if discovered:
        host_field = SelectSelector(
            SelectSelectorConfig(
                options=discovered,
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    else:
        host_field = str
    return vol.Schema(
        {
            vol.Required(CONF_HOST): host_field,
            vol.Required(CONF_LOCAL_PORT, default=DEFAULT_LOCAL_PORT): _int_box(1024, 65535),
            vol.Required(CONF_USER_INDEX, default=DEFAULT_USER_INDEX): _int_box(1, 100),
            vol.Required(CONF_NODE_INDEX, default=DEFAULT_NODE_INDEX): _int_box(1, 254),
        }
    )


STEP_USER_SCHEMA = _user_schema([])


async def _validate(data: dict[str, Any]) -> str | None:
    """Try to connect; return an error key or None."""
    gateway = SoulissGateway(
        data[CONF_HOST],
        local_port=data[CONF_LOCAL_PORT],
        user_index=data[CONF_USER_INDEX],
        node_index=data[CONF_NODE_INDEX],
    )
    try:
        await gateway.connect()
    except SoulissBindError:
        return "port_in_use"
    except SoulissError:
        return "cannot_connect"
    finally:
        gateway.close()
        # let the event loop actually release the UDP socket before
        # async_setup_entry binds the same port again
        await asyncio.sleep(0.2)
    return None


class SoulissConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for a Souliss gateway."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SoulissOptionsFlow:
        return SoulissOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            error = await _validate(user_input)
            if error is None:
                return self.async_create_entry(
                    title=f"Souliss gateway ({user_input[CONF_HOST]})",
                    data=user_input,
                )
            errors["base"] = error
        else:
            # broadcast probe so known gateways can be picked from a list;
            # probe from every adapter address (multi-homed hosts)
            source_ips = [
                str(address)
                for address in await async_get_enabled_source_ips(self.hass)
                if address.version == 4 and not address.is_loopback
            ]
            self._discovered = await discover_gateways(
                source_ips=source_ips or ("0.0.0.0",)
            )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema(self._discovered), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _validate(user_input)
            if error is None:
                return self.async_update_reload_and_abort(entry, data=user_input)
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or dict(entry.data)
            ),
            errors=errors,
        )


class SoulissOptionsFlow(OptionsFlow):
    """Manage per-slot entity-type overrides."""

    @property
    def _overrides(self) -> dict[str, str]:
        return dict(self.config_entry.options.get(CONF_SLOT_OVERRIDES, {}))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._overrides:
            return self.async_show_menu(
                step_id="init", menu_options=["add_override", "remove_override"]
            )
        return await self.async_step_add_override()

    async def async_step_add_override(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        gateway: SoulissGateway | None = getattr(
            self.config_entry, "runtime_data", None
        )
        if gateway is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            overrides = self._overrides
            overrides[user_input[CONF_SLOT]] = user_input[CONF_ENTITY_TYPE]
            return self.async_create_entry(data={CONF_SLOT_OVERRIDES: overrides})

        overrides = self._overrides
        slot_options = [
            SelectOptionDict(
                value=key,
                label=(
                    f"Node {node.index} slot {slot.index}"
                    f" (T{slot.typical:02X}, {overrides.get(key, default)})"
                ),
            )
            for node in gateway.nodes.values()
            for slot in node.slots.values()
            if (default := DEFAULT_DOMAIN.get(slot.typical)) is not None
            and (key := override_key(node.index, slot.index))
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_SLOT): SelectSelector(
                    SelectSelectorConfig(
                        options=slot_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(CONF_ENTITY_TYPE): SelectSelector(
                    SelectSelectorConfig(
                        options=list(OVERRIDABLE_DOMAINS),
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="override_type",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="add_override", data_schema=schema)

    async def async_step_remove_override(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        overrides = self._overrides
        if user_input is not None:
            for key in user_input[CONF_OVERRIDES]:
                overrides.pop(key, None)
            return self.async_create_entry(data={CONF_SLOT_OVERRIDES: overrides})

        schema = vol.Schema(
            {
                vol.Required(CONF_OVERRIDES): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=key, label=f"Node {key.replace('-', ' slot ')}: {domain}"
                            )
                            for key, domain in overrides.items()
                        ],
                        mode=SelectSelectorMode.LIST,
                        multiple=True,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_override", data_schema=schema)
