# Souliss vNet/MaCaco UDP Protocol Reference

Compiled from the Souliss firmware sources (`souliss/souliss`, branch `friariello`) and the
OpenHAB binding (`org.openhab.binding.souliss`) as reference client implementation.

## Transport

| Item | Value |
|---|---|
| Gateway UDP port | **230** (`ETH_PORT`, effectively hard-coded) |
| Client local port | **23000** by convention (`USR_PORT`) — any fixed port works |
| Max vNet frame | 62 bytes (`VNET_MAX_FRAME`), payload ≤ 46 |

The gateway records the *source IP:port* of each request from a User-Mode address and sends
all answers and subscription pushes back to exactly that endpoint ("User Mode",
`frame/vNet/tools/UserMode.c`). Keep one socket bound to a stable local port for the whole
session. The gateway keeps only **5** user entries (oldest overwritten) — every UI on the
LAN must use a distinct user/node index pair (SoulissApp, OpenHAB, this integration ...).

## vNet frame (UDP payload)

All multi-byte fields little-endian.

```
offset size field
0      1    total UDP payload length        (= vNet_len + 1)
1      1    vNet frame length               (= 6 + MaCaco length, counts itself)
2      1    vNet port = 0x17 (23, MaCaco)
3      2    destination vNet address (LE)   gateway = last IP octet, high byte 0
5      2    source vNet address (LE)        client = (user_index << 8) | node_index
7      ...  MaCaco frame
```

- Client source address: `user_index` must be 1–100 (0x01–0x64); defaults used by OpenHAB:
  user 70, node 120 → source `0x4678` → wire bytes `78 46`.
- Broadcast destination: `0xFFFF` (sent to 255.255.255.255:230).

## MaCaco frame

```
offset size field
0      1    functional code
1      2    putin (LE)      client tag, UIs send 0x0000
3      1    startoffset     node index (state/force answers) / first byte offset
4      1    numberof        payload length / number of nodes requested
5      n    payload         only in answer funcodes (high nibble 1/3/5/7)
```

### Functional codes

| Request | Answer | Purpose |
|---|---|---|
| 0x08 | 0x18 | Ping |
| 0x28 | 0x38 | Gateway discovery (broadcast); answer payload = gateway IPv4 |
| 0x26 | 0x36 | Database structure |
| 0x22 | 0x32 | Typicals (logic types) per node |
| 0x21 | 0x31 | State read **with subscription** (push follows) |
| 0x27 | 0x37 | State poll (no subscription) |
| 0x25 | 0x35 | Node health |
| 0x33 | —    | Force input (commands), startoffset = node |
| 0x34 | —    | Force by typical id (all matching logics) |
| 0x72 | —    | Action message / topic publish |
| —    | 0x83/0x84/0x85 | Errors: not supported / out of range / subscription refused |

0x31 and 0x37 carry identical payloads and must both be treated as state publications.

### Requests (MaCaco bytes)

```
ping:        08 00 00 00 00
discover:    28 05 00 00 00                (broadcast)
db struct:   26 00 00 00 07                (numberof>=7 -> long form answer)
typicals:    22 00 00 00 <numnodes>
subscribe:   21 00 00 00 <numnodes>
poll:        27 00 00 00 00
health:      25 00 00 00 <numnodes>
force:       33 00 00 <node> <slot+len> [00 x slot] <cmd bytes...>
```

FORCE payload always starts at slot 0 of the node's IN area; untouched slots are padded
with `0x00` (= `RstCmd`, "no command" for every typical). A slot can therefore never be
forced to raw 0x00 — commands are command codes, not raw states.

### Answers

- **0x36 db struct** payload: `[configured_nodes, MaCaco_NODES, MaCaco_SLOT(=24),
  MaCaco_INMAXSUBSCR, MaCaco_IN_s, MaCaco_TYP_s, MaCaco_OUT_s]`. Client needs bytes 0 and 2.
- **0x32 typicals**: `startoffset` = first node index, payload = flat typical-id array,
  `MaCaco_SLOT` bytes per node. `0x00` = empty slot, `0xFF` = continuation slot of a
  multi-slot typical. `slot = i % slots_per_node`, `node = i / slots_per_node + startoffset`.
- **0x31/0x37 state**: `startoffset` = node index, payload = that node's OUT array
  (`numberof` bytes, usually 24).
- **0x35 health**: one byte per node from `startoffset`; 0xFF best, fresh subscription
  starts at 0x25, values < 0x25 mean degraded/dead.

## Subscription behaviour

- Subscribe with 0x21; gateway answers node 0 immediately, refreshes peers, then pushes
  0x31 frames event-based per node.
- Subscriptions live in RAM (lost on gateway reboot), ring of 10 channels, dropped after
  3 failed sends. **Refresh periodically** (OpenHAB: every 30 s; must be 2–240 s).
- Ping every ~30 s; >3 missed answers → consider the gateway offline.

## Typicals (relevant subset)

Half-float codec: IEEE 754 binary16 little-endian == Python `struct.pack("<e", v)`.
`0x8000` (−0.0) encodes 0.0, `0xFE00` (NaN) means "no value yet".

### T11 (0x11) — on/off digital output, 1 slot
Commands: Toggle 0x01, On 0x02, Off 0x04, Timed 0x30+cycles. States: 0x01 on, 0x00 off
(timed variants 0xE1/0xE0, feedback 0x23 on / 0x24 off).

### T12 (0x12) — on/off with AUTO mode, 1 slot
Commands: as T11 plus Auto 0x08. States: 0x00 off, 0x01 on, 0xF0 auto-off, 0xF1 auto-on.

### T22 (0x22) — motorized with middle position (shutter), 1 slot
Commands (SW): Close 0x01, Open 0x02, Stop 0x04, Toggle 0x08.
States: 0x01 closing (coil), 0x02 opening (coil), 0x03 stopped, 0x08 closed (limit/timer),
0x10 open (limit/timer), 0x20 stopped without limit switch.

### T41 (0x41) — anti-theft main, 1 slot
Commands: Alarm(trigger) 0x01, AlarmDelay 0x02, ReArm 0x03, NotArmed(disarm) 0x04,
Armed(arm) 0x05. States: 0x00 disarmed, 0x01 armed, 0x03 in alarm, 0x04 re-arming.

### T5n (0x51–0x58) — analog input, 2 slots (slot+1 = 0xFF)
OUT[slot..slot+1] = half-float LE. Read-only.
T51 generic, T52 temperature, T53 humidity, T54 lux, T55 voltage, T56 current,
T57 power, T58 pressure.

### T6n (0x61–0x68) — analog setpoint, 2 slots
Same encoding, writable: FORCE with the two half-float bytes at the slot; the node copies
IN → OUT, the push confirms the setpoint.

## Client session recipe

1. Bind UDP socket to a fixed local port, pick a unique (user, node) index pair.
2. Optional discovery: broadcast 0x28, parse 0x38. Otherwise ping 0x08 the known host.
3. 0x26 → node count and slots per node.
4. 0x22 → typical map (collect 0x32 answers until all nodes known).
5. 0x21 → initial states + event pushes; refresh subscription every ≤ 240 s.
6. Commands via 0x33; confirmation arrives as 0x31 push.
7. Rate-limit sends (~30 ms between frames) — the nodes are 8-bit AVRs.
