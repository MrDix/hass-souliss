"""Asyncio UDP client for a Souliss gateway."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable

from . import frames
from .const import (
    DEFAULT_LOCAL_PORT,
    DEFAULT_NODE_INDEX,
    DEFAULT_SLOTS_PER_NODE,
    DEFAULT_USER_INDEX,
    ERROR_CODES,
    FC_ACTION_MESSAGE,
    FC_DBSTRUCT_ANS,
    FC_DISCOVER_ANS,
    FC_HEALTH_ANS,
    FC_PING_ANS,
    FC_TYPICAL_ANS,
    GATEWAY_PORT,
    STATE_ANSWERS,
    VNET_ADDR_BROADCAST,
)
from .frames import FrameError, MacacoFrame
from .models import Node

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 3.0
REQUEST_RETRIES = 3
SEND_SPACING = 0.03  # the nodes are 8-bit AVRs; do not burst
SUBSCRIPTION_REFRESH = 60.0  # must stay below the 240 s gateway limit
PING_INTERVAL = 30.0
MAX_PING_MISSES = 3
DISCOVERY_TIMEOUT = 2.0
# dedicated user-mode source for discovery probes: the gateway answers a
# user-mode address at the ip:port it last saw it from, so probing with a
# live client's address (e.g. the 70/120 defaults) would steal its slot
# and send the answer to that client instead of us
DISCOVERY_SOURCE_ADDRESS = (100 << 8) | 254

AvailabilityCallback = Callable[[bool], None]
DiscoveryCallback = Callable[[Node], None]
# source vNet address, message id, action id, optional data
ActionMessageCallback = Callable[[int, int, int, bytes], None]


async def discover_gateways(
    timeout: float = DISCOVERY_TIMEOUT,
    source_ips: Iterable[str] = ("0.0.0.0",),
) -> list[str]:
    """Broadcast a gateway-discovery probe and return the IPs that answered.

    Only FC_DISCOVER_ANS is accepted, so peer nodes (which answer pings but
    are no gateways) do not show up in the result.

    The limited broadcast 255.255.255.255 only leaves through the interface
    of the socket's source address, and W5x00 gateways drop directed subnet
    broadcasts in hardware — so one socket is bound per source IP and every
    socket sends the limited broadcast. Multi-homed callers should pass the
    IPv4 address of each interface.
    """
    loop = asyncio.get_running_loop()
    found: list[str] = []

    class _DiscoveryProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            try:
                frame = frames.parse_vnet(data)
            except FrameError:
                return
            if frame.funcode == FC_DISCOVER_ANS and addr[0] not in found:
                found.append(addr[0])

    transports: list[asyncio.DatagramTransport] = []
    for source_ip in dict.fromkeys(source_ips):
        try:
            transport, _ = await loop.create_datagram_endpoint(
                _DiscoveryProtocol,
                local_addr=(source_ip, 0),
                allow_broadcast=True,
            )
        except OSError as err:
            _LOGGER.debug("Cannot bind discovery socket to %s: %s", source_ip, err)
            continue
        transports.append(transport)
    if not transports:
        return found

    try:
        probe = frames.build_vnet(
            VNET_ADDR_BROADCAST, DISCOVERY_SOURCE_ADDRESS, frames.discover()
        )
        for _ in range(2):
            for transport in transports:
                try:
                    transport.sendto(probe, ("255.255.255.255", GATEWAY_PORT))
                except OSError as err:
                    _LOGGER.debug("Discovery probe failed: %s", err)
            await asyncio.sleep(timeout / 2)
    finally:
        for transport in transports:
            transport.close()
    return found


class SoulissError(Exception):
    """Base error for gateway communication."""


class SoulissConnectionError(SoulissError):
    """Gateway did not answer."""


class SoulissBindError(SoulissError):
    """The local UDP port could not be bound."""


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, gateway: SoulissGateway) -> None:
        self._gateway = gateway

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._gateway._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("UDP error received: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        self._gateway._handle_connection_lost(exc)


class SoulissGateway:
    """Client session against one Souliss gateway."""

    def __init__(
        self,
        host: str,
        *,
        port: int = GATEWAY_PORT,
        local_port: int = DEFAULT_LOCAL_PORT,
        user_index: int = DEFAULT_USER_INDEX,
        node_index: int = DEFAULT_NODE_INDEX,
    ) -> None:
        self.host = host
        self.port = port
        self.local_port = local_port
        self.source_address = ((user_index & 0xFF) << 8) | (node_index & 0xFF)
        self.dest_address = int(host.rsplit(".", 1)[-1])  # vNet addr = last IP octet
        self.nodes: dict[int, Node] = {}
        self.slots_per_node = DEFAULT_SLOTS_PER_NODE
        self.node_count = 0
        self.connected = False

        self._transport: asyncio.DatagramTransport | None = None
        self._maintenance_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0
        self._ping_misses = 0
        self._waiters: dict[int, list[asyncio.Future[MacacoFrame]]] = {}
        self._availability_callbacks: list[AvailabilityCallback] = []
        self._discovery_callbacks: list[DiscoveryCallback] = []
        self._action_callbacks: list[ActionMessageCallback] = []

    # ---------------------------------------------------------------- setup

    async def connect(self) -> None:
        """Bind the socket, enumerate the network and subscribe to updates."""
        loop = asyncio.get_running_loop()
        try:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _Protocol(self),
                local_addr=("0.0.0.0", self.local_port),
            )
        except OSError as err:
            raise SoulissBindError(
                f"cannot bind local UDP port {self.local_port}: {err}"
            ) from err
        try:
            await self._enumerate()
            await self._request(frames.subscribe(self.node_count), STATE_ANSWERS[0])
        except SoulissError:
            self.close()
            raise
        self._set_connected(True)
        self._maintenance_task = asyncio.get_running_loop().create_task(
            self._maintenance_loop()
        )

    async def _enumerate(self) -> None:
        answer = await self._request(frames.db_struct(), FC_DBSTRUCT_ANS)
        if not answer.payload:
            raise SoulissConnectionError("empty database structure answer")
        self.node_count = answer.payload[0]
        if len(answer.payload) >= 3 and answer.payload[2]:
            self.slots_per_node = answer.payload[2]
        _LOGGER.debug(
            "Gateway reports %d nodes, %d slots per node",
            self.node_count,
            self.slots_per_node,
        )
        for index in range(self.node_count):
            self.nodes.setdefault(index, Node(index))

        await self._request(frames.typical_request(self.node_count), FC_TYPICAL_ANS)
        missing = await self._wait_for_typicals()
        for index in missing:
            try:
                await self._request(
                    frames.typical_request(1, startoffset=index),
                    FC_TYPICAL_ANS,
                    retries=1,
                )
            except SoulissConnectionError:
                _LOGGER.warning(
                    "Node %d did not report its typicals (offline?)", index
                )

    async def _wait_for_typicals(self) -> list[int]:
        """Give the gateway time to relay peer typicals; return nodes still empty."""
        for _ in range(20):
            missing = [i for i, node in self.nodes.items() if not node.slots]
            if not missing:
                return []
            await asyncio.sleep(0.5)
        return [i for i, node in self.nodes.items() if not node.slots]

    def close(self) -> None:
        if self._maintenance_task:
            self._maintenance_task.cancel()
            self._maintenance_task = None
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        if self._transport:
            self._transport.close()
            self._transport = None
        self._set_connected(False)

    # ------------------------------------------------------------- commands

    async def send_command(self, node: int, slot: int, command: bytes) -> None:
        """Force command bytes into a node's IN area (confirmation via push)."""
        await self._send(frames.force(node, slot, command))

    async def send_setpoint(self, node: int, slot: int, value: float) -> None:
        await self.send_command(node, slot, frames.encode_half_float(value))

    async def poll(self) -> None:
        """Request a state refresh outside the subscription push."""
        await self._send(frames.poll())

    # ------------------------------------------------------------ callbacks

    def register_availability_callback(
        self, callback: AvailabilityCallback
    ) -> Callable[[], None]:
        self._availability_callbacks.append(callback)

        def _unregister() -> None:
            if callback in self._availability_callbacks:
                self._availability_callbacks.remove(callback)

        return _unregister

    def register_discovery_callback(
        self, callback: DiscoveryCallback
    ) -> Callable[[], None]:
        """Subscribe to nodes whose typicals arrive after connect()."""
        self._discovery_callbacks.append(callback)

        def _unregister() -> None:
            if callback in self._discovery_callbacks:
                self._discovery_callbacks.remove(callback)

        return _unregister

    def register_action_callback(
        self, callback: ActionMessageCallback
    ) -> Callable[[], None]:
        """Subscribe to broadcast action messages published by any node."""
        self._action_callbacks.append(callback)

        def _unregister() -> None:
            if callback in self._action_callbacks:
                self._action_callbacks.remove(callback)

        return _unregister

    def _set_connected(self, connected: bool) -> None:
        if connected == self.connected:
            return
        self.connected = connected
        for callback in list(self._availability_callbacks):
            callback(connected)

    # ----------------------------------------------------------------- I/O

    async def _send(self, macaco: bytes) -> None:
        if self._transport is None:
            raise SoulissConnectionError("not connected")
        frame = frames.build_vnet(self.dest_address, self.source_address, macaco)
        async with self._send_lock:
            spacing = SEND_SPACING - (time.monotonic() - self._last_send)
            if spacing > 0:
                await asyncio.sleep(spacing)
            self._transport.sendto(frame, (self.host, self.port))
            self._last_send = time.monotonic()

    async def _request(
        self, macaco: bytes, answer_funcode: int, retries: int = REQUEST_RETRIES
    ) -> MacacoFrame:
        """Send a request and wait for the matching answer, with retries."""
        for attempt in range(1, retries + 1):
            future: asyncio.Future[MacacoFrame] = (
                asyncio.get_running_loop().create_future()
            )
            self._waiters.setdefault(answer_funcode, []).append(future)
            try:
                await self._send(macaco)
                return await asyncio.wait_for(future, REQUEST_TIMEOUT)
            except TimeoutError:
                _LOGGER.debug(
                    "No answer 0x%02x from %s (attempt %d/%d)",
                    answer_funcode,
                    self.host,
                    attempt,
                    retries,
                )
            finally:
                waiters = self._waiters.get(answer_funcode, [])
                if future in waiters:
                    waiters.remove(future)
        raise SoulissConnectionError(
            f"gateway {self.host} did not answer request 0x{macaco[0]:02x}"
        )

    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            frame = frames.parse_vnet(data)
        except FrameError as err:
            _LOGGER.debug("Dropping datagram from %s: %s", addr, err)
            return

        if frame.funcode == FC_ACTION_MESSAGE:
            # action messages are broadcast by ANY node, not just the gateway
            _LOGGER.debug(
                "Action message 0x%04x/0x%02x from 0x%04x (%d data bytes)",
                frame.putin,
                frame.startoffset,
                frame.source,
                len(frame.payload),
            )
            for action_callback in list(self._action_callbacks):
                action_callback(
                    frame.source, frame.putin, frame.startoffset, frame.payload
                )
            return

        if (frame.source & 0xFF) != self.dest_address:
            _LOGGER.debug(
                "Dropping frame from foreign vNet source 0x%04x", frame.source
            )
            return

        self._ping_misses = 0
        self._set_connected(True)

        if frame.funcode in STATE_ANSWERS:
            self._handle_state(frame)
        elif frame.funcode == FC_TYPICAL_ANS:
            self._handle_typicals(frame)
        elif frame.funcode == FC_HEALTH_ANS:
            self._handle_health(frame)
        elif frame.funcode in ERROR_CODES:
            _LOGGER.warning("Gateway %s reported error 0x%02x", self.host, frame.funcode)

        for future in self._waiters.get(frame.funcode, []):
            if not future.done():
                future.set_result(frame)

    def _handle_state(self, frame: MacacoFrame) -> None:
        node = self.nodes.get(frame.startoffset)
        if node:
            node.apply_state(frame.payload)

    def _handle_typicals(self, frame: MacacoFrame) -> None:
        discovered: list[Node] = []
        for chunk_index in range(0, len(frame.payload), self.slots_per_node):
            node_index = frame.startoffset + chunk_index // self.slots_per_node
            node = self.nodes.setdefault(node_index, Node(node_index))
            was_empty = not node.slots
            typicals = frame.payload[chunk_index : chunk_index + self.slots_per_node]
            if node.apply_typicals(typicals):
                _LOGGER.debug(
                    "Node %d typicals: %s",
                    node_index,
                    {s.index: hex(s.typical) for s in node.slots.values()},
                )
                if was_empty and node.slots:
                    discovered.append(node)
        if discovered and self.connected:
            for node in discovered:
                _LOGGER.info("Node %d reported its typicals late", node.index)
                for callback in list(self._discovery_callbacks):
                    callback(node)
            # fetch the current OUT state of the freshly discovered slots
            self._poll_task = asyncio.get_running_loop().create_task(
                self._poll_quietly()
            )

    async def _poll_quietly(self) -> None:
        try:
            await self.poll()
        except SoulissError as err:
            _LOGGER.debug("State poll after late discovery failed: %s", err)

    def _handle_health(self, frame: MacacoFrame) -> None:
        for offset, health in enumerate(frame.payload):
            node = self.nodes.get(frame.startoffset + offset)
            if node:
                node.update_health(health)

    def _handle_connection_lost(self, exc: Exception | None) -> None:
        if exc:
            _LOGGER.warning("UDP endpoint closed unexpectedly: %s", exc)
        self._set_connected(False)

    # ---------------------------------------------------------- maintenance

    async def _maintenance_loop(self) -> None:
        """Keep the subscription and availability state alive."""
        last_subscribe = time.monotonic()
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await self._request(frames.ping(), FC_PING_ANS)
            except SoulissConnectionError:
                self._ping_misses += 1
                if self._ping_misses >= MAX_PING_MISSES:
                    self._set_connected(False)
                continue
            try:
                # nodes that never reported their typicals (e.g. they were
                # still booting when we connected): keep asking
                for index, node in self.nodes.items():
                    if not node.slots:
                        await self._send(frames.typical_request(1, startoffset=index))
            except SoulissConnectionError:
                continue
            now = time.monotonic()
            if now - last_subscribe >= SUBSCRIPTION_REFRESH:
                last_subscribe = now
                try:
                    await self._send(frames.subscribe(self.node_count))
                    await self._send(frames.health_request(self.node_count))
                except SoulissConnectionError:
                    continue
