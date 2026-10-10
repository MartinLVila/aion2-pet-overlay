# Development

## Run from source

Use this if you'd rather not run an unsigned exe, or if Smart App Control blocks it.

1. Install [Python](https://www.python.org/downloads/) 3.11 or newer (tick *"Add python.exe to PATH"*).
2. Download this repo (**Code → Download ZIP**) and extract it.
3. Open a terminal in that folder and run once:

   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

4. Start it with `start.bat`.

## How it works

`pet_protocol.py` listens to the game's TCP traffic through Npcap and decodes two server messages:

| Opcode | Sent when | Contains |
| --- | --- | --- |
| `0x0090` | You enter the world | Level and souls for every pet |
| `0x0D90` | You loot a soul | Pet ID and souls gained |

Messages arrive in LZ4-compressed bundles. The decoder rebuilds the TCP stream, unpacks them, and keeps
a running count between syncs. `pet_overlay.py` is the Tkinter UI.

Global servers cap pets at level 3 (5 + 25 + 75 = 105 souls). Korean and Taiwanese servers have more
levels and may use different packets, so they aren't supported.

## Pet data

`data/pets.json` holds each pet's name, genus, best mob, mob level and spawn zone, scraped from
[MetaBot.GG](https://metabot.gg/en/aion-2/mounts) (attribution required by their terms). After a
patch adds pets, regenerate it:

```
.venv\Scripts\python tools\build_pets.py
```

It fetches about one page per second, so it takes a few minutes.

## Tests and builds

- `.venv\Scripts\python selftest.py` checks the decoder, data and UI without the game.
- `build.ps1` builds `dist\Aion2PetOverlay.exe` with PyInstaller, then runs the same checks inside the exe
  (`Aion2PetOverlay.exe --selftest`).
- Pushing a `v*` tag makes GitHub Actions build, test and publish a release with `SHA256SUMS.txt`.

## Contributing

Bug reports and pull requests are welcome. Game patches can change the packet format, so if the overlay
stops syncing after an update, an issue with your `pet_overlay.log` helps the most.

## Credits

- Protocol research and original decoder: [elkaida/AION2-pet-tracker](https://github.com/elkaida/AION2-pet-tracker)
  (MIT). `pet_protocol.py` is adapted from it.
- Pet, monster and spawn data: [MetaBot.GG](https://metabot.gg/en/aion-2/mounts).
