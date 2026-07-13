"""Constants for the Souliss integration."""

from homeassistant.const import Platform

DOMAIN = "souliss"

CONF_USER_INDEX = "user_index"
CONF_NODE_INDEX = "node_index"
CONF_LOCAL_PORT = "local_port"

CONF_SLOT_OVERRIDES = "slot_overrides"
CONF_SLOT = "slot"
CONF_ENTITY_TYPE = "entity_type"
CONF_OVERRIDES = "overrides"

PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]
