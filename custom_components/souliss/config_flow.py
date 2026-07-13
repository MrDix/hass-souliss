"""Config flow for the Souliss integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST

from .const import CONF_LOCAL_PORT, CONF_NODE_INDEX, CONF_USER_INDEX, DOMAIN
from .protocol import SoulissError, SoulissGateway
from .protocol.const import DEFAULT_LOCAL_PORT, DEFAULT_NODE_INDEX, DEFAULT_USER_INDEX

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_LOCAL_PORT, default=DEFAULT_LOCAL_PORT): vol.All(
            int, vol.Range(min=1024, max=65535)
        ),
        vol.Required(CONF_USER_INDEX, default=DEFAULT_USER_INDEX): vol.All(
            int, vol.Range(min=1, max=100)
        ),
        vol.Required(CONF_NODE_INDEX, default=DEFAULT_NODE_INDEX): vol.All(
            int, vol.Range(min=1, max=254)
        ),
    }
)


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
    except SoulissError:
        return "cannot_connect"
    except OSError:
        return "port_in_use"
    finally:
        gateway.close()
    return None


class SoulissConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for a Souliss gateway."""

    VERSION = 1

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
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
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
