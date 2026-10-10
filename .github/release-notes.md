### Download

Grab **`Aion2PetOverlay.exe`** below. It's a single file, so there's nothing to install. Put it in its own folder,
because it saves your progress next to itself.

You also need [Npcap](https://npcap.com/#download) (default options).

### First launch

The exe isn't code-signed, so Windows will be suspicious of it at first:

- **SmartScreen** ("Windows protected your PC"): click **More info → Run anyway**.
- **Smart App Control** ("This app has been blocked"): there's no way to allow a single app. Run the
  [Python version](https://github.com/MartinLVila/aion2-pet-overlay/blob/main/docs/DEVELOPMENT.md#run-from-source) instead.

This exe was built and tested by GitHub Actions straight from the source in this repo; see the
workflow run linked to this release. `SHA256SUMS.txt` lets you verify the download.

### Usage

Start the overlay, then **enter the world** with your character (or re-enter from character select)
so it can sync your pet progress. See the [README](https://github.com/MartinLVila/aion2-pet-overlay#readme)
for controls and troubleshooting.

Enjoying it? You can [support the project on PayPal](https://paypal.me/mytzuo), or say hi on Discord: **mytzuo**.

> Reads game traffic passively and never touches the game client, but NCSOFT hasn't approved it.
> Use at your own risk.
