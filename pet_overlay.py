"""Aion 2 overlay: which pets are still short of level 3, updated live as you farm.

Listens to game traffic through Npcap (read-only). On entering the world the
server sends the level and souls of every pet; after that each soul you pick up
is added on top.

    python pet_overlay.py

Start it BEFORE entering the world (or re-enter from character select).
Progress is saved between sessions. Drag the title bar to move, "–" collapses,
"x" closes, the corner grip resizes.
"""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

import pet_protocol as proto

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "data", "pets.json"), encoding="utf-8") as _f:
    PETS = {int(k): v for k, v in json.load(_f).items()}
UI_FILE = os.path.join(proto.APP_DIR, "pet_overlay_ui.json")

TOTAL = sum(proto.REQ)  # 105 souls from nothing to level 3
ALL_MAPS = "All maps"
GENUS_ORDER = ["Cogni", "Natura", "Fera", "Varian"]  # usual farming priority
GENUS_COLOR = {"Cogni": "#e8a33d", "Fera": "#6cc070", "Natura": "#58b4e8", "Varian": "#c27be0", "Special": "#999"}
BG, PANEL, FIELD, BAR = "#16181d", "#1d2027", "#22252c", "#0e0f12"
FG, DIM, ACCENT, DONE = "#e6e6e6", "#8a8f98", "#ffd166", "#6cc070"


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


class Overlay:
    def __init__(self, tracker=None):
        self.tracker = tracker or proto.Tracker()
        self.events = queue.Queue()
        self.capturing = False
        self.error = None
        self.flash = {}  # pet id -> refresh ticks left highlighted
        self.toast_win = self.toast_job = None
        self.collapsed = False
        self.ui = self.load_ui()

        root = self.root = tk.Tk()
        root.title("Pets Lv3")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.ui.get("alpha", 0.9))
        root.configure(bg=BG)
        root.geometry(self.ui.get("geom", "620x460+60+120"))
        self.style()

        # title bar (drag handle)
        bar = tk.Frame(root, bg=BAR)
        bar.pack(fill="x")
        self.title = tk.Label(bar, bg=BAR, fg=ACCENT, font=("Segoe UI", 9, "bold"), anchor="w")
        self.title.pack(side="left", padx=6, pady=3, fill="x", expand=True)
        for label, command in (("x", self.quit), ("–", self.toggle)):
            button = tk.Label(bar, text=label, bg=BAR, fg=DIM, font=("Segoe UI", 10, "bold"), padx=7, cursor="hand2")
            button.pack(side="right")
            button.bind("<Button-1>", lambda e, c=command: c())
        for widget in (bar, self.title):
            widget.bind("<ButtonPress-1>", self.drag_start)
            widget.bind("<B1-Motion>", self.drag_move)

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True)

        # what you're farming right now
        recent = tk.Frame(self.body, bg=PANEL)
        recent.pack(fill="x", padx=6, pady=4)
        self.recent_labels = [tk.Label(recent, bg=PANEL, fg=FG, anchor="w") for _ in range(3)]

        # filters
        filters = tk.Frame(self.body, bg=BG)
        filters.pack(fill="x", padx=6, pady=(0, 4))
        self.genus = {}
        for g in GENUS_ORDER:
            var = tk.BooleanVar(value=self.ui.get("genus", {}).get(g, True))
            self.genus[g] = var
            self.checkbox(filters, g, var, GENUS_COLOR[g], bold=True)
        self.no_mob = tk.BooleanVar(value=self.ui.get("no_mob", False))
        self.checkbox(filters, "chest/shop only", self.no_mob, DIM).pack_configure(padx=(6, 0))

        search_row = tk.Frame(self.body, bg=BG)
        search_row.pack(fill="x", padx=6, pady=(0, 4))
        maps = sorted({p["map"] for p in PETS.values() if p.get("map")})
        self.map = tk.StringVar(value=self.ui.get("map", ALL_MAPS) if self.ui.get("map") in maps else ALL_MAPS)
        combo = ttk.Combobox(search_row, textvariable=self.map, values=[ALL_MAPS] + maps, state="readonly", width=24)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.refresh())
        tk.Entry(search_row, textvariable=self.search, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=2)

        # pet list
        columns = (("pet", "Pet", 130, "w"), ("lv", "Lv", 36, "center"), ("left", "Left", 52, "center"),
                   ("mob", "Mob (level)", 170, "w"), ("zone", "Zone · Map", 200, "w"))
        self.tree = ttk.Treeview(self.body, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, heading, width, anchor in columns:
            self.tree.heading(key, text=heading, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=key in ("mob", "zone"))
        for g, color in GENUS_COLOR.items():
            self.tree.tag_configure(g, foreground=color)
        self.tree.tag_configure("flash", background="#3b3520")
        scroll = ttk.Scrollbar(self.body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, padx=(6, 0), pady=(0, 6))
        self.sort = self.ui.get("sort", "left")

        grip = tk.Label(root, text="◢", bg=BG, fg=DIM, cursor="size_nw_se")
        grip.place(relx=1, rely=1, anchor="se")
        grip.bind("<B1-Motion>", self.resize)

        self.refresh()
        root.after(300, self.pump)

    def style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("Treeview", background=BG, fieldbackground=BG, foreground=FG, rowheight=20, borderwidth=0,
                    font=("Segoe UI", 9))
        s.configure("Treeview.Heading", background=FIELD, foreground=DIM, borderwidth=0, font=("Segoe UI", 8, "bold"))
        s.map("Treeview", background=[("selected", "#2d3340")])
        s.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG)
        s.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])

    def checkbox(self, parent, text, var, color, bold=False):
        box = tk.Checkbutton(parent, text=text, variable=var, command=self.refresh, bg=BG, fg=color,
                             selectcolor=FIELD, activebackground=BG, activeforeground=color, bd=0,
                             font=("Segoe UI", 8, "bold" if bold else "normal"))
        box.pack(side="left")
        return box

    # ---------------------------------------------------------------- data

    def start_capture(self):
        threading.Thread(target=self.capture, daemon=True).start()

    def capture(self):
        if not proto.npcap_installed():
            self.events.put(("error", "Npcap missing: install it from npcap.com"))
            return
        try:
            proto.run_sniffer(self.events.put)
        except Exception as e:
            proto.log("sniffer:", e)
            self.events.put(("error", f"Capture failed ({e.__class__.__name__}); try running as administrator"))

    def pump(self):
        changed = False
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "conn":
                    self.capturing = ev[1]
                elif ev[0] == "error":
                    self.error = ev[1]
                else:
                    self.tracker.on_event(ev)
                    if ev[0] == "gain":
                        self.flash[ev[1]] = 8
                        self.toast(ev[1], ev[2])
                    changed = True
        except queue.Empty:
            pass
        if changed:
            self.tracker.save()
        for pid in list(self.flash):
            self.flash[pid] -= 1
            if self.flash[pid] <= 0:
                del self.flash[pid]
                changed = True
        if changed or self.flash:
            self.refresh()
        else:
            self.update_title()
        self.root.after(500, self.pump)

    def progress(self, pid):
        return self.tracker.levels.get(pid, 0), self.tracker.points.get(pid, 0)

    def pet_name(self, pid):
        pet = PETS.get(pid)
        return pet["name"] if pet and pet["name"] else f"Pet {pid}"

    def rows(self):
        query = self.search.get().strip().lower()
        wanted_map = self.map.get()
        rows = []
        for pid, pet in PETS.items():
            genus = pet["genus"]
            if genus not in self.genus or not self.genus[genus].get():
                continue
            if not pet.get("mob") and not self.no_mob.get():
                continue
            if wanted_map != ALL_MAPS and pet.get("map") != wanted_map:
                continue
            level, pts = self.progress(pid)
            left = remaining(level, pts)
            if not left:
                continue
            if pet.get("mob"):
                mob = f'{pet["mob"]} ({pet["lvl"]})' + (f' +{pet["more"]}' if pet.get("more") else "")
            else:
                mob = "chest / shop"
            zone = " · ".join(x for x in (pet.get("zone"), pet.get("map")) if x)
            name = self.pet_name(pid)
            if query and query not in f"{name} {mob} {zone}".lower():
                continue
            rows.append((pid, genus, name, level, left, mob, zone))
        key = {"pet": lambda r: r[2], "lv": lambda r: (-r[3], r[4]), "left": lambda r: r[4],
               "mob": lambda r: r[5], "zone": lambda r: (r[6] or "~", r[4])}[self.sort]
        return sorted(rows, key=key)

    # ---------------------------------------------------------------- UI

    def refresh(self):
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        for pid, genus, name, level, left, mob, zone in self.rows():
            tags = (genus, "flash") if pid in self.flash else (genus,)
            self.tree.insert("", "end", iid=str(pid), values=(name, level, left, mob, zone), tags=tags)
        self.tree.yview_moveto(top)
        self.update_recent()
        self.update_title()

    def update_recent(self):
        shown = [pid for pid in self.tracker.recent if pid in PETS][:3]
        for i, label in enumerate(self.recent_labels):
            if i >= len(shown):
                label.pack_forget()
                continue
            pid = shown[i]
            level, pts = self.progress(pid)
            label.config(text=f"{self.pet_name(pid)}  ·  Lv{level}  ·  {progress_text(level, pts)}",
                         fg=ACCENT if i == 0 else GENUS_COLOR.get(PETS[pid]["genus"], FG),
                         font=("Segoe UI", 10, "bold") if i == 0 else ("Segoe UI", 9))
            label.pack(fill="x", padx=6, pady=1)
        if not shown:
            self.recent_labels[0].config(text="Pick up a soul and I'll tell you how many are left", fg=DIM,
                                         font=("Segoe UI", 9))
            self.recent_labels[0].pack(fill="x", padx=6, pady=1)

    def update_title(self):
        farmable = [pid for pid, p in PETS.items() if p["genus"] != "Special" and p.get("mob")]
        done = sum(1 for pid in farmable if self.tracker.levels.get(pid, 0) >= proto.MAX_LEVEL)
        if self.error:
            status = "⚠ " + self.error
        elif not self.tracker.synced:
            status = "waiting for sync: enter the world with your character"
        else:
            status = f"synced {self.tracker.synced} · {'● capturing' if self.capturing else '○ game not detected'}"
        self.title.config(text=f"Pets Lv3  {done}/{len(farmable)}   ·   {status}")

    def toast(self, pid, amount):
        """Floating notice under the overlay, visible even when it's collapsed."""
        level, pts = self.progress(pid)
        if not self.toast_win:
            win = self.toast_win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.92)
            win.configure(bg=BAR)
            self.toast_label = tk.Label(win, bg=BAR, font=("Segoe UI", 13, "bold"), padx=12, pady=6)
            self.toast_label.pack()
        message = f"{self.pet_name(pid)} +{amount}   ·   {progress_text(level, pts)}"
        maxed = not remaining(level, pts)
        if maxed and self.tracker.extra.get(pid):
            message += f"  (+{self.tracker.extra[pid]} wasted, switch mobs)"
        self.toast_label.config(text=message, fg=DONE if maxed else ACCENT)
        self.toast_win.deiconify()
        x = self.root.winfo_x()
        y = self.root.winfo_y() + self.root.winfo_height() + 6
        self.toast_win.geometry(f"+{x}+{y}")
        if self.toast_job:
            self.root.after_cancel(self.toast_job)
        self.toast_job = self.root.after(5000, self.toast_win.withdraw)

    def sort_by(self, column):
        self.sort = column
        self.refresh()

    def toggle(self):
        if self.collapsed:
            self.body.pack(fill="both", expand=True)
            self.root.geometry(self.expanded_geom)
        else:
            self.expanded_geom = self.root.geometry()
            self.body.pack_forget()
            self.root.geometry(f"{self.root.winfo_width()}x24")
        self.collapsed = not self.collapsed

    def drag_start(self, e):
        self.drag_offset = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def drag_move(self, e):
        dx, dy = self.drag_offset
        self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def resize(self, e):
        width = max(380, e.x_root - self.root.winfo_x())
        height = max(150, e.y_root - self.root.winfo_y())
        self.root.geometry(f"{width}x{height}")

    def load_ui(self):
        try:
            with open(UI_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def quit(self):
        if self.collapsed:
            self.toggle()
        ui = {"geom": self.root.geometry(), "alpha": self.ui.get("alpha", 0.9), "sort": self.sort,
              "map": self.map.get(), "no_mob": self.no_mob.get(),
              "genus": {g: var.get() for g, var in self.genus.items()}}
        try:
            with open(UI_FILE, "w", encoding="utf-8") as f:
                json.dump(ui, f)
        except OSError:
            pass
        self.tracker.save()
        self.root.destroy()


if __name__ == "__main__":
    overlay = Overlay()
    overlay.start_capture()
    overlay.root.mainloop()
