"""Protocol constants for Souliss vNet/MaCaco over UDP.

Values taken from the Souliss firmware sources (conf/frame/MaCacoCfg.h,
conf/frame/vNetCfg.h, Typicals.h) and the OpenHAB binding reference client.
"""

from __future__ import annotations

# Transport
GATEWAY_PORT = 230
DEFAULT_LOCAL_PORT = 23000
DEFAULT_USER_INDEX = 70
DEFAULT_NODE_INDEX = 120
VNET_MAX_FRAME = 62
MACACO_PORT = 0x17
VNET_ADDR_BROADCAST = 0xFFFF

# Default memory map geometry (overridden by the DB-struct answer)
DEFAULT_SLOTS_PER_NODE = 24

# MaCaco functional codes: requests
FC_PING_REQ = 0x08
FC_DISCOVER_REQ = 0x28
FC_SUBSCRIBE_REQ = 0x21
FC_TYPICAL_REQ = 0x22
FC_HEALTH_REQ = 0x25
FC_DBSTRUCT_REQ = 0x26
FC_POLL_REQ = 0x27
FC_FORCE = 0x33
FC_FORCE_BY_TYPICAL = 0x34

# MaCaco functional codes: answers
FC_PING_ANS = 0x18
FC_DISCOVER_ANS = 0x38
FC_STATE_ANS = 0x31  # subscription publication
FC_TYPICAL_ANS = 0x32
FC_HEALTH_ANS = 0x35
FC_DBSTRUCT_ANS = 0x36
FC_POLL_ANS = 0x37  # identical payload to FC_STATE_ANS
FC_ACTION_MESSAGE = 0x72

# MaCaco error codes
FC_ERR_NOT_SUPPORTED = 0x83
FC_ERR_OUT_OF_RANGE = 0x84
FC_ERR_SUBSCRIPTION_REFUSED = 0x85

STATE_ANSWERS = (FC_STATE_ANS, FC_POLL_ANS)
ERROR_CODES = (FC_ERR_NOT_SUPPORTED, FC_ERR_OUT_OF_RANGE, FC_ERR_SUBSCRIPTION_REFUSED)

# Typical ids (TYP slot markers)
SLOT_EMPTY = 0x00
SLOT_RELATED = 0xFF  # continuation slot of a multi-slot typical

T11 = 0x11
T12 = 0x12
T13 = 0x13
T14 = 0x14
T16 = 0x16
T18 = 0x18
T19 = 0x19
T1A = 0x1A
T21 = 0x21
T22 = 0x22
T31 = 0x31
T32 = 0x32
T41 = 0x41
T42 = 0x42
T51 = 0x51
T52 = 0x52
T53 = 0x53
T54 = 0x54
T55 = 0x55
T56 = 0x56
T57 = 0x57
T58 = 0x58
T61 = 0x61
T62 = 0x62
T63 = 0x63
T64 = 0x64
T65 = 0x65
T66 = 0x66
T67 = 0x67
T68 = 0x68

ANALOG_INPUT_TYPICALS = (T51, T52, T53, T54, T55, T56, T57, T58)
ANALOG_SETPOINT_TYPICALS = (T61, T62, T63, T64, T65, T66, T67, T68)

# Extra slots occupied by multi-slot typicals (beyond the first slot)
TYPICAL_EXTRA_SLOTS = {
    T16: 3,  # cmd + R + G + B
    T19: 1,  # cmd + dimmer
    T31: 4,  # cmd + measured half-float + setpoint half-float
    T32: 4,
    **{t: 1 for t in ANALOG_INPUT_TYPICALS},
    **{t: 1 for t in ANALOG_SETPOINT_TYPICALS},
}

# T1n commands
T1N_RST_CMD = 0x00
T1N_TOGGLE_CMD = 0x01
T1N_ON_CMD = 0x02
T1N_OFF_CMD = 0x04
T1N_AUTO_CMD = 0x08  # T12 only
T1N_BRIGHT_UP_CMD = 0x10  # T16/T19 only
T1N_BRIGHT_DOWN_CMD = 0x20  # T16/T19 only
T1N_SET_CMD = 0x22  # T16: + R,G,B bytes / T19: + brightness byte
# T1n states
T1N_OFF_COIL = 0x00
T1N_ON_COIL = 0x01
T1N_ON_FEEDBACK = 0x23
T1N_OFF_FEEDBACK = 0x24
T1N_TIMED_ON_COIL = 0xE1
T1N_AUTO_OFF_COIL = 0xF0
T1N_AUTO_ON_COIL = 0xF1  # doubles as the T19 "good night" fade state

# T3n commands (values sent to the IN slot of a T31)
T3N_IN_SETPOINT_CMD = 0x01  # setpoint +1 degree
T3N_OUT_SETPOINT_CMD = 0x02  # setpoint -1 degree
T3N_AS_MEASURED_CMD = 0x03
T3N_COOLING_CMD = 0x04
T3N_HEATING_CMD = 0x05
T3N_FAN_OFF_CMD = 0x06
T3N_FAN_LOW_CMD = 0x07
T3N_FAN_MED_CMD = 0x08
T3N_FAN_HIGH_CMD = 0x09
T3N_FAN_AUTO_CMD = 0x0A
T3N_FAN_MANUAL_CMD = 0x0B
T3N_SET_TEMP_CMD = 0x0C  # setpoint half-float goes into IN slot+3/+4
T3N_SHUTDOWN_CMD = 0x0D
# T3n state bits (first OUT slot of a T31)
T3N_SYSTEM_ON = 0x01
T3N_HEATING_ON = 0x02
T3N_COOLING_ON = 0x04
T3N_FAN1_ON = 0x08
T3N_FAN2_ON = 0x10
T3N_FAN3_ON = 0x20
T3N_FAN_AUTO_STATE = 0x40
T3N_COOLING_MODE = 0x80  # set = cooling mode, clear = heating mode

# T2n commands (software commands, as used by UIs)
T2N_CLOSE_CMD = 0x01
T2N_OPEN_CMD = 0x02
T2N_STOP_CMD = 0x04
T2N_TOGGLE_CMD = 0x08
# T2n states
T2N_COIL_CLOSE = 0x01  # closing
T2N_COIL_OPEN = 0x02  # opening
T2N_COIL_STOP = 0x03  # stopped
T2N_STATE_CLOSE = 0x08  # closed (limit switch / timer)
T2N_STATE_OPEN = 0x10  # open (limit switch / timer)
T2N_NO_LIMSWITCH = 0x20  # stopped, position unknown

# T4n commands
T4N_ALARM_CMD = 0x01  # trigger the alarm
T4N_REARM_CMD = 0x03
T4N_DISARM_CMD = 0x04
T4N_ARM_CMD = 0x05
# T4n states
T4N_STATE_DISARMED = 0x00
T4N_STATE_ARMED = 0x01
T4N_STATE_IN_ALARM = 0x03
T4N_STATE_REARMING = 0x04

# Node health thresholds (0x35 answer)
HEALTH_FRESH = 0x25  # value assigned right after subscription
HEALTH_BEST = 0xFF
