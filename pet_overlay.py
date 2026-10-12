"""Aion 2 overlay: which pets are still short of level 3, updated live as you farm.

Listens to game traffic through Npcap (read-only). On entering the world the
server sends the level and souls of every pet; after that each soul you pick up
is added on top.

    python pet_overlay.py

Start it BEFORE entering the world (or re-enter from character select).
The UI is HTML (ui/) in a WebView2 window: either a borderless overlay over the
game or a normal window, chosen in Settings. Click a pet to see where its mob
spawns. Progress and settings are saved between sessions.
"""
import base64
import copy
import ctypes
import io
import json
import os
import queue
import sys
import threading
import webbrowser

import pet_map
import pet_protocol as proto
import updater
from version import __version__

with open(os.path.join(proto.RES_DIR, "data", "pets.json"), encoding="utf-8") as _f:
    PETS = {int(k): v for k, v in json.load(_f).items()}
UI_FILE = os.path.join(proto.APP_DIR, "pet_overlay_ui.json")
UI_DIR = os.path.join(proto.RES_DIR, "ui")
ICON_ICO = os.path.join(proto.RES_DIR, "assets", "icon.ico")
ICON_PNG = os.path.join(proto.RES_DIR, "assets", "icon.png")
APP_ID = "MartinLVila.Aion2PetOverlay"
TITLE = "Aion 2 Pet Overlay"

TOTAL = sum(proto.REQ)  # 105 souls from nothing to level 3
GENERA = ["Cogni", "Natura", "Fera", "Varian"]
SURFACE = "#121821"
MAP_SIZE = (768, 432)  # twice the panel size, sharp on high-DPI screens
OFF_SCREEN = -20000     # where the popup waits between souls

DEFAULTS = {
    "mode": "overlay",        # "overlay" (borderless, over the game) or "window" (normal window)
    "opacity": 92,            # overlay background, percent
    "on_top": False,          # window mode only; the overlay is always on top
    "toast": True,
    "toast_pos": "top",       # "top" of the screen or "under" the overlay
    "toast_time": 5,
    "tray": True,
    "close_to_tray": True,
    "check_updates": True,
    "genus": {g: True for g in GENERA},
    "no_mob": False,
    "map": "",
    "geometry": {"overlay": [60, 120, 900, 560], "window": [None, None, 1040, 680]},  # x, y, width, height
}
CHOICES = {"mode": ("overlay", "window"), "toast_pos": ("top", "under"), "toast_time": (3, 5, 8)}
FLAGS = ("on_top", "toast", "tray", "close_to_tray", "check_updates", "no_mob")


def remaining(level, pts):
    """Souls still needed to reach level 3."""
    return TOTAL - sum(proto.REQ[:level]) - pts if level < proto.MAX_LEVEL else 0


def progress_text(level, pts):
    """'12 to Lv3 (2 to Lv2)' or 'Lv3 done'."""
    left = remaining(level, pts)
    if not left:
        return "Lv3 done ✔"
    text = f"{left} to Lv3"
    if level + 1 < proto.MAX_LEVEL:
        text += f"  ({proto.REQ[level] - pts} to Lv{level + 1})"
    return text


# ---------------------------------------------------------------- settings

def clean_settings(raw, base=None):
    """Merges `raw` into `base` (defaults if None), dropping unknown keys and bad values."""
    s = copy.deepcopy(base or DEFAULTS)
    for key, allowed in CHOICES.items():
        if raw.get(key) in allowed:
            s[key] = raw[key]
    for key in FLAGS:
        if isinstance(raw.get(key), bool):
            s[key] = raw[key]
    if isinstance(raw.get("opacity"), (int, float)):
        s["opacity"] = max(50, min(100, int(raw["opacity"])))
    if isinstance(raw.get("map"), str):
        s["map"] = "" if raw["map"] == "All maps" else raw["map"]
    if isinstance(raw.get("genus"), dict):
        s["genus"] = {g: bool(raw["genus"].get(g, s["genus"][g])) for g in GENERA}
    geometry = raw.get("geometry")
    if isinstance(geometry, dict):
        for mode in CHOICES["mode"]:
            g = geometry.get(mode)
            if isinstance(g, list) and len(g) == 4 and all(v is None or isinstance(v, int) for v in g):
                s["geometry"][mode] = g
    return s


def load_settings(path=UI_FILE):
    """Saved settings over the defaults. Also reads v1's Tk format ("geom": "WxH+X+Y", "alpha": 0.9)."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    s = clean_settings(raw)
    geom = raw.get("geom")
    if isinstance(geom, str) and "geometry" not in raw:
        try:
            size, x, y = geom.split("+")
            w, h = size.split("x")
            s["geometry"]["overlay"] = [int(x), int(y), int(w), int(h)]
        except ValueError:
            pass
    if isinstance(raw.get("alpha"), (int, float)) and "opacity" not in raw:
        s["opacity"] = max(50, min(100, round(raw["alpha"] * 100)))
    return s


def ui_pets():
    """Pet data for the page: everything but the map tiles, which stay on this side."""
    out = {}
    for pid, p in PETS.items():
        spawn = p.get("spawn")
        out[pid] = {k: p.get(k) for k in ("genus", "name", "mob", "more", "lvl", "zone", "map")}
        out[pid]["spawn"] = {"dots": spawn["dots"], "link": spawn.get("link")} if spawn and spawn["dots"] else None
    return out


# ---------------------------------------------------------------- bridge

class Api:
    """Methods the page calls as window.pywebview.api.<name>(...). Names starting with _ stay private."""

    def __init__(self, app):
        self._app = app

    def init(self):
        return self._app.ui_payload()

    def ready(self):
        self._app.on_ready()

    def save_settings(self, changes):
        return self._app.update_settings(changes if isinstance(changes, dict) else {})

    def get_map(self, pid):
        return self._app.map_uri(int(pid))

    def open_url(self, url):
        if isinstance(url, str) and url.startswith("https://"):
            webbrowser.open(url)

    def close(self):
        self._app.close_main()

    def set_collapsed(self, collapsed, bar_height):
        self._app.set_collapsed(bool(collapsed), int(bar_height))

    def resize(self, width, height):
        if self._app.window:
            self._app.window.resize(int(width), int(height))

    def start_update(self):
        self._app.start_update()


# ---------------------------------------------------------------- app

class App:
    def __init__(self, tracker=None, settings_path=UI_FILE, selftest=False):
        self.tracker = tracker or proto.Tracker()
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.events = queue.Queue()
        self.api = Api(self)
        self.window = self.toast = self.tray = None
        self.capturing = False
        self.error = None
        self.update_info = None
        self.update_status = None   # None, "available", "downloading", "failed"
        self.update_progress = 0.0
        self.hidden = False         # main window hidden to the tray
        self.collapsed = False
        self.expanded_height = None
        self.quitting = False
        self.selftest = selftest
        self.ready_seen = threading.Event()
        self.maps = {}              # pet id -> data URI
        self.toast_timer = None
        self.lock = threading.RLock()

    # ---------------------------------------------------------- data for the page

    def state_payload(self):
        t = self.tracker
        return {"levels": t.levels, "points": t.points, "extra": t.extra, "recent": t.recent,
                "synced": t.synced, "capturing": self.capturing, "error": self.error}

    def update_payload(self):
        if not self.update_status:
            return None
        return {"status": self.update_status, "version": self.update_info["version"], "progress": self.update_progress}

    def ui_payload(self):
        return {"version": __version__, "pets": ui_pets(), "state": self.state_payload(),
                "settings": self.settings, "update": self.update_payload()}

    def map_uri(self, pid):
        spawn = (PETS.get(pid) or {}).get("spawn")
        if not spawn or not spawn["dots"]:
            return None
        if pid not in self.maps:
            try:
                img = pet_map.render(spawn, size=MAP_SIZE, dots=False)
            except Exception as e:
                proto.log("map:", e)
                return None
            buf = io.BytesIO()
            img.save(buf, "WEBP", quality=80)
            self.maps[pid] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
        return self.maps[pid]

    def push(self, script):
        win = self.window
        if win is None or self.quitting:
            return
        try:
            win.evaluate_js(script)
        except Exception as e:
            proto.log("ui:", e)

    def push_state(self):
        self.push(f"window.app && app.setState({json.dumps(self.state_payload())})")
        self.update_tray_title()

    def push_update(self):
        self.push(f"window.app && app.setUpdate({json.dumps(self.update_payload())})")

    # ---------------------------------------------------------- events from capture and updater

    def handle(self, batch):
        """Applies a batch of events, then refreshes the page once."""
        changed = state_changed = False
        gains = []
        for ev in batch:
            kind = ev[0]
            if kind == "conn":
                state_changed |= self.capturing != ev[1]
                self.capturing = ev[1]
            elif kind == "error":
                self.error, state_changed = ev[1], True
            elif kind == "update":
                self.update_info, self.update_status = ev[1], "available"
                self.push_update()
            elif kind == "update_progress":
                self.update_status, self.update_progress = "downloading", ev[1]
                self.push_update()
            elif kind == "update_error":
                self.update_status = "failed"
                self.push_update()
            elif kind == "update_ready":
                self.quit()
                updater.restart(sys.executable)
                return
            else:
                self.tracker.on_event(ev)
                changed = True
                if kind == "gain":
                    gains.append((ev[1], ev[2]))
        if changed:
            self.tracker.save()
        for pid, _ in gains:
            self.push(f"window.app && app.flash({int(pid)})")
        if changed or state_changed:
            self.push_state()
        if gains:
            self.show_toast(*gains[-1])

    def pump(self):
        while not self.quitting:
            try:
                batch = [self.events.get(timeout=0.5)]
            except queue.Empty:
                continue
            while True:
                try:
                    batch.append(self.events.get_nowait())
                except queue.Empty:
                    break
            try:
                self.handle(batch)
            except Exception as e:
                proto.log("events:", e)

    def capture(self):
        if not proto.npcap_installed():
            self.events.put(("error", "Npcap missing: install it from npcap.com"))
            return
        try:
            proto.run_sniffer(self.events.put)
        except Exception as e:
            proto.log("sniffer:", e)
            self.events.put(("error", f"Capture failed ({e.__class__.__name__}); try running as administrator"))

    def check_for_update(self):
        if not self.settings["check_updates"]:
            return
        try:
            info = updater.check()
        except Exception as e:
            proto.log("update check:", e)
            return
        if info:
            self.events.put(("update", info))

    def start_update(self):
        info = self.update_info
        if not info or self.update_status == "downloading":
            return
        if not proto.FROZEN or not info.get("exe_url") or self.update_status == "failed":
            webbrowser.open(info["page"])  # running from source, or the download failed: let the user grab it
            return
        self.update_status = "downloading"
        self.push_update()

        def worker():
            new = sys.executable + ".new"
            try:
                updater.download(info, new, lambda f: self.events.put(("update_progress", f)))
                updater.swap(sys.executable, new)
            except Exception as e:
                proto.log("update failed:", e)
                self.events.put(("update_error", str(e)))
                return
            self.events.put(("update_ready",))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------- soul popup

    def show_toast(self, pid, amount):
        if not self.settings["toast"] or self.toast is None or self.quitting:
            return
        pet = PETS.get(pid) or {}
        level, pts = self.tracker.levels.get(pid, 0), self.tracker.points.get(pid, 0)
        data = {"name": pet.get("name") or f"Pet {pid}", "genus": pet.get("genus"), "amount": amount,
                "level": level, "points": pts, "extra": self.tracker.extra.get(pid, 0)}
        try:
            size = self.toast.evaluate_js(f"showToast({json.dumps(data)})") or {}
            w, h = int(size.get("width", 480)), int(size.get("height", 44))
            x, y = self.toast_position(w)
            place_without_focus(self.toast, x, y, w, h)  # never take focus away from the game
        except Exception as e:
            proto.log("toast:", e)
            return
        if self.toast_timer:
            self.toast_timer.cancel()
        self.toast_timer = threading.Timer(self.settings["toast_time"], self.hide_toast)
        self.toast_timer.daemon = True
        self.toast_timer.start()

    def toast_position(self, width):
        win = self.window
        if (self.settings["toast_pos"] == "under" and self.settings["mode"] == "overlay"
                and win is not None and not self.hidden):
            return win.x, win.y + win.height + 6
        import webview
        screen = webview.screens[0]
        return screen.x + (screen.width - width) // 2, screen.y + 16

    def hide_toast(self):
        if self.toast is not None and not self.quitting:
            try:
                place_without_focus(self.toast, OFF_SCREEN, OFF_SCREEN, 60, 20)
            except Exception as e:
                proto.log("toast:", e)

    # ---------------------------------------------------------- windows

    def create_main(self):
        import webview
        mode = self.settings["mode"]
        overlay = mode == "overlay"
        x, y, w, h = self.settings["geometry"][mode]
        win = webview.create_window(
            TITLE, os.path.join(UI_DIR, "index.html"), js_api=self.api,
            width=w, height=h, x=x, y=y, min_size=(420, 40) if overlay else (480, 320),
            frameless=overlay, easy_drag=False, shadow=not overlay,
            on_top=overlay or self.settings["on_top"], background_color=SURFACE)
        win.events.closing += self.on_closing
        if overlay:
            def on_shown():
                # pywebview applies the size before removing the frame, and Windows keeps the client area,
                # so the window comes out 16x39 px smaller than asked: set it again once it's up
                win.resize(w, h)
                round_corners(win)
                set_opacity(win, self.settings["opacity"])
            win.events.shown += on_shown
        else:
            win.events.shown += lambda: dark_title_bar(win)
        self.window = win
        self.hidden = self.collapsed = False
        return win

    def on_closing(self, window):
        """Returning False cancels the close."""
        if self.quitting or window is not self.window:
            return True  # quitting, or an old window being replaced after a mode switch
        if self.settings["tray"] and self.settings["close_to_tray"]:
            self.hide_main()
        else:
            threading.Thread(target=self.quit, daemon=True).start()
        return False

    def close_main(self):
        if self.settings["tray"] and self.settings["close_to_tray"]:
            self.hide_main()
        else:
            self.quit()

    def hide_main(self):
        self.remember_geometry()
        self.save_settings()
        self.hidden = True
        self.window.hide()

    def show_main(self):
        if self.quitting or self.window is None:
            return
        self.hidden = False
        self.window.show()
        self.window.restore()

    def switch_mode(self):
        with self.lock:
            old = self.window
            self.create_main()
            if old is not None:
                old.destroy()

    def set_collapsed(self, collapsed, bar_height):
        win = self.window
        if win is None or self.settings["mode"] != "overlay" or collapsed == self.collapsed:
            return
        if collapsed:
            self.expanded_height = win.height
            win.resize(win.width, bar_height)
        else:
            win.resize(win.width, self.expanded_height or self.settings["geometry"]["overlay"][3])
        self.collapsed = collapsed

    def remember_geometry(self):
        win = self.window
        if win is None or self.hidden:
            return
        try:
            x, y, w, h = win.x, win.y, win.width, win.height
        except Exception:
            return
        if x < -10000 or y < -10000:  # minimized
            return
        if self.collapsed:
            h = self.expanded_height or h
        self.settings["geometry"][self.settings["mode"]] = [x, y, w, h]

    # ---------------------------------------------------------- settings

    def update_settings(self, changes):
        changes = {k: v for k, v in changes.items() if k != "geometry"}
        self.remember_geometry()
        old = self.settings
        self.settings = clean_settings(changes, old)
        self.save_settings()
        new = self.settings
        if new["mode"] != old["mode"]:
            # after this call returns to the page that asked, since that page is about to go away
            threading.Timer(0.05, self.switch_mode).start()
        elif new["mode"] == "window" and new["on_top"] != old["on_top"] and self.window:
            self.window.on_top = new["on_top"]
        elif new["mode"] == "overlay" and new["opacity"] != old["opacity"] and self.window:
            set_opacity(self.window, new["opacity"])
        if new["tray"] != old["tray"]:
            if new["tray"]:
                self.start_tray()
            else:
                self.stop_tray()
                if self.hidden:
                    self.show_main()
        return self.settings

    def save_settings(self):
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=1)
        except OSError as e:
            proto.log("settings:", e)

    # ---------------------------------------------------------- tray

    def start_tray(self):
        if self.tray or self.selftest:
            return
        try:
            import pystray
            from PIL import Image
            menu = pystray.Menu(pystray.MenuItem("Show", lambda: self.show_main(), default=True),
                                pystray.MenuItem("Quit", lambda: self.quit()))
            self.tray = pystray.Icon("Aion2PetOverlay", Image.open(ICON_PNG), TITLE, menu)
            self.tray.run_detached()
            self.update_tray_title()
        except Exception as e:
            proto.log("tray:", e)
            self.tray = None

    def stop_tray(self):
        tray, self.tray = self.tray, None
        if tray:
            try:
                tray.stop()
            except Exception as e:
                proto.log("tray:", e)

    def update_tray_title(self):
        if not self.tray:
            return
        farmable = [pid for pid, p in PETS.items() if p["genus"] != "Special" and p.get("mob")]
        done = sum(1 for pid in farmable if self.tracker.levels.get(pid, 0) >= proto.MAX_LEVEL)
        try:
            self.tray.title = f"{TITLE}: {done} of {len(farmable)} pets at Lv3"
        except Exception:
            pass

    # ---------------------------------------------------------- lifecycle

    def on_ready(self):
        self.ready_seen.set()
        if self.selftest:
            threading.Timer(1.0, self.quit).start()

    def quit(self):
        with self.lock:
            if self.quitting:
                return
            self.remember_geometry()
            self.quitting = True
        self.save_settings()
        self.tracker.save()
        self.stop_tray()
        if self.toast_timer:
            self.toast_timer.cancel()
        for win in (self.window, self.toast):
            if win is not None:
                try:
                    win.destroy()
                except Exception as e:
                    proto.log("close:", e)

    def background(self):
        """Runs once the GUI loop is up."""
        if self.toast.events.loaded.wait(20):
            style_toast(self.toast)
            round_corners(self.toast)
        if self.settings["tray"]:
            self.start_tray()
        if not self.selftest:
            threading.Thread(target=self.capture, daemon=True).start()
            threading.Thread(target=self.check_for_update, daemon=True).start()
        else:
            def watchdog():  # the page must call ready() or the selftest fails
                if not self.ready_seen.wait(60):
                    proto.log("selftest: the page never loaded")
                    self.quit()
            threading.Thread(target=watchdog, daemon=True).start()
        self.pump()

    def run(self):
        import webview
        # The popup window is created first: pywebview keeps running while any window is open, so the
        # main window can be replaced (mode switch) without the app exiting. It stays "shown" but parked
        # off screen, because WebView2 stops drawing in a hidden window.
        self.toast = webview.create_window(
            "Soul pickup", os.path.join(UI_DIR, "toast.html"), width=480, height=44, x=OFF_SCREEN, y=OFF_SCREEN,
            min_size=(60, 20), frameless=True, easy_drag=False, on_top=True, focus=False,
            shadow=False, resizable=False, background_color=SURFACE)
        self.create_main()
        webview.start(self.background, gui="edgechromium", icon=ICON_ICO,
                      debug=bool(os.environ.get("PET_OVERLAY_DEBUG")))


# ---------------------------------------------------------------- Windows helpers

def hwnd_of(win):
    return win.native.Handle.ToInt64()


def place_without_focus(win, x, y, width, height):
    """Shows `win` topmost at x, y (logical px) sized width x height, without activating it.
    pywebview's own move/resize/show all activate the window, which would pull focus out of the game."""
    hwnd = ctypes.c_void_p(hwnd_of(win))
    scale = ctypes.windll.user32.GetDpiForWindow(hwnd) / 96 or 1
    HWND_TOPMOST, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x10, 0x40
    ctypes.windll.user32.SetWindowPos(hwnd, ctypes.c_void_p(HWND_TOPMOST), int(x * scale), int(y * scale),
                                      int(width * scale), int(height * scale), SWP_NOACTIVATE | SWP_SHOWWINDOW)


def round_corners(win):
    """Windows 11 rounds a borderless window's corners and draws its border in the app's line color.
    (CSS can't: pywebview's transparent windows show grey where the page is see-through.)"""
    try:
        hwnd = ctypes.c_void_p(hwnd_of(win))
        DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, ctypes.c_int(2)
        DWMWA_BORDER_COLOR, line = 34, ctypes.c_uint(0x00453328)  # COLORREF 0x00BBGGRR of #283345
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                                   ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(line), ctypes.sizeof(line))
    except Exception as e:
        proto.log("corners:", e)


def set_opacity(win, percent):
    """Whole-window opacity, like v1's Tk overlay. WebView2 keeps drawing in a layered window."""
    try:
        from System import Func, Type
        form = win.native

        def apply():
            form.Opacity = max(50, min(100, percent)) / 100
        form.Invoke(Func[Type](apply))
    except Exception as e:
        proto.log("opacity:", e)


def style_toast(win):
    """No taskbar button or Alt-Tab entry for the popup, and rounded corners on Windows 11."""
    try:
        hwnd = ctypes.c_void_p(hwnd_of(win))
        GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = -20, 0x80, 0x40000, 0x8000000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception as e:
        proto.log("toast style:", e)


def dark_title_bar(win):
    """Dark native title bar in window mode (Windows 10 2004+ / 11)."""
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd_of(win)), DWMWA_USE_IMMERSIVE_DARK_MODE,
                                                   ctypes.byref(on), ctypes.sizeof(on))
    except Exception as e:
        proto.log("title bar:", e)


def webview2_available():
    from webview.platforms import winforms
    return winforms.is_chromium


def message_box(text, title=TITLE):
    MB_ICONWARNING = 0x30
    ctypes.windll.user32.MessageBoxW(None, text, title, MB_ICONWARNING)


# ---------------------------------------------------------------- entry points

def run_selftest():
    """`--selftest`: offline checks, also used by CI against the built exe."""
    import traceback

    import selftest
    try:
        selftest.main()
    except BaseException:
        proto.log("selftest failed:\n" + traceback.format_exc())
        sys.exit(1)
    proto.log("selftest passed")
    sys.exit(0)


def run_swap_test():
    """`--selftest-update` (CI only): swap the running exe for a copy of itself and
    relaunch it with --selftest, exercising the real self-update path."""
    import shutil
    new = sys.executable + ".new"
    shutil.copyfile(sys.executable, new)
    updater.swap(sys.executable, new)
    updater.restart(sys.executable, "--selftest")
    proto.log("swap test: relaunched")
    sys.exit(0)


def main():
    if "--selftest" in sys.argv:
        run_selftest()
    if "--selftest-update" in sys.argv:
        run_swap_test()
    updater.cleanup()
    proto.log(f"started v{__version__}")
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # own taskbar button and icon
    except Exception:
        pass
    if not webview2_available():
        proto.log("WebView2 runtime missing")
        message_box("This app needs the Microsoft Edge WebView2 Runtime, which is missing on this PC.\n\n"
                    "Your browser will open the download page. Install the Evergreen runtime, then start the app again.")
        webbrowser.open("https://developer.microsoft.com/microsoft-edge/webview2/")
        sys.exit(1)
    App().run()


if __name__ == "__main__":
    main()
