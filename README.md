# Aion 2 Pet Overlay

See which pets you still need for level 3, and how many souls are left, every time you loot one.

![Overlay screenshot](docs/screenshot.png)

- A popup on every soul: `Klaw +1 · 15 to Lv3`
- A list of every pet you haven't maxed, with the best mob to farm and where to find it
- Filter by genus or map, or search by name

Works on **Global** servers (EU/NA) on Windows 10 and 11.

## Get started

1. Install [Npcap](https://npcap.com/#download) with the default options. You probably already
   have it if you use a DPS meter.
2. Download **Aion2PetOverlay.exe** from the
   [latest release](https://github.com/MartinLVila/aion2-pet-overlay/releases/latest) and put it in
   its own folder.
3. Open it, then log in and enter the world with your character.
   Already in game? Go back to character select and enter again.

That's it. Your progress loads when you enter the world, and the overlay keeps count as you farm.

Play in **windowed** or **borderless** mode so the overlay can stay on top.

### "Windows protected your PC"?

The exe isn't signed, so Windows warns you the first time. Click **More info → Run anyway**.
If it says **"This app has been blocked"** (Smart App Control), you can
[run it with Python](docs/DEVELOPMENT.md#run-from-source) instead.

## Is it safe?

It only reads the data the game already sends to your PC, the same way DPS meters do. It never
touches the game, and it doesn't connect to the internet.

Still, NCSOFT hasn't approved it, and their rules ban unauthorized programs.
**Use it at your own risk.**

## Something's wrong?

| You see | Try this |
| --- | --- |
| `waiting for sync` | Go back to character select and enter the world again. |
| `game not detected` | Make sure the game is running. |
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
