"""Offline check: builds fake packets (world-entry state + a soul pickup) and
verifies the decoder, the "souls left" math, the bundled data, settings and the UI,
without the game running.

    .venv\\Scripts\\python selftest.py
    Aion2PetOverlay.exe --selftest      (exit code 0 = pass; details in pet_overlay.log)
"""
import json
import os
import struct
import tempfile

import lz4.block

import pet_overlay
import pet_protocol as proto
import updater


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
    check_map()

    check_updater()

    check_settings()

    # app logic without windows: a sync, a soul and an update notice
    settings_path = os.path.join(tempfile.mkdtemp(), "pet_overlay_ui.json")
    app = pet_overlay.App(tracker, settings_path=settings_path, selftest=True)
    app.handle([events[0], ("gain", 1005, 1), ("conn", True),
                ("update", {"version": "9.9.9", "page": "", "exe_url": None, "sums_url": None})])
    assert (tracker.levels[1005], tracker.points[1005]) == (2, 71), (tracker.levels, tracker.points)
    assert tracker.synced and app.capturing
    assert app.update_payload() == {"status": "available", "version": "9.9.9", "progress": 0.0}
    payload = json.loads(json.dumps(app.ui_payload()))  # must survive the trip to the page
    assert len(payload["pets"]) == len(pet_overlay.PETS) and payload["state"]["levels"]["1005"] == 2
    assert "tiles" not in json.dumps(payload["pets"])
    mapped = next(pid for pid, p in pet_overlay.PETS.items() if p.get("spawn") and p["spawn"]["dots"])
    assert app.map_uri(mapped).startswith("data:image/webp;base64,")  # tiles from check_map's fake fetcher
    app.update_settings({"opacity": 5, "mode": "nope", "toast_time": 8, "geometry": {"overlay": [0, 0, 1, 1]}})
    assert (app.settings["opacity"], app.settings["mode"], app.settings["toast_time"]) == (50, "overlay", 8)
    assert app.settings["geometry"]["overlay"] != [0, 0, 1, 1]
    app.update_settings({"toast_pos": "custom", "toast_xy": [1, 2], "tray_hint_shown": True})  # last two are app-only
    assert app.settings["toast_pos"] == "custom" and app.settings["toast_xy"] is None
    assert not app.settings["tray_hint_shown"]
    assert pet_overlay.clean_settings({"toast_xy": [10, 20], "tray_hint_shown": True})["toast_xy"] == [10, 20]
    assert pet_overlay.load_settings(settings_path)["toast_time"] == 8

    # the real window: WebView2 loads the page, which calls back into Python, then it closes
    assert pet_overlay.webview2_available(), "WebView2 runtime missing"
    app = pet_overlay.App(tracker, settings_path=settings_path, selftest=True)
    app.run()
    assert app.ready_seen.is_set(), "the page never called back"
    print("OK")


def check_settings():
    """v1 (Tk) settings files keep their position, opacity and filters."""
    path = os.path.join(tempfile.mkdtemp(), "pet_overlay_ui.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"geom": "962x415+60+120", "alpha": 0.9, "sort": "left", "map": "All maps", "no_mob": True,
                   "genus": {"Cogni": True, "Natura": False}, "check_updates": False}, f)
    s = pet_overlay.load_settings(path)
    assert s["geometry"]["overlay"] == [60, 120, 962, 415], s["geometry"]
    assert (s["opacity"], s["map"], s["no_mob"], s["check_updates"]) == (90, "", True, False)
    assert s["genus"] == {"Cogni": True, "Natura": False, "Fera": True, "Varian": True}
    assert pet_overlay.load_settings(os.path.join(tempfile.mkdtemp(), "missing.json")) == pet_overlay.DEFAULTS


def check_map():
    """Spawn data is bundled and the minimap renders, using a fake tile instead of the network."""
    from PIL import Image
    import pet_map
    farmable = [p for p in pet_overlay.PETS.values() if p.get("mob")]
    with_spawn = [p for p in farmable if p.get("spawn") and p["spawn"]["dots"]]
    assert len(with_spawn) >= len(farmable) * 0.8, (len(with_spawn), len(farmable))
    pet_map.fetch_tile = lambda path: Image.new("RGB", (256, 256), "#406040")
    img = pet_map.render({"tiles": [["/t.webp", 0, 0, 50, 50]], "dots": [[75, 75]]})
    assert img.size == (pet_map.WIDTH, pet_map.HEIGHT)
    assert img.getpixel((10, 10)) == (0x40, 0x60, 0x40)  # tile
    assert img.getpixel((pet_map.WIDTH - 10, 10)) == (0x0b, 0x14, 0x20)  # water
    assert img.getpixel((round(pet_map.WIDTH * 0.75), round(pet_map.HEIGHT * 0.75))) == (0xff, 0xd1, 0x66)  # dot


def check_updater():
    v = updater.parse_version
    assert v("v1.10.0") > v("v1.9.3") > v("1.9") > v("garbage")
    assert updater.expected_hash("ABC123  Aion2PetOverlay.exe\nfff  other.txt\n") == "abc123"

    # swap: the running exe becomes .old, the new one takes its name
    d = tempfile.mkdtemp()
    cur, new = os.path.join(d, "app.exe"), os.path.join(d, "app.exe.new")
    for path, data in ((cur, b"old"), (new, b"new")):
        with open(path, "wb") as f:
            f.write(data)
    updater.swap(cur, new)
    assert open(cur, "rb").read() == b"new"
    assert open(cur + ".old", "rb").read() == b"old"
    assert not os.path.exists(new)


if __name__ == "__main__":
    main()
