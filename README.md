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
| T12 on/off with AUTO mode | `light` (AUTO mode as attribute, overridable) |
| T21/T22 motorized (shutter) | `cover` (open/close/stop) |
| T41 anti-theft main | `alarm_control_panel` |
| T51-T58 analog input | `sensor` (temperature, humidity, lux, V, A, W, hPa) |
| T61-T68 analog setpoint | `number` |
| node health | diagnostic `sensor` per node |

Per-slot entity-type overrides: the integration cannot know what is wired to a T1n
slot, so the *Configure* dialog of the hub entry lets you map any T11/T12 slot to
`switch`, `light`, `binary_sensor` (motion, read-only) or `button` (single ON
command, e.g. a node reboot input). The integration reloads and replaces the
entity; registry customizations of the replaced entity are lost.

Planned: T16/T19 dimmable/RGB lights, T31 climate, action-message events, gateway
discovery.

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
