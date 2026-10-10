"""Self-update from GitHub releases.

check() asks the GitHub API for the latest release. install() downloads the new
exe, verifies it against the release's SHA256SUMS.txt, swaps it in place of the
running exe and starts it. Only the exe build can replace itself; when running
from source the caller should just open the release page.
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

from version import __version__

REPO = "MartinLVila/aion2-pet-overlay"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
EXE_NAME = "Aion2PetOverlay.exe"
SUMS_NAME = "SHA256SUMS.txt"
USER_AGENT = f"aion2-pet-overlay/{__version__}"


def parse_version(tag):
    """'v1.2.3' -> (1, 2, 3). Anything unparsable sorts as oldest."""
    try:
        return tuple(int(part) for part in tag.lstrip("vV").split("."))
    except ValueError:
        return ()


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check():
    """Returns a dict describing a newer release, or None if we're up to date."""
    release = json.loads(_get(API_LATEST))
    tag = release.get("tag_name", "")
    if parse_version(tag) <= parse_version(__version__):
        return None
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    return {"version": tag.lstrip("vV"), "page": release.get("html_url"),
            "exe_url": assets.get(EXE_NAME), "sums_url": assets.get(SUMS_NAME)}


def expected_hash(sums_text, name=EXE_NAME):
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    raise ValueError(f"{name} not listed in {SUMS_NAME}")


def download(update, dest, progress=None):
    """Downloads the new exe to `dest` and verifies its SHA256. Raises on mismatch."""
    if not update.get("exe_url") or not update.get("sums_url"):
        raise ValueError("release is missing the exe or its checksum")
    want = expected_hash(_get(update["sums_url"]).decode("utf-8", "replace"))
    req = urllib.request.Request(update["exe_url"], headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(256 * 1024):
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if sha.hexdigest() != want:
        os.remove(dest)
        raise ValueError("downloaded file failed the checksum")


def swap(current, new):
    """Puts `new` in place of `current`. Windows can't overwrite a running exe but
    can rename it, so the old one becomes `<name>.old` and is deleted next launch."""
    old = current + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(current, old)
    try:
        os.replace(new, current)
    except OSError:
        os.replace(old, current)  # put the original back
        raise


def restart(exe, *args):
    """Starts `exe` as a fresh, independent process (the caller should exit right after)."""
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")  # don't inherit our unpacked bundle
    subprocess.Popen([exe, *args], cwd=os.path.dirname(exe), env=env, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def install(update, progress=None):
    """Download, verify, swap and relaunch. Only valid for the frozen exe."""
    exe = sys.executable
    new = exe + ".new"
    download(update, new, progress)
    swap(exe, new)
    restart(exe)


def cleanup():
    """Removes the previous exe left behind by an update."""
    if getattr(sys, "frozen", False):
        try:
            os.remove(sys.executable + ".old")
        except OSError:
            pass
