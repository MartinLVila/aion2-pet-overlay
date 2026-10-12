# Aion 2 Pet Overlay

See which pets you still need for level 3, and how many souls are left, every time you loot one.

![Overlay screenshot](docs/screenshot.png)

- A popup on every soul with the pet, the souls you got and how many are left to Lv3
- Every pet you haven't maxed, grouped by map, with the mob to farm on each map and its zone.
  A pet that drops on several maps shows up under each of them
- Filter by genus or map, or search by pet, mob or zone
- Click a pet to see every mob that drops it, with level, zones, spawn count and nearest Kibelisk,
  and a map of where each one spawns
- Use it as an overlay on top of the game or as a normal window, with its own taskbar and tray icon
- Settings for opacity, the popup, the tray and updates (gear icon)

Works on **Global** servers (EU/NA) on Windows 10 and 11. Windows 10 needs the
[WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/), which most PCs already have.

## Get started

1. Install [Npcap](https://npcap.com/#download) with the default options. You probably already
   have it if you use a DPS meter.
2. Download **Aion2PetOverlay.exe** from the
   [latest release](https://github.com/MartinLVila/aion2-pet-overlay/releases/latest) and put it in
   its own folder.
3. Open it, then log in and enter the world with your character.
   Already in game? Go back to character select and enter again.

That's it. Your progress loads when you enter the world, and the overlay keeps count as you farm.
When a new version is out, an **Update** button shows up in the title bar. One click and it updates itself.
Versions before 1.3.2 only check when they start, so if you don't see it, close and reopen the overlay.

Play in **windowed** or **borderless** mode so the overlay can stay on top. Prefer it outside the game?
Open the settings (gear icon) and switch to **Window**. Closing it keeps it running in the tray, still
counting souls. To bring it back, open the app again, click a soul popup or click the tray icon (Windows 11
may tuck it under the **^** arrow). Quit from the tray icon's menu. You can also drag the soul popup anywhere:
**Settings → Move the popup**.

### "Windows protected your PC"?

The exe isn't signed, so Windows warns you the first time. Click **More info → Run anyway**.
If it says **"This app has been blocked"** (Smart App Control), you can
[run it with Python](docs/DEVELOPMENT.md#run-from-source) instead.

## Is it safe?

It only reads the data the game already sends to your PC, the same way DPS meters do. It never
touches the game. It connects to GitHub to check for updates (at startup and every 3 hours) and to
MetaBot.GG for map images the first time you open a pet's map. Updates are verified against a checksum
before they're installed.

Still, NCSOFT hasn't approved it, and their rules ban unauthorized programs.
**Use it at your own risk.**

## Something's wrong?

| You see | Try this |
| --- | --- |
| `Waiting for sync` | Go back to character select and enter the world again. |
| `Game not detected` | Make sure the game is running. |
| A message about WebView2 | Install the [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (Evergreen), then reopen the overlay. |
| `Npcap missing` | Install [Npcap](https://npcap.com/#download), then reopen the overlay. |
| `Capture failed` | Right-click the exe and choose **Run as administrator**. |
| Numbers don't match the game | Re-enter the world. The game is always right. |

Still stuck? [Open an issue](https://github.com/MartinLVila/aion2-pet-overlay/issues) and attach
`pet_overlay.log` from the overlay's folder.

## Support

Like it? You can [buy me a coffee on PayPal](https://paypal.me/mytzuo). Thanks!
Questions or ideas: **mytzuo** on Discord.

---

Unofficial fan project, not affiliated with NCSOFT. AION is a trademark of NCSOFT Corporation.
Pet and spawn data from [MetaBot.GG](https://metabot.gg/en/aion-2/mounts). Packet decoding based on
[elkaida/AION2-pet-tracker](https://github.com/elkaida/AION2-pet-tracker).
Developers: see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). [MIT License](LICENSE).
