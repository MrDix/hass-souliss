"""End-to-end tests of the UDP client against a fake in-process gateway."""

from __future__ import annotations

import asyncio

import pytest
from protocol import const, frames
from protocol.gateway import (
    SoulissConnectionError,
    SoulissGateway,
)

GW_VNET_ADDRESS = 0x0001  # 127.0.0.1 -> last octet 1


class FakeGateway(asyncio.DatagramProtocol):
    """Minimal Souliss gateway: 2 nodes, answers on the request's source port."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.node0_out = bytearray(24)
        self.node1_out = bytearray(24)
        self.node0_typ = bytearray(24)
        self.node0_typ[0] = const.T12
        self.node0_typ[1] = const.T22
        self.node0_typ[2] = const.T52
        self.node0_typ[3] = const.SLOT_RELATED
        self.node1_typ = bytearray(24)
        self.node1_typ[0] = const.T11
        self.forces: list[tuple[int, bytes]] = []

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport

    def _answer(
        self,
        addr: tuple[str, int],
        dest: int,
        funcode: int,
        startoffset: int = 0,
        payload: bytes = b"",
    ) -> None:
        macaco = frames.build_macaco(
            funcode, startoffset=startoffset, numberof=len(payload), payload=payload
        )
        assert self.transport
        self.transport.sendto(frames.build_vnet(dest, GW_VNET_ADDRESS, macaco), addr)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        frame = frames.parse_vnet(data)
        client = frame.source
        if frame.funcode == const.FC_PING_REQ:
            self._answer(addr, client, const.FC_PING_ANS)
        elif frame.funcode == const.FC_DBSTRUCT_REQ:
            self._answer(
                addr, client, const.FC_DBSTRUCT_ANS,
                payload=bytes((2, 45, 24, 10, 39, 63, 87)),
            )
        elif frame.funcode == const.FC_TYPICAL_REQ:
            self._answer(
                addr, client, const.FC_TYPICAL_ANS,
                startoffset=0, payload=bytes(self.node0_typ),
            )
            self._answer(
                addr, client, const.FC_TYPICAL_ANS,
                startoffset=1, payload=bytes(self.node1_typ),
            )
        elif frame.funcode in (const.FC_SUBSCRIBE_REQ, const.FC_POLL_REQ):
            self._answer(
                addr, client, const.FC_STATE_ANS,
                startoffset=0, payload=bytes(self.node0_out),
            )
            self._answer(
                addr, client, const.FC_STATE_ANS,
                startoffset=1, payload=bytes(self.node1_out),
            )
        elif frame.funcode == const.FC_HEALTH_REQ:
            self._answer(
                addr, client, const.FC_HEALTH_ANS, payload=bytes((0xFF, 0x30))
            )
        elif frame.funcode == const.FC_FORCE:
            node = frame.startoffset
            self.forces.append((node, frame.payload))
            out = self.node0_out if node == 0 else self.node1_out
            typ = self.node0_typ if node == 0 else self.node1_typ
            slot = len(frame.payload) - 1
            command = frame.payload[slot]
            if typ[slot] in (const.T11, const.T12):
                out[slot] = (
                    const.T1N_ON_COIL
                    if command == const.T1N_ON_CMD
                    else const.T1N_OFF_COIL
                )
            elif typ[slot] == const.T22:
                out[slot] = {
                    const.T2N_OPEN_CMD: const.T2N_COIL_OPEN,
                    const.T2N_CLOSE_CMD: const.T2N_COIL_CLOSE,
                    const.T2N_STOP_CMD: const.T2N_COIL_STOP,
                }[command]
            self._answer(
                addr, client, const.FC_STATE_ANS,
                startoffset=node, payload=bytes(out),
            )


@pytest.fixture
async def fake_gateway() -> tuple[FakeGateway, int]:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        FakeGateway, local_addr=("127.0.0.1", 0)
    )
    port = transport.get_extra_info("sockname")[1]
    yield protocol, port
    transport.close()


@pytest.fixture
async def client(fake_gateway: tuple[FakeGateway, int]) -> SoulissGateway:
    _, port = fake_gateway
    gateway = SoulissGateway("127.0.0.1", port=port, local_port=0)
    await gateway.connect()
    yield gateway
    gateway.close()


async def test_connect_enumerates_nodes(client: SoulissGateway) -> None:
    assert client.connected
    assert client.node_count == 2
    assert client.slots_per_node == 24
    assert {i: s.typical for i, s in client.nodes[0].slots.items()} == {
        0: const.T12,
        1: const.T22,
        2: const.T52,
    }
    assert client.nodes[1].slots[0].typical == const.T11


async def test_command_roundtrip(
    client: SoulissGateway, fake_gateway: tuple[FakeGateway, int]
) -> None:
    gateway, _ = fake_gateway
    slot = client.nodes[1].slots[0]
    updated = asyncio.Event()
    slot.register_callback(updated.set)

    await client.send_command(1, 0, bytes((const.T1N_ON_CMD,)))
    await asyncio.wait_for(updated.wait(), 3)

    assert gateway.forces == [(1, bytes((const.T1N_ON_CMD,)))]
    assert slot.value == const.T1N_ON_COIL


async def test_command_pads_leading_slots(
    client: SoulissGateway, fake_gateway: tuple[FakeGateway, int]
) -> None:
    gateway, _ = fake_gateway
    slot = client.nodes[0].slots[1]
    updated = asyncio.Event()
    slot.register_callback(updated.set)

    await client.send_command(0, 1, bytes((const.T2N_OPEN_CMD,)))
    await asyncio.wait_for(updated.wait(), 3)

    assert gateway.forces == [(0, bytes((0x00, const.T2N_OPEN_CMD)))]
    assert slot.value == const.T2N_COIL_OPEN


async def test_connect_fails_without_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protocol import gateway as gateway_module

    monkeypatch.setattr(gateway_module, "REQUEST_TIMEOUT", 0.1)
    gateway = SoulissGateway("127.0.0.1", port=1, local_port=0)
    with pytest.raises(SoulissConnectionError):
        await gateway.connect()
    assert not gateway.connected


async def test_late_typicals_fire_discovery(client: SoulissGateway) -> None:
    # simulate a node that was silent during connect(): no slots known yet
    node1_typ = bytes(client.nodes[1].slots[0].typical for _ in range(1)) + bytes(23)
    client.nodes[1].slots = {}
    discovered = []
    client.register_discovery_callback(discovered.append)

    frame = frames.build_vnet(
        client.source_address,
        GW_VNET_ADDRESS,
        frames.build_macaco(
            const.FC_TYPICAL_ANS, startoffset=1, numberof=24, payload=node1_typ
        ),
    )
    client._handle_datagram(frame, ("127.0.0.1", 9999))

    assert [node.index for node in discovered] == [1]
    assert client.nodes[1].slots[0].typical == const.T11
    await asyncio.sleep(0.1)  # let the follow-up state poll task finish

    # an unchanged repeat must not fire the callback again
    client._handle_datagram(frame, ("127.0.0.1", 9999))
    assert len(discovered) == 1


async def test_foreign_source_is_ignored(client: SoulissGateway) -> None:
    # a frame with a foreign vNet source must not reach the model
    frame = frames.build_vnet(
        client.source_address,
        0x00AB,
        frames.build_macaco(
            const.FC_STATE_ANS, startoffset=1, numberof=24, payload=b"\x01" + bytes(23)
        ),
    )
    client._handle_datagram(frame, ("127.0.0.1", 9999))
    assert client.nodes[1].slots[0].value == 0x00


async def test_action_message_dispatch(client: SoulissGateway) -> None:
    # action messages are broadcast by any node and bypass the source filter
    received: list[tuple[int, int, int, bytes]] = []
    unregister = client.register_action_callback(
        lambda source, message, action, data: received.append(
            (source, message, action, data)
        )
    )

    frame = frames.build_vnet(
        0xFFFF,
        0x00AB,  # a foreign peer node, not the gateway
        frames.build_macaco(
            const.FC_ACTION_MESSAGE,
            putin=0x1234,
            startoffset=0x05,
            numberof=2,
            payload=b"\x01\x02",
        ),
    )
    client._handle_datagram(frame, ("127.0.0.1", 9999))
    assert received == [(0x00AB, 0x1234, 0x05, b"\x01\x02")]

    unregister()
    client._handle_datagram(frame, ("127.0.0.1", 9999))
    assert len(received) == 1
