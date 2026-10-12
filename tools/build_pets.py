"""Builds data/pets.json: genus and every mob that drops each pet's souls, with its level, drop
chance, spawn zones, nearest Kibelisk and spawn minimap.

Source: metabot.gg (English pages). Run by hand only when new pets ship:

    python tools/build_pets.py [--only PET_ID ...]

Fetches roughly one page per second to stay polite (one page per pet plus one per distinct mob).
"""
import html as htmllib
import json
import os
import re
import sys
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
        link = re.search(r'href="(/en/aion-2/mounts/[^"]+)"', r)
        if not pid or not link:
            continue
        genus = next((h for pos, h in reversed(headings) if pos < row.start() and h in GENERA), "?")
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
        pets[pid.group(1)] = {"genus": genus, "name": text(cells[0]) if cells else "", "url": link.group(1)}
    return pets


DROP_PANEL = re.compile(r'<div id="where-panel-drop".*?</ol>', re.S)
DROP_ROW = re.compile(r'<li id="where-drop-(\d+)"[^>]*>(.*?)</li>', re.S)


def parse_drops(page):
    """The pet page's 'Monster drops' list, one row per NPC: its id, mob link, name, chance, level, zones
    (as one 'A, B and C' entry), map, spawn count and nearest Kibelisk."""
    panel = DROP_PANEL.search(page)
    drops = []
    for npc, row in DROP_ROW.findall(panel.group(0) if panel else ""):
        url = re.search(r'href="(/en/aion-2/monsters/[^"]+)"', row)
        name = re.search(r'nameText">([^<]+)<', row)
        if not url or not name:
            continue
        pct = re.search(r'__pct">([\d.]+)%', row)
        level = re.search(r"Lv\. (\d+)", row)
        subs = [text(s) for s in re.findall(r'__sub">(.*?)</div>', row, re.S)]
        place = next((s for s in subs if "spawns" in s), "")
        parts = [p.strip() for p in place.split("·")]
        kisk = re.search(r'__kisk">(.*?)</div>', row, re.S)
        drops.append({
            "npc": npc,
            "url": url.group(1),
            "name": htmllib.unescape(name.group(1)).strip(),
            "pct": float(pct.group(1)) if pct else None,
            "lvl": int(level.group(1)) if level else None,
            "zones": [[parts[0], parts[1], int(re.sub(r"\D", "", parts[2]) or 0)]] if len(parts) == 3 else [],
            "kisk": text(kisk.group(1)).removeprefix("Nearest Kibelisk:").strip() if kisk else None,
        })
    return drops


def parse_zones(page):
    """Every row of the mob page's 'Zone | Map | Spawns' table, most spawns first."""
    body = text(re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S).replace("<", "\n<"))
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    try:
        i = lines.index("Spawns")
    except ValueError:
        return []
    zones = []
    j = i + 1
    while j + 2 < len(lines) and lines[j + 2].replace(",", "").isdigit():
        zones.append([lines[j], lines[j + 1], int(lines[j + 2].replace(",", ""))])
        j += 3
    return sorted(zones, key=lambda z: -z[2])


FIGURE = re.compile(r'<figure class="[^"]*spawnMap"[^>]*aria-label="([^"]*)">(.*?)</figure>', re.S)
TILE = re.compile(r'spawnTile" style="left:([-\d.]+)%;top:([-\d.]+)%;width:calc\(([\d.]+)% \+ 1px\);'
                  r'height:calc\(([\d.]+)% \+ 1px\);background-image:url\(([^)]+)\)')
DOT = re.compile(r'spawnDot"[^>]*style="left:([-\d.]+)%;top:([-\d.]+)%')
MAP_LINK = re.compile(r'href="(/en/aion-2/map/[^"?]+\?focus=npc:\d+)"')


def parse_spawn(page, map_):
    """Spawn-point minimap for `map_`: the 16:9 view's tiles and dots, all in % of the view."""
    figures = FIGURE.findall(page)
    if not figures:
        return None
    label, body = next((f for f in figures if f[0].endswith(f"on the {map_} map")), figures[0])
    r = lambda v: round(float(v), 2)
    link = MAP_LINK.search(page)
    return {
        "map": label.rsplit("on the ", 1)[-1].removesuffix(" map") if "on the " in label else map_,
        "tiles": [[url, r(left), r(top), r(w), r(h)] for left, top, w, h, url in TILE.findall(body)],
        "dots": [[r(x), r(y)] for x, y in DOT.findall(body)],
        "link": link.group(1) if link else None,
    }


def mob_info(url, cache):
    """Npc id, zones and spawn minimap from the mob's own page, fetched once per mob.

    Several NPCs can share a name and therefore one mob page, which describes only one of them
    (the npc id in its map link), so callers use it only for that NPC."""
    if url not in cache:
        time.sleep(1)
        try:
            page = get(BASE + url)
            zones = parse_zones(page)
            npc = re.search(r"focus=npc:(\d+)", page)
            cache[url] = {"npc": npc.group(1) if npc else None, "zones": zones,
                          "spawn": parse_spawn(page, zones[0][1] if zones else "")}
        except Exception as e:
            print("  error", url, e)
            cache[url] = {"npc": None, "zones": [], "spawn": None}
    return cache[url]


def page_spawn(page, name, map_):
    """Fallback minimap from the pet page's own map: its dots for mobs called `name`, if it shows `map_`."""
    for label, body in FIGURE.findall(page):
        if not label.endswith(f"on the {map_} map"):
            continue
        dots = [[round(float(x), 2), round(float(y), 2)] for x, y, title in
                re.findall(r'spawnDot"[^>]*style="left:([-\d.]+)%;top:([-\d.]+)%[^"]*"[^>]*title="([^"]*)"', body)
                if htmllib.unescape(title) == name]
        if dots:
            r = lambda v: round(float(v), 2)
            return {"map": map_, "dots": dots, "link": None,
                    "tiles": [[u, r(left), r(top), r(w), r(h)] for left, top, w, h, u in TILE.findall(body)]}
    return None


def map_link(map_, npc):
    return f"/en/aion-2/map/{re.sub(r'[^a-z0-9]+', '-', map_.lower()).strip('-')}?focus=npc:{npc}"


def build_pet(p, cache):
    page = get(BASE + p["url"])
    merged = {}
    for d in parse_drops(page):
        # the pet page row is per NPC, so it is the truth for level and place; the mob page adds
        # per-zone counts and the minimap only when it describes this very NPC
        # (MetaBot's mob pages can even mix NPCs, so their data must also agree with the row)
        info = mob_info(d["url"], cache)
        row_map = d["zones"][0][1] if d["zones"] else None
        row_spawns = sum(z[2] for z in d["zones"])
        same = (info["npc"] == d["npc"] and info["zones"] and {z[1] for z in info["zones"]} == {row_map}
                and sum(z[2] for z in info["zones"]) == row_spawns)
        zones = info["zones"] if same else d["zones"]
        map_ = row_map
        spawn = info["spawn"] if same and info["spawn"] and info["spawn"]["map"] == map_ else None
        spawn = spawn or (page_spawn(page, d["name"], map_) if map_ else None)
        if map_ and not spawn:
            spawn = {"map": map_, "tiles": [], "dots": [], "link": None}  # no minimap, but a link to the map
        if spawn and not spawn.get("link"):
            spawn = {**spawn, "link": map_link(map_, d["npc"])}
        m = {"name": d["name"], "lvl": d["lvl"], "pct": d["pct"], "zones": zones, "kisk": d["kisk"], "spawn": spawn}
        # NPCs with the same name, level and map are one mob to the player: merge them
        key = (d["name"], d["lvl"], map_)
        if key not in merged:
            merged[key] = m
            continue
        prev = merged[key]
        prev["pct"] = max(prev["pct"] or 0, m["pct"] or 0) or None
        counts = {(z[0], z[1]): z[2] for z in prev["zones"]}
        for zone, zmap, n in zones:
            counts[(zone, zmap)] = counts.get((zone, zmap), 0) + n
        prev["zones"] = sorted([[z, zm, n] for (z, zm), n in counts.items()], key=lambda z: -z[2])
        prev["kisk"] = prev["kisk"] or m["kisk"]
        if not prev["spawn"]:
            prev["spawn"] = spawn
        elif spawn and spawn is not prev["spawn"] and spawn["map"] == prev["spawn"]["map"]:
            prev["spawn"] = {**prev["spawn"], "dots": prev["spawn"]["dots"] + [d for d in spawn["dots"]
                                                                             if d not in prev["spawn"]["dots"]]}
    mobs = list(merged.values())
    # surest drop first, then the mob with the most spawns
    mobs.sort(key=lambda m: (-(m["pct"] or 0), -sum(z[2] for z in m["zones"])))
    return {"genus": p["genus"], "name": p["name"], "mobs": mobs}


def main():
    only = set(sys.argv[sys.argv.index("--only") + 1:]) if "--only" in sys.argv else None
    listed = parse_list(get(BASE + "/en/aion-2/mounts"))
    print(len(listed), "pets")
    pets, cache = {}, {}
    for pid, p in listed.items():
        if only and pid not in only:
            continue
        time.sleep(1)
        try:
            pets[pid] = build_pet(p, cache)
        except Exception as e:
            print("  error", pid, e)
            pets[pid] = {"genus": p["genus"], "name": p["name"], "mobs": []}
        mobs = pets[pid]["mobs"]
        print(pid, p["name"], "|", ", ".join(f"{m['name']} ({'/'.join(z[1] for z in m['zones'][:1])})" for m in mobs)
              or "no mobs", flush=True)
    if only:
        print(json.dumps(pets, ensure_ascii=False)[:3000])
        return
    write(pets)


def write(pets):
    """One pet per line: spawn coordinates would otherwise take tens of thousands of lines."""
    lines = [f"{json.dumps(pid)}: {json.dumps(p, ensure_ascii=False)}" for pid, p in pets.items()]
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("{\n" + ",\n".join(lines) + "\n}\n")


if __name__ == "__main__":
    main()
