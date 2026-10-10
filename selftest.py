"""Offline check: builds fake packets (world-entry state + a soul pickup) and
verifies the decoder, the "souls left" math, the bundled data and the UI,
without the game running.

    .venv\\Scripts\\python selftest.py
    Aion2PetOverlay.exe --selftest      (exit code 0 = pass; details in pet_overlay.log)
"""
import os
import struct
import tempfile

import lz4.block

import pet_overlay
import pet_protocol as proto


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def frame(op, body):
    # declared length = opcode + payload + 4, not counting the varint itself
    return varint(len(body) + 6) + op + body


def state_body(levels, points):
    body = struct.pack("<I", 0) + varint(len(levels))
    for pid, level in levels.items():
        body += struct.pack("<III", pid, pid, level)
    body += varint(len(points))
    for pid, pts in points.items():
        body += struct.pack("<II", pid, pts)
    return body


def main():
    inner = frame(proto.OP_STATE, state_body({1005: 2, 1097: 3, 1010: 1}, {1005: 70, 1010: 3}))
    bundle = frame(proto.OP_LZ4, struct.pack("<I", len(inner)) + lz4.block.compress(inner, store_size=False))
    gain = frame(proto.OP_GAIN, struct.pack("<BII", 1, 1005, 4))
    # unrelated traffic with known opcodes first, like on world entry
    noise = b"".join(frame(bytes.fromhex("0036"), bytes(range(i, i + 30))) for i in range(12))

    events = []
    decoder = proto.Decoder(events.append)
    stream = noise + bundle + gain
    for i in range(0, len(stream), 64):  # in chunks, like TCP segments
        decoder.segment(("1.2.3.4", 1, 2), 1000 + i, stream[i:i + 64])
    assert [e[0] for e in events] == ["state", "gain"], events

    tracker = proto.Tracker.__new__(proto.Tracker)  # skip loading the real state file
    tracker.path = os.path.join(tempfile.mkdtemp(), "pet_state.json")
    tracker.synced = None
    tracker.levels, tracker.points, tracker.extra, tracker.recent = {}, {}, {}, []
    for e in events:
        tracker.on_event(e)
    assert (tracker.levels[1005], tracker.points[1005]) == (2, 74), (tracker.levels, tracker.points)
    assert tracker.recent == [1005]

    tracker.add_points(1005, 3)  # 1 soul finishes Lv3, the other 2 are wasted
    assert (tracker.levels[1005], tracker.points[1005], tracker.extra[1005]) == (3, 0, 2)
    tracker.add_points(1010, 2)  # Lv1 with 3 + 2 = 5 souls, still short of 25
    assert (tracker.levels[1010], tracker.points[1010]) == (1, 5)

    assert pet_overlay.remaining(0, 0) == 105
    assert pet_overlay.remaining(1, 3) == 97
    assert pet_overlay.remaining(2, 74) == 1
    assert pet_overlay.remaining(3, 0) == 0
    assert pet_overlay.progress_text(1, 10) == "90 to Lv3  (15 to Lv2)"
    assert pet_overlay.progress_text(2, 74) == "1 to Lv3"

    # bundled data and capture library
    assert len(pet_overlay.PETS) >= 200, len(pet_overlay.PETS)
    from scapy.all import sniff  # noqa: F401  (fails if the exe is missing scapy modules)

    # UI: build the window, feed it a sync and a soul, then close it
    overlay = pet_overlay.Overlay(tracker)
    overlay.events.put(events[0])
    overlay.events.put(("gain", 1005, 1))
    overlay.root.after(1500, overlay.root.destroy)
    overlay.root.mainloop()
    assert (tracker.levels[1005], tracker.points[1005]) == (2, 71), (tracker.levels, tracker.points)
    assert tracker.synced
    print("OK")


if __name__ == "__main__":
    main()
