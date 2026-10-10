# Aion 2 pet overlay

Always-on-top overlay that lists the pets still short of level 3 and tells you,
on every soul you pick up, how many are left.

- **Toast** under the overlay on each soul: `Klaw +1 · 15 to Lv3 (4 to Lv2)`.
- **Recent panel** with the last 3 pets you farmed.
- **List** of every unfinished pet: souls left, best mob (and how many other mobs drop it), zone and map.
  Filter by genus, map or text; click a column header to sort.

## Run

Windows 10/11 with Python 3.11+.

1. Install [Npcap](https://npcap.com/#download) (defaults are fine).
2. Set up the environment once:
   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
3. Double-click `start.bat` **before** entering the world, or re-enter from character select
   so the server sends your progress. Run the game in windowed or borderless mode.

Progress is kept in `pet_state.json`, window settings in `pet_overlay_ui.json`.

## How it works

`pet_protocol.py` passively captures the game's TCP traffic (Npcap + scapy) and decodes two
opcodes: `0x0090` (full pet state on world entry) and `0x0D90` (souls per kill). Nothing is
sent to the game. Protocol and decoder adapted from
[elkaida/AION2-pet-tracker](https://github.com/elkaida/AION2-pet-tracker) (MIT, see `LICENSE`).

Pet genus, mob, level and zone come from [metabot.gg](https://metabot.gg/en/aion-2/mounts);
refresh them after a patch with `.venv\Scripts\python tools\build_pets.py`.
`tools\selftest.py` checks the decoder offline.

Reading game traffic may break NCSOFT's terms of service. Use at your own risk.
