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
a running count between syncs.

`pet_overlay.py` runs the app: it owns the tracker and the settings (`pet_overlay_ui.json`), and shows the
UI in `ui/` (HTML, CSS and JS) in WebView2 windows through [pywebview](https://pywebview.flowrl.com/).
The page calls Python through `window.pywebview.api` (the `Api` class) and Python pushes changes back
through `window.app`. There are two windows: the main one, either a borderless overlay or a normal
framed window, and the soul popup, which waits off screen and is moved into place without ever
taking focus from the game. The tray icon uses pystray.

`pet_map.py` renders the spawn map shown when you click a pet; its world-map tiles come from MetaBot.GG
on first use and are cached in `map_cache/`. `tools/make_icon.py` draws `assets/icon.ico` and `icon.png`.

Set `PET_OVERLAY_DEBUG=1` to open the WebView2 dev tools.

Global servers cap pets at level 3 (5 + 25 + 75 = 105 souls). Korean and Taiwanese servers have more
levels and may use different packets, so they aren't supported.

## Pet data

`data/pets.json` holds each pet's name, genus, best mob, mob level, spawn zone and spawn points, scraped from
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

## Releasing

1. Bump `__version__` in `version.py` and commit.
2. Tag and push: `git tag -a v1.2.0 -m v1.2.0 && git push origin v1.2.0`

CI refuses to publish if the tag doesn't match `version.py`. It also tests the self-update path:
the built exe swaps itself for a copy, relaunches, and the copy has to pass `--selftest`.

Running copies find the release through the GitHub API at startup and show an **Update** button.
Clicking it downloads the new exe, checks it against `SHA256SUMS.txt`, renames the running exe to
`.old` (deleted on the next launch), moves the new one in place and restarts. Users can turn the check
off with `"check_updates": false` in `pet_overlay_ui.json`.

## Contributing

Bug reports and pull requests are welcome. Game patches can change the packet format, so if the overlay
stops syncing after an update, an issue with your `pet_overlay.log` helps the most.

## Credits

- Protocol research and original decoder: [elkaida/AION2-pet-tracker](https://github.com/elkaida/AION2-pet-tracker)
  (MIT). `pet_protocol.py` is adapted from it.
- Pet, monster and spawn data: [MetaBot.GG](https://metabot.gg/en/aion-2/mounts).
