"""Builds data/pets.json: genus, best soul mob, mob level and spawn zone for every pet.

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


def main():
    pets = parse_list(get(BASE + "/en/aion-2/mounts"))
    print(len(pets), "pets")
    for pid, p in pets.items():
        if p["mob_url"]:
            time.sleep(1)
            try:
                p["zone"], p["map"] = parse_mob(get(BASE + p["mob_url"]))
            except Exception as e:
                print("  error", pid, e)
                p["zone"] = p["map"] = None
            print(pid, p["name"], "|", p["mob"], "|", p.get("zone"), "/", p.get("map"), flush=True)
        p.pop("mob_url")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pets, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
