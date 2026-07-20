# Souliss integration for Home Assistant

A custom Home Assistant integration for the [Souliss](https://github.com/souliss/souliss)
home automation framework. It talks to a Souliss gateway node natively over UDP
(vNet/MaCaco protocol, port 230) — the same way SoulissApp and the OpenHAB binding do —
and exposes every node behind the gateway (IP, WiFi and RS485 peers) as Home Assistant
devices and entities. No firmware changes required.

## Status

Early development. Implemented:

- Config flow (gateway IP, local port, user/node index), reconfigure support
- Automatic enumeration of the node database and typicals via the gateway
- Push state updates via MaCaco subscription (refresh handled automatically)
- Node health monitoring and availability handling
- Diagnostics download

| Souliss typical | Home Assistant entity |
|---|---|
| T11 on/off output | `switch` (overridable) |
| T12 on/off with AUTO mode | `light` (AUTO mode as attribute, overridable) plus a disabled-by-default `select` (off/on/auto) |
| T13 digital input | `binary_sensor` (overridable) |
| T14 pulse output | `button` (overridable) |
| T16 RGB LED strip | `light` (RGB color, brightness = max channel) |
| T18 on/off with pulse feedback | `switch` (overridable) |
| T19 single-channel dimmable LED | `light` (brightness) |
| T1A 8-bit digital input | 8 `binary_sensor` entities (one per input) |
| T21/T22 motorized (shutter) | `cover` (open/close/stop) |
| T31 temperature control | `climate` (heat/cool/off, setpoint, fan modes) |
| T32 air conditioner | `climate` (auto/cool/dry/fan/heat, 16-30 °C, fan modes, eco preset) |
| T41 anti-theft main | `alarm_control_panel` |
| T42 anti-theft peer | `binary_sensor` (safety, latched until chain rearm) |
| T51-T58 analog input | `sensor` (temperature, humidity, lux, V, A, W, hPa) |
| T61-T68 analog setpoint | `number` |
| node health | diagnostic `sensor` per node |

Note on T32: the typical is a pass-through remote — the node forwards the
command word to the appliance (usually via IR) and only echoes the last
command back, so the entity state reflects the last command, not appliance
feedback.

Per-slot entity-type overrides: the integration cannot know what is wired to a
single-slot T1n typical, so the *Configure* dialog of the hub entry lets you map
any T11/T12/T13/T14/T18 slot to `switch`, `light`, `binary_sensor` (read-only)
or `button` (single ON command, e.g. a node reboot input). The integration
reloads and replaces the entity; registry customizations of the replaced entity
are lost. T16/T19 are always lights and T31 is always a climate entity.

Planned: action-message events, gateway discovery.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → *Custom repositories* → add this repository as type
   *Integration*.
2. Install **Souliss** and restart Home Assistant.

### Manual

Copy `custom_components/souliss/` into your Home Assistant `config/custom_components/`
directory and restart.

## Configuration

Settings → Devices & Services → *Add Integration* → **Souliss**, then enter the IP
address of the gateway node. The defaults for the local UDP port (23000) and the
user/node index (70/120) are fine unless another Souliss client (SoulissApp, OpenHAB)
runs on the same machine — every client on the LAN needs a unique user/node index pair,
and the gateway keeps at most 5 subscribed clients.

Entities are created from the gateway's typical database and named
`Souliss node <n> Slot <s>`; rename them in Home Assistant as you like.

## Development

```
pip install pytest pytest-asyncio ruff
python -m pytest
ruff check .
```

The protocol client in `custom_components/souliss/protocol/` is a standalone asyncio
package without Home Assistant imports (candidate for a future PyPI release). The wire
protocol is documented in [`docs/protocol.md`](docs/protocol.md).

## License

MIT
