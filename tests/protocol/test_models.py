"""Tests for the node/slot model."""

from protocol import const
from protocol.frames import encode_half_float
from protocol.models import Node


def _typ_array(mapping: dict[int, int], size: int = 24) -> bytes:
    array = bytearray(size)
    for slot, typical in mapping.items():
        array[slot] = typical
        for extra in range(const.TYPICAL_EXTRA_SLOTS.get(typical, 0)):
            array[slot + 1 + extra] = const.SLOT_RELATED
    return bytes(array)


def test_apply_typicals_builds_slots_with_sizes() -> None:
    node = Node(0)
    changed = node.apply_typicals(
        _typ_array({0: const.T12, 1: const.T22, 2: const.T52, 4: const.T61})
    )
    assert changed
    assert {i: s.typical for i, s in node.slots.items()} == {
        0: const.T12,
        1: const.T22,
        2: const.T52,
        4: const.T61,
    }
    assert node.slots[2].size == 2
    assert node.slots[4].size == 2
    # re-applying the same layout keeps the slot objects and reports no change
    slot_before = node.slots[0]
    assert not node.apply_typicals(
        _typ_array({0: const.T12, 1: const.T22, 2: const.T52, 4: const.T61})
    )
    assert node.slots[0] is slot_before


def test_apply_state_updates_and_notifies() -> None:
    node = Node(0)
    node.apply_typicals(_typ_array({0: const.T12, 2: const.T52}))
    events: list[tuple[int, bytes]] = []
    node.slots[0].register_callback(lambda: events.append((0, node.slots[0].raw)))
    node.slots[2].register_callback(lambda: events.append((2, node.slots[2].raw)))

    out = bytearray(24)
    out[0] = const.T1N_ON_COIL
    out[2:4] = encode_half_float(21.5)
    node.apply_state(bytes(out))

    assert node.slots[0].value == const.T1N_ON_COIL
    assert node.slots[2].analog_value == 21.5
    assert len(events) == 2

    # unchanged publication does not notify again
    node.apply_state(bytes(out))
    assert len(events) == 2


def test_callback_unregister() -> None:
    node = Node(0)
    node.apply_typicals(_typ_array({0: const.T11}))
    calls: list[int] = []
    unregister = node.slots[0].register_callback(lambda: calls.append(1))
    unregister()
    node.apply_state(b"\x01" + bytes(23))
    assert not calls


def test_health_threshold() -> None:
    node = Node(3)
    assert node.alive
    node.update_health(0x10)
    assert not node.alive
    node.update_health(const.HEALTH_BEST)
    assert node.alive
