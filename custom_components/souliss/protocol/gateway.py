"""Asyncio UDP client for a Souliss gateway."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from . import frames
from .const import (
    DEFAULT_LOCAL_PORT,
    DEFAULT_NODE_INDEX,
    DEFAULT_SLOTS_PER_NODE,
    DEFAULT_USER_INDEX,
    ERROR_CODES,
    FC_DBSTRUCT_ANS,
    FC_HEALTH_ANS,
    FC_PING_ANS,
    FC_TYPICAL_ANS,
    GATEWAY_PORT,
    STATE_ANSWERS,
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

AvailabilityCallback = Callable[[bool], None]


class SoulissError(Exception):
    """Base error for gateway communication."""


class SoulissConnectionError(SoulissError):
    """Gateway did not answer."""


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
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0
        self._ping_misses = 0
        self._waiters: dict[int, list[asyncio.Future[MacacoFrame]]] = {}
        self._availability_callbacks: list[AvailabilityCallback] = []

    # ---------------------------------------------------------------- setup

    async def connect(self) -> None:
        """Bind the socket, enumerate the network and subscribe to updates."""
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _Protocol(self),
            local_addr=("0.0.0.0", self.local_port),
        )
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
                    frames.typical_request(1, startoffset=index), FC_TYPICAL_ANS
                )
            except SoulissConnectionError:
                _LOGGER.warning("Node %d did not report its typicals", index)

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

    async def _request(self, macaco: bytes, answer_funcode: int) -> MacacoFrame:
        """Send a request and wait for the matching answer, with retries."""
        for attempt in range(1, REQUEST_RETRIES + 1):
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
                    REQUEST_RETRIES,
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
        for chunk_index in range(0, len(frame.payload), self.slots_per_node):
            node_index = frame.startoffset + chunk_index // self.slots_per_node
            node = self.nodes.setdefault(node_index, Node(node_index))
            typicals = frame.payload[chunk_index : chunk_index + self.slots_per_node]
            if node.apply_typicals(typicals):
                _LOGGER.debug(
                    "Node %d typicals: %s",
                    node_index,
                    {s.index: hex(s.typical) for s in node.slots.values()},
                )

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
            now = time.monotonic()
            if now - last_subscribe >= SUBSCRIPTION_REFRESH:
                last_subscribe = now
                try:
                    await self._send(frames.subscribe(self.node_count))
                    await self._send(frames.health_request(self.node_count))
                except SoulissConnectionError:
                    continue
