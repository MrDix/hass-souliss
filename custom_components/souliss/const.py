"""Constants for the Souliss integration."""

from homeassistant.const import Platform

DOMAIN = "souliss"

CONF_USER_INDEX = "user_index"
CONF_NODE_INDEX = "node_index"
CONF_LOCAL_PORT = "local_port"

PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]
