"""Per-slot entity-type overrides for T1n typicals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONF_SLOT_OVERRIDES
from .protocol import Slot
from .protocol import const as pconst

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

# T1n value bytes that mean "output is on", covering both the plain T11
# coil/feedback pairs and the T12 AUTO coils
T1N_ON_VALUES = (
    pconst.T1N_ON_COIL,
    pconst.T1N_ON_FEEDBACK,
    pconst.T1N_AUTO_ON_COIL,
)

DEFAULT_DOMAIN = {
    pconst.T11: "switch",
    pconst.T12: "light",
}

OVERRIDABLE_DOMAINS = ("switch", "light", "binary_sensor", "button")


def override_key(node_index: int, slot_index: int) -> str:
    return f"{node_index}-{slot_index}"


def slot_domain(entry: ConfigEntry, node_index: int, slot: Slot) -> str | None:
    """Effective HA domain for a T1n slot, or None for other typicals."""
    default = DEFAULT_DOMAIN.get(slot.typical)
    if default is None:
        return None
    override = entry.options.get(CONF_SLOT_OVERRIDES, {}).get(
        override_key(node_index, slot.index)
    )
    if override in OVERRIDABLE_DOMAINS:
        return override
    return default
