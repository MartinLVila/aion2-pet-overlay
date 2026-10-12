"""Static spawn minimap for a pet's mob: world-map tiles plus spawn dots, from MetaBot.GG.

Tiles are downloaded on first use and cached next to the app, so each map area is
fetched only once. Positions in data/pets.json are percentages of a 16:9 view.
"""
import os
import threading
import urllib.request

from PIL import Image, ImageDraw

import pet_protocol as proto

BASE = "https://metabot.gg"
CACHE_DIR = os.path.join(proto.APP_DIR, "map_cache")
WIDTH, HEIGHT = 384, 216  # 16:9, same as the source view
WATER = "#0b1420"
DOT, DOT_EDGE = "#ffd166", "#0e0f12"

_lock = threading.Lock()


def fetch_tile(path):
    """Tile image for a site path like /web/aion2/worldmap/...webp, cached on disk."""
    local = os.path.join(CACHE_DIR, *path.strip("/").split("/"))
    with _lock:
        if not os.path.isfile(local):
            os.makedirs(os.path.dirname(local), exist_ok=True)
            req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0 (aion2-pet-overlay)"})
            data = urllib.request.urlopen(req, timeout=20).read()
            with open(local + ".tmp", "wb") as f:
                f.write(data)
            os.replace(local + ".tmp", local)
    return Image.open(local).convert("RGB")


def render(spawn, fetch=None, size=(WIDTH, HEIGHT)):
    """PIL image of the spawn view. Missing tiles are left as water instead of failing."""
    fetch = fetch or fetch_tile
    width, height = size
    img = Image.new("RGB", size, WATER)
    for path, left, top, w, h in spawn["tiles"]:
        box_w, box_h = round(w / 100 * width) + 1, round(h / 100 * height) + 1
        try:
            tile = fetch(path).resize((box_w, box_h), Image.LANCZOS)
        except Exception as e:
            proto.log("map tile:", path, e)
            continue
        img.paste(tile, (round(left / 100 * width), round(top / 100 * height)))
    draw = ImageDraw.Draw(img)
    r = 3
    for x, y in spawn["dots"]:
        cx, cy = x / 100 * width, y / 100 * height
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DOT, outline=DOT_EDGE)
    return img
