"""Aion 2 pet soul protocol: passive capture, decoding and progress tracking.

Adapted from elkaida/AION2-pet-tracker (MIT, see LICENSE). Only the parts the
overlay needs are kept: TCP stream reassembly, frame decoding and the two pet
opcodes. Read-only: nothing is ever sent to the game or its servers.

Wire format (server -> client):
    frame  = varint(len) + opcode(2) + payload, where len = opcode + payload + 4
    0xFFFF = LZ4 bundle: uint32 uncompressed size + raw LZ4 block of more frames
    0x0090 = full pet state, sent on entering the world (levels + points)
    0x0D90 = souls gained on a kill (pet id + amount, no running total)
"""
import json
import os
import struct
import sys
import threading
import time

import lz4.block

FROZEN = getattr(sys, "frozen", False)  # running as the PyInstaller exe
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))  # bundled read-only files


def _app_dir():
    """Next to the exe/scripts; falls back to %LOCALAPPDATA% if that folder isn't writable."""
    here = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
    try:
        probe = os.path.join(here, ".write_test")
        open(probe, "w").close()
        os.remove(probe)
        return here
    except OSError:
        fallback = os.path.join(os.environ.get("LOCALAPPDATA", here), "Aion2PetOverlay")
        os.makedirs(fallback, exist_ok=True)
        return fallback


APP_DIR = _app_dir()
if sys.stderr is None:  # windowed exe / pythonw: libraries still print warnings
    sys.stderr = sys.stdout = open(os.devnull, "w")
STATE_FILE = os.path.join(APP_DIR, "pet_state.json")
LEGACY_STATE_FILE = os.path.join(APP_DIR, "aion2_pet_tracker_state.json")
LOG_FILE = os.path.join(APP_DIR, "pet_overlay.log")

REQ = [5, 25, 75]  # souls needed for levels 1, 2 and 3 (counter resets each level)
MAX_LEVEL = len(REQ)

OP_STATE = b"\x00\x90"
OP_GAIN = b"\x0d\x90"
OP_LZ4 = b"\xff\xff"

# Opcodes seen in the stream. Used to find the next frame boundary after a lost
# segment; grows as new opcodes show up.
KNOWN_OPS = {bytes.fromhex(h) for h in (
    "0036 1d37 1c37 0438 008d 0238 0638 1a37 1b37 4b36 0338 0138 3b38 3d38 2a37 0191 2937 8456 "
    "2a38 218d ffff 2b38 2c38 1b56 3538 4738 4136 1838 1938 0336 3438 3138 1f56 4a36 3436 4236 "
    "1e56 4736 1f37 2156 2037 0d90 3237 048d 2237 3536 0090").split()}


def log(*parts):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(map(str, parts)) + "\n")


def npcap_installed():
    npcap_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "Npcap")
    return os.path.isfile(os.path.join(npcap_dir, "wpcap.dll"))


# ---------------------------------------------------------------- decoding

def read_varint(buf, i):
    value = shift = 0
    while True:
        if i >= len(buf):
            raise IndexError
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, i


def split_frames(buf):
    """Cuts a buffer into frames. Returns (frames, rest), or (frames, None) on garbage."""
    i, frames = 0, []
    while i < len(buf):
        try:
            n, j = read_varint(buf, i)
        except IndexError:
            break
        total = n - 4 + (j - i)
        if total < (j - i) + 2 or total > 4_000_000:
            return frames, None
        if i + total > len(buf):
            break
        frames.append(buf[i:i + total])
        i += total
    return frames, buf[i:]


def frame_op(frame):
    _, j = read_varint(frame, 0)
    return frame[j:j + 2]


def unpack(frame):
    """Yields (opcode, payload), expanding compressed bundles."""
    _, j = read_varint(frame, 0)
    op, body = frame[j:j + 2], frame[j + 2:]
    if op != OP_LZ4:
        yield op, body
        return
    size = int.from_bytes(body[:4], "little")
    try:
        raw = lz4.block.decompress(body[4:], uncompressed_size=size)
    except Exception as e:
        log("lz4:", e)
        return
    inner, _ = split_frames(raw)
    for f in inner:
        yield from unpack(f)


def parse_state(payload):
    i = 4  # uint32 header, meaning unknown
    count, i = read_varint(payload, i)
    levels = {}
    for _ in range(count):
        pid, pid2, level = struct.unpack_from("<III", payload, i)
        i += 12
        if pid != pid2 or level > 10:
            raise ValueError("unexpected level entry")
        levels[pid] = level
    count, i = read_varint(payload, i)
    points = {}
    for _ in range(count):
        pid, pts = struct.unpack_from("<II", payload, i)
        i += 8
        points[pid] = pts
    return levels, points


def parse_gain(payload):
    kind, pid, amount = struct.unpack_from("<BII", payload, 0)
    return kind, pid, amount


def find_sync(buf, need=8):
    """Offset where `need` consecutive frames with known opcodes start
    (or known frames that end exactly at the end of the buffer)."""
    n = len(buf)
    for off in range(n):
        i, good = off, 0
        while good < need:
            try:
                length, j = read_varint(buf, i)
            except IndexError:
                break
            total = length - 4 + (j - i)
            if total < (j - i) + 2 or buf[j:j + 2] not in KNOWN_OPS:
                good = -1
                break
            if i + total > n:
                break
            i += total
            good += 1
        if good >= need or (good > 0 and i == n):
            return off
    return None


class Stream:
    """Reassembles one server->client TCP stream, tolerating retransmits and reordering."""
    MASK, HALF = 0xFFFFFFFF, 0x80000000

    def __init__(self):
        self.next = None
        self.pending = {}
        self.buf = b""
        self.resync = True  # capture may have started mid-frame

    def add(self, seq, data):
        if self.next is None:
            self.next = seq
        if len(data) > len(self.pending.get(seq, b"")):
            self.pending[seq] = data
        out = bytearray()
        moved = True
        while moved:
            moved = False
            for s in list(self.pending):
                d = (s - self.next) & self.MASK
                if d != 0 and d < self.HALF:
                    continue  # still in the future
                chunk = self.pending.pop(s)
                skip = 0 if d == 0 else (self.next - s) & self.MASK
                if skip < len(chunk):
                    out += chunk[skip:]
                    self.next = (self.next + len(chunk) - skip) & self.MASK
                    moved = True
        if len(self.pending) > 8:  # a segment was lost by the capture: jump the hole
            log("gap, resync")
            self.buf, self.resync = b"", True
            self.next = min(self.pending, key=lambda s: (s - self.next) & self.MASK)
            return self.add(self.next, self.pending.pop(self.next))
        self.buf += bytes(out)
        if self.resync:
            off = find_sync(self.buf)
            if off is None:
                if len(self.buf) > 65536:
                    self.buf = b""
                return []
            self.buf, self.resync = self.buf[off:], False
        frames, rest = split_frames(self.buf)
        if rest is None:
            self.buf, self.resync = b"", True
            return frames
        self.buf = rest
        for f in frames:
            KNOWN_OPS.add(frame_op(f))
        return frames


class Decoder:
    """Raw TCP segments -> events ("state", levels, points) / ("gain", pet_id, amount)."""

    def __init__(self, emit):
        self.emit = emit
        self.streams = {}

    def segment(self, conn, seq, data):
        stream = self.streams.setdefault(conn, Stream())
        for frame in stream.add(seq, data):
            try:
                for op, payload in unpack(frame):
                    if op == OP_GAIN:
                        kind, pid, amount = parse_gain(payload)
                        if kind != 1:
                            log("gain kind", kind, pid, amount)
                        self.emit(("gain", pid, amount))
                    elif op == OP_STATE:
                        try:
                            self.emit(("state",) + parse_state(payload))
                        except Exception as e:
                            log("state parse:", e, payload[:64].hex())
            except Exception as e:
                log("frame:", e, frame[:32].hex())


# ---------------------------------------------------------------- capture

def run_sniffer(emit):
    """Blocks forever, emitting decoder events plus ("conn", bool) every 2 s."""
    import psutil
    from scapy.all import IP, TCP, Raw, conf, sniff

    game_ports = set()

    def watch_game():
        while True:
            try:
                pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "aion2.exe"}
                ports = {c.laddr[1] for c in psutil.net_connections(kind="tcp")
                         if c.pid in pids and c.raddr and not c.raddr[0].startswith("127.")
                         and c.raddr[1] not in (80, 443)}
                game_ports.clear()
                game_ports.update(ports)
                emit(("conn", bool(ports)))
            except Exception as e:
                log("psutil:", e)
            time.sleep(2)

    threading.Thread(target=watch_game, daemon=True).start()
    decoder = Decoder(emit)

    def on_packet(p):
        if Raw in p and TCP in p and p[TCP].dport in game_ports:
            decoder.segment((p[IP].src, p[TCP].sport, p[TCP].dport), p[TCP].seq, bytes(p[Raw].load))

    ifaces = [i.network_name for i in conf.ifaces.values() if i.ip and not i.ip.startswith("127.")]
    sniff(iface=ifaces, filter="tcp and not port 443 and not port 80", prn=on_packet, store=False)


# ---------------------------------------------------------------- progress

class Tracker:
    """Per-pet level and souls toward the next level, mirroring the server.
    The server stops counting at max level, so overflow souls go to `extra`."""

    def __init__(self, path=STATE_FILE):
        self.path = path
        self.levels, self.points, self.extra = {}, {}, {}
        self.recent = []    # pet ids, most recent soul first
        self.synced = None  # time of the last full state from the server
        self.load()

    def load(self):
        for path in (self.path, LEGACY_STATE_FILE):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                break
            except (OSError, ValueError):
                continue
        else:
            return
        ints = lambda m: {int(k): v for k, v in m.items()}
        self.levels, self.points = ints(d.get("levels", {})), ints(d.get("points", {}))
        self.extra = ints(d.get("extra", {}))
        self.recent = d.get("recent", [])
        self.synced = d.get("synced")

    def save(self):
        d = {"levels": self.levels, "points": self.points, "extra": self.extra,
             "recent": self.recent, "synced": self.synced}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, self.path)

    def on_event(self, ev):
        if ev[0] == "state":
            self.levels, self.points = dict(ev[1]), dict(ev[2])
            self.synced = time.strftime("%m/%d %H:%M")
        elif ev[0] == "gain":
            _, pid, amount = ev
            self.add_points(pid, amount)
            if pid in self.recent:
                self.recent.remove(pid)
            self.recent.insert(0, pid)
            del self.recent[30:]

    def add_points(self, pid, amount):
        level = self.levels.get(pid, 0)
        if level >= MAX_LEVEL:
            self.extra[pid] = self.extra.get(pid, 0) + amount
            return
        pts = self.points.get(pid, 0) + amount
        while level < MAX_LEVEL and pts >= REQ[level]:
            pts -= REQ[level]
            level += 1
        if level >= MAX_LEVEL and pts:
            self.extra[pid] = self.extra.get(pid, 0) + pts
            pts = 0
        self.levels[pid], self.points[pid] = level, pts
