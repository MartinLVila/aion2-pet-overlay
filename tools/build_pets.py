"""Builds data/pets.json: genus, best soul mob, mob level, spawn zone and spawn minimap for every pet.

Source: metabot.gg (English pages). Run by hand only when new pets ship:

    python tools/build_pets.py

Fetches roughly one page per second to stay polite.
"""
import html as htmllib
import json
import os
import re
import time
import urllib.request

BASE = "https://metabot.gg"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pets.json")
GENERA = {"Fera", "Natura", "Varian", "Cogni", "Special"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (aion2-pet-overlay)"})
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        except OSError:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def text(s):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_list(page):
    """One table per genus, each preceded by a heading with the genus name."""
    headings = [(m.start(), text(m.group(2))) for m in re.finditer(r"<(h[2-3])[^>]*>(.*?)</\1>", page, re.S)]
    pets = {}
    for row in re.finditer(r"<tr>(.*?)</tr>", page, re.S):
        r = row.group(1)
        pid = re.search(r'data-a2-k="own:m:(\d+)"', r)
        if not pid:
            continue
        genus = next((h for pos, h in reversed(headings) if pos < row.start() and h in GENERA), "?")
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
        mob = re.search(r'href="(/[^"]*/monsters/[^"]+)".*?<span[^>]*>([^<]+)</span></a>'
                        r'(?:<span[^>]*> \+<!-- -->(\d+))?', r, re.S)
        level = re.search(r"Lv\. (\d+)", r)
        pets[pid.group(1)] = {
            "genus": genus,
            "name": text(cells[0]) if cells else "",
            "mob": htmllib.unescape(mob.group(2)) if mob else None,
            "mob_url": mob.group(1) if mob else None,
            "more": int(mob.group(3)) if mob and mob.group(3) else 0,
            "lvl": int(level.group(1)) if level else None,
        }
    return pets


def parse_mob(page):
    """Zone and map with the most spawns, from the 'Zone | Map | Spawns' table."""
    body = text(re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S).replace("<", "\n<"))
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    try:
        i = lines.index("Spawns")
    except ValueError:
        return None, None
    best = None
    j = i + 1
    while j + 2 < len(lines) and lines[j + 2].replace(",", "").isdigit():
        zone, map_, count = lines[j], lines[j + 1], int(lines[j + 2].replace(",", ""))
        if not best or count > best[2]:
            best = (zone, map_, count)
        j += 3
    return (best[0], best[1]) if best else (None, None)


FIGURE = re.compile(r'<figure class="[^"]*spawnMap"[^>]*aria-label="([^"]*)">(.*?)</figure>', re.S)
TILE = re.compile(r'spawnTile" style="left:([-\d.]+)%;top:([-\d.]+)%;width:calc\(([\d.]+)% \+ 1px\);'
                  r'height:calc\(([\d.]+)% \+ 1px\);background-image:url\(([^)]+)\)')
DOT = re.compile(r'spawnDot"[^>]*style="left:([-\d.]+)%;top:([-\d.]+)%')
MAP_LINK = re.compile(r'href="(/en/aion-2/map/[^"?]+\?focus=npc:\d+)"')


def parse_spawn(page, map_):
    """Spawn-point minimap for `map_`: the 16:9 view's tiles and dots, all in % of the view."""
    figures = [(label, body) for label, body in FIGURE.findall(page)]
    if not figures:
        return None
    label, body = next((f for f in figures if f[0].endswith(f"on the {map_} map")), figures[0])
    r = lambda v: round(float(v), 2)
    link = MAP_LINK.search(page)
    return {
        "tiles": [[url, r(left), r(top), r(w), r(h)] for left, top, w, h, url in TILE.findall(body)],
        "dots": [[r(x), r(y)] for x, y in DOT.findall(body)],
        "link": link.group(1) if link else None,
    }


def main():
    pets = parse_list(get(BASE + "/en/aion-2/mounts"))
    print(len(pets), "pets")
    for pid, p in pets.items():
        if p["mob_url"]:
            time.sleep(1)
            try:
                page = get(BASE + p["mob_url"])
                p["zone"], p["map"] = parse_mob(page)
                p["spawn"] = parse_spawn(page, p["map"])
            except Exception as e:
                print("  error", pid, e)
                p["zone"] = p["map"] = p["spawn"] = None
            print(pid, p["name"], "|", p["mob"], "|", p.get("zone"), "/", p.get("map"), flush=True)
        p.pop("mob_url")
    write(pets)


def write(pets):
    """One pet per line: spawn coordinates would otherwise take tens of thousands of lines."""
    lines = [f"{json.dumps(pid)}: {json.dumps(p, ensure_ascii=False)}" for pid, p in pets.items()]
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("{\n" + ",\n".join(lines) + "\n}\n")


if __name__ == "__main__":
    main()
