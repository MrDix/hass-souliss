"""Object model of a Souliss network as seen through a gateway."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .const import (
    ANALOG_INPUT_TYPICALS,
    ANALOG_SETPOINT_TYPICALS,
    HEALTH_FRESH,
    SLOT_EMPTY,
    SLOT_RELATED,
    TYPICAL_EXTRA_SLOTS,
)
from .frames import decode_half_float

SlotCallback = Callable[[], None]


@dataclass(slots=True)
class Slot:
    """One typical instance: the slot it starts at plus its raw state bytes."""

    node_index: int
    index: int
    typical: int
    size: int = 1
    raw: bytes = b"\x00"
    _callbacks: list[SlotCallback] = field(default_factory=list)

    @property
    def is_analog(self) -> bool:
        return self.typical in ANALOG_INPUT_TYPICALS or self.typical in ANALOG_SETPOINT_TYPICALS

    @property
    def value(self) -> int:
        """Raw state byte (first slot byte) for digital typicals."""
        return self.raw[0]

    @property
    def analog_value(self) -> float | None:
        """Half-float value for T5n/T6n typicals."""
        if len(self.raw) < 2:
            return None
        return decode_half_float(self.raw[:2])

    def register_callback(self, callback: SlotCallback) -> Callable[[], None]:
        self._callbacks.append(callback)

        def _unregister() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return _unregister

    def update(self, raw: bytes) -> bool:
        """Store new raw state bytes; notify and report True when changed."""
        if raw == self.raw:
            return False
        self.raw = raw
        for callback in list(self._callbacks):
            callback()
        return True


@dataclass(slots=True)
class Node:
    """A Souliss node (gateway itself = index 0, peers = 1..n)."""

    index: int
    slots: dict[int, Slot] = field(default_factory=dict)
    health: int = HEALTH_FRESH
    _callbacks: list[SlotCallback] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.health >= HEALTH_FRESH

    def register_callback(self, callback: SlotCallback) -> Callable[[], None]:
        """Subscribe to node-level changes (currently: health)."""
        self._callbacks.append(callback)

        def _unregister() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return _unregister

    def update_health(self, health: int) -> None:
        if health == self.health:
            return
        self.health = health
        for callback in list(self._callbacks):
            callback()

    def apply_typicals(self, typicals: bytes) -> bool:
        """(Re)build the slot map from a TYP array; True when layout changed."""
        slots: dict[int, Slot] = {}
        index = 0
        while index < len(typicals):
            typical = typicals[index]
            if typical in (SLOT_EMPTY, SLOT_RELATED):
                index += 1
                continue
            size = 1 + TYPICAL_EXTRA_SLOTS.get(typical, 0)
            existing = self.slots.get(index)
            if existing and existing.typical == typical and existing.size == size:
                slots[index] = existing
            else:
                slots[index] = Slot(self.index, index, typical, size, bytes(size))
            index += size
        changed = {i: (s.typical, s.size) for i, s in slots.items()} != {
            i: (s.typical, s.size) for i, s in self.slots.items()
        }
        self.slots = slots
        return changed

    def apply_state(self, out: bytes) -> None:
        """Distribute an OUT array publication to the slots."""
        for slot in self.slots.values():
            raw = out[slot.index : slot.index + slot.size]
            if len(raw) == slot.size:
                slot.update(raw)
