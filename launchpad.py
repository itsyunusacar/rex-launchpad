#!/usr/bin/env python3
"""rex-launchpad panel: lists the folders in your projects directory, opens them
as Rex sessions and creates new ones. launchpad.lua runs it in a floating pane.

Usage: launchpad.py [ROOT] [en|tr]
"""
import curses
import json
import locale
import os
import subprocess
import sys
import time

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Projects")
LANG = sys.argv[2] if len(sys.argv) > 2 else "en"

STRINGS = {
    "en": {
        "title": "Projects", "search": "search, or type a new name", "open": "Open", "recent": "Recent",
        "new": "new project", "empty": "No projects yet. Type a name and press Enter.",
        "keys": (("↵", "open"), ("⌃N", "new"), ("⌃F", "Finder"), ("esc", "close")),
        "need_name": "Type the new project's name first, then ⌃N",
        "remote": "Turn on Remote Control in Rex Settings → Rex Server, then try again",
        "failed": "couldn't open", "bad_name": "invalid name", "exists": "a folder with that name already exists",
        "now": "now", "min": "{}m", "hour": "{}h", "yesterday": "1d", "day": "{}d", "week": "{}w", "month": "{}mo",
    },
    "tr": {
        "title": "Projeler", "search": "ara ya da yeni bir ad yaz", "open": "Açık", "recent": "Son",
        "new": "yeni proje", "empty": "Henüz proje yok. Bir ad yaz ve Enter'a bas.",
        "keys": (("↵", "aç"), ("⌃N", "yeni"), ("⌃F", "Finder"), ("esc", "kapat")),
        "need_name": "Önce yeni projenin adını yaz, sonra ⌃N",
        "remote": "Rex Ayarlar → Rex Server → Remote Control'ü aç, sonra tekrar dene",
        "failed": "açılamadı", "bad_name": "geçersiz ad", "exists": "bu adla bir klasör zaten var",
        "now": "az önce", "min": "{} dk", "hour": "{} sa", "yesterday": "dün", "day": "{} gün", "week": "{} hf", "month": "{} ay",
    },
}
T = STRINGS.get(LANG, STRINGS["en"])
os.environ.setdefault("ESCDELAY", "25")
locale.setlocale(locale.LC_ALL, "")


def rex(*args):
    return subprocess.run(["rex", *args], capture_output=True, text=True, timeout=15)


def open_sessions():
    try:
        r = rex("api", "call", "session.list", "{}")
        return {s["label"] for s in json.loads(r.stdout).get("sessions") or []}
    except Exception:
        return set()


def git_branch(path):
    try:
        with open(os.path.join(path, ".git", "HEAD")) as f:
            head = f.read().strip()
        return head.rsplit("/", 1)[-1] if head.startswith("ref:") else head[:7]
    except OSError:
        return ""


def last_touch(path):
    t = os.path.getmtime(path)
    for name in (".git/index", ".git/HEAD", ".git/FETCH_HEAD"):
        try:
            t = max(t, os.path.getmtime(os.path.join(path, name)))
        except OSError:
            pass
    return t


def ago(t):
    s = time.time() - t
    if s < 3600:
        return T["now"] if s < 120 else T["min"].format(int(s // 60))
    if s < 86400:
        return T["hour"].format(int(s // 3600))
    d = int(s // 86400)
    if d == 1:
        return T["yesterday"]
    if d < 14:
        return T["day"].format(d)
    if d < 60:
        return T["week"].format(d // 7)
    return T["month"].format(d // 30)


def load_projects(opened):
    items = []
    for name in os.listdir(ROOT):
        p = os.path.join(ROOT, name)
        if name.startswith(".") or not os.path.isdir(p):
            continue
        items.append({"name": name, "branch": git_branch(p), "t": last_touch(p),
                      "open": name in opened})
    items.sort(key=lambda x: -x["t"])
    return items


def matches(query, name):
    """Fuzzy match: letters in order, so 'wsm' finds 'web-site-mac'."""
    q, i = query.lower(), 0
    for ch in name.lower():
        if i < len(q) and ch == q[i]:
            i += 1
    return i == len(q)


def open_project(name):
    r = rex("do", "launchpad_open", f"name={name}")
    if r.returncode != 0:
        out = r.stderr + r.stdout
        if "Remote Control" in out:
            return T["remote"]
        msg = out.strip().splitlines()
        return msg[-1] if msg else T["failed"]
    return None


def create_project(name):
    name = name.strip()
    if not name or "/" in name or name.startswith("."):
        return T["bad_name"]
    p = os.path.join(ROOT, name)
    if os.path.exists(p):
        return T["exists"]
    os.makedirs(p)
    subprocess.run(["git", "init", "-q"], cwd=p)
    return open_project(name)


class UI:
    def __init__(self, scr):
        self.scr = scr
        curses.curs_set(1)
        curses.use_default_colors()
        rich = curses.COLORS >= 256
        curses.init_pair(1, curses.COLOR_GREEN, -1)                  # open ●
        curses.init_pair(2, 75 if rich else curses.COLOR_CYAN, -1)   # vurgu
        curses.init_pair(3, 244 if rich else -1, -1)                 # soluk metin
        curses.init_pair(4, -1, 236 if rich else curses.COLOR_BLUE)  # selected row
        curses.init_pair(5, 75 if rich else curses.COLOR_CYAN, 236 if rich else curses.COLOR_BLUE)
        curses.init_pair(6, 244 if rich else -1, 236 if rich else curses.COLOR_BLUE)
        curses.init_pair(7, curses.COLOR_GREEN, 236 if rich else curses.COLOR_BLUE)
        self.green, self.accent = curses.color_pair(1), curses.color_pair(2)
        self.dim = curses.color_pair(3) if rich else curses.A_DIM
        self.sel_bg, self.sel_accent = curses.color_pair(4), curses.color_pair(5)
        self.sel_dim, self.sel_green = curses.color_pair(6), curses.color_pair(7)

    def put(self, y, x, text, attr=0, maxw=None):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w - 1:
            return
        n = (w - 1 - x) if maxw is None else min(maxw, w - 1 - x)
        if n > 0:
            try:
                self.scr.addnstr(y, x, text, n, attr)
            except curses.error:
                pass


def main(scr):
    ui = UI(scr)
    put = ui.put
    opened = open_sessions()
    projects = load_projects(opened)
    query, sel, status = "", 0, ""
    last_scan = time.time()
    scr.timeout(1000)  # rescan so folders made in Finder show up

    while True:
        if time.time() - last_scan > 2:
            projects, last_scan = load_projects(opened), time.time()

        q = query.strip()
        shown = [p for p in projects if matches(q, p["name"])]
        exact = any(p["name"].lower() == q.lower() for p in projects)
        has_open = any(p["open"] for p in shown)
        groups = [(T["open"], [p for p in shown if p["open"]]),
                  (T["recent"] if has_open else "", [p for p in shown if not p["open"]])]
        selectable = [p for _, g in groups for p in g]
        if q and not exact:
            selectable.append({"new": q})
        sel = max(0, min(sel, len(selectable) - 1))

        # Lines to draw: ("head", text) | ("row", item) | ("gap",)
        lines = []
        for title, items in groups:
            if not items:
                continue
            if lines:
                lines.append(("gap",))
            if title:
                lines.append(("head", title))
            lines += [("row", p) for p in items]
        if q and not exact:
            if lines:
                lines.append(("gap",))
            lines.append(("row", selectable[-1]))

        scr.erase()
        h, w = scr.getmaxyx()
        L, R = 3, w - 4                                # left and right margins

        put(1, L, T["title"], curses.A_BOLD)

        put(3, L, "›", ui.accent | curses.A_BOLD)
        if query:
            put(3, L + 2, query, 0, R - L - 2)
        else:
            put(3, L + 2, T["search"], ui.dim, R - L - 2)
        put(4, L, "─" * (R - L + 1), ui.dim)

        top, avail = 6, max(1, h - 9)
        sel_line = next((i for i, l in enumerate(lines)
                         if l[0] == "row" and l[1] is selectable[sel]), 0) if selectable else 0
        start = max(0, min(sel_line - avail + 1, len(lines) - avail)) if sel_line >= avail else 0

        for i, line in enumerate(lines[start:start + avail]):
            y = top + i
            if line[0] == "head":
                put(y, L, line[1], ui.dim)
                continue
            if line[0] == "gap":
                continue
            row = line[1]
            cur = row is selectable[sel]
            if cur:
                put(y, L - 1, " " * (R - L + 3), ui.sel_bg)
            if "new" in row:
                put(y, L, f"+  {row['new']}", (ui.sel_accent if cur else ui.accent))
                hint = T["new"]
                put(y, R - len(hint) + 1, hint, ui.sel_dim if cur else ui.dim)
                continue
            if row["open"]:
                put(y, L, "●", ui.sel_green if cur else ui.green)
            put(y, L + 2, row["name"][:R - L - 24], (ui.sel_bg | curses.A_BOLD) if cur else 0)
            meta = ago(row["t"])
            if row["branch"] not in ("", "main", "master"):
                meta = f"{row['branch'][:12]}   {meta}"
            put(y, R - len(meta) + 1, meta, ui.sel_dim if cur else ui.dim)

        if not lines:
            put(top, L, T["empty"], ui.dim)

        if status:
            put(h - 2, L, status, ui.accent)
        else:
            x = L
            for key, label in T["keys"]:
                put(h - 2, x, key, ui.dim | curses.A_BOLD)
                put(h - 2, x + len(key) + 1, label, ui.dim)
                x += len(key) + len(label) + 4
        scr.move(3, min(w - 2, L + 2 + len(query)))
        scr.refresh()

        try:
            k = scr.get_wch()
        except curses.error:
            continue                                   # timeout: redraw
        status = ""
        if k in ("\x1b", "\x03"):
            return
        if k == curses.KEY_UP:
            sel -= 1
        elif k == curses.KEY_DOWN:
            sel += 1
        elif k == "\x06":                              # Ctrl+F: Finder
            subprocess.run(["open", ROOT])
        elif k == "\x0e":                              # Ctrl+N: new project from the query
            if not q:
                status = T["need_name"]
                continue
            err = create_project(q)
            if err is None:
                return
            status = err
        elif k in ("\n", "\r", curses.KEY_ENTER):
            if not selectable:
                continue
            row = selectable[sel]
            err = create_project(row["new"]) if "new" in row else open_project(row["name"])
            if err is None:
                return
            status = err
        elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            query, sel = query[:-1], 0
        elif k == "\x15":                              # Ctrl+U: temizle
            query, sel = "", 0
        elif isinstance(k, str) and k.isprintable():
            query, sel = query + k, 0


if __name__ == "__main__":
    curses.wrapper(main)
