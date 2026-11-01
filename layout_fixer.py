#!/usr/bin/env python3
"""
Layout Fixer - fixes text typed with the wrong keyboard language.
Select the text, press the hotkey, and it is converted (Hebrew <-> English etc.).

Run the program again at any time to open the settings window.
CLI: --install / --uninstall (autostart)
"""
import sys
import os
import time
import json
import socket
import queue
import platform
import threading
import subprocess

APP = "LayoutFixer"
PORT = 48613

# ---------------------------------------------------------------- layouts
# US-QWERTY keys, in the same order as every layout string below.
EN_KEYS = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`\\"

LAYOUTS = {
    "hebrew": ("Hebrew (עברית)",
               list("/'קראטוןםפ][שדגכעיחלךף,זסבהנמצתץ.;\\")),
    "russian": ("Russian (Русский)",
                list("йцукенгшщзхъфывапролджэячсмитьбю.ё\\")),
    "ukrainian": ("Ukrainian (Українська)",
                  list("йцукенгшщзхїфівапролджєячсмитьбю.ʼґ")),
    "arabic": ("Arabic (العربية)",
               "ض ص ث ق ف غ ع ه خ ح ج د ش س ي ب ل ا ت ن م ك ط ئ ء ؤ ر لا ى ة و ز ظ ذ \\".split(" ")),
    "greek": ("Greek (Ελληνικά)",
              list(";ςερτυθιοπ[]ασδφγηξκλ΄'ζχψωβνμ,./`\\")),
}

DEFAULT_CFG = {"layout": "hebrew", "hotkey": "Ctrl+Alt+Space", "autostart": False}
HOTKEY_PRESETS = ["Ctrl+Alt+Space", "Ctrl+Shift+Space", "Ctrl+Alt+L", "Ctrl+Shift+K", "F9"]


def build_maps(layout):
    toks = LAYOUTS[layout][1]
    assert len(toks) == len(EN_KEYS), layout
    fwd = dict(zip(EN_KEYS, toks))
    rev = {}
    for k, v in fwd.items():
        rev.setdefault(v, k)
    return fwd, rev


def convert(text, layout):
    fwd, rev = build_maps(layout)
    letters = {ch for v in fwd.values() for ch in v if ch.isalpha()}
    tgt = sum(1 for c in text if c.lower() in letters)
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    out = []
    if tgt > lat:  # target language -> English
        maxl = max(len(k) for k in rev)
        i = 0
        while i < len(text):
            for ln in range(maxl, 0, -1):
                chunk = text[i:i + ln]
                if len(chunk) == ln and chunk.lower() in rev:
                    e = rev[chunk.lower()]
                    out.append(e.upper() if ln == 1 and chunk.isupper() else e)
                    i += ln
                    break
            else:
                out.append(text[i])
                i += 1
    else:  # English -> target language
        for c in text:
            t = fwd.get(c.lower())
            if t is None:
                out.append(c)
            else:
                out.append(t.upper() if c.isupper() else t)
    return "".join(out)


# ---------------------------------------------------------------- config
def cfg_path():
    s = platform.system()
    if s == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif s == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")
    return os.path.join(base, APP, "config.json")


def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(cfg_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    if cfg["layout"] not in LAYOUTS:
        cfg["layout"] = "hebrew"
    return cfg


def save_cfg(cfg):
    p = cfg_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def to_pynput(s):
    names = {"ctrl": "<ctrl>", "control": "<ctrl>", "alt": "<alt>", "option": "<alt>",
             "shift": "<shift>", "cmd": "<cmd>", "win": "<cmd>", "super": "<cmd>",
             "space": "<space>"}
    out = []
    for p in [x.strip().lower() for x in s.split("+") if x.strip()]:
        if p in names:
            out.append(names[p])
        elif len(p) > 1 and p[0] == "f" and p[1:].isdigit():
            out.append("<%s>" % p)
        else:
            out.append(p)
    return "+".join(out)


# ---------------------------------------------------------------- autostart
def launch_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = sys.executable
    if platform.system() == "Windows":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            exe = w
    return [exe, os.path.abspath(__file__)]


def autostart(enable):
    s = platform.system()
    cmd = launch_cmd()
    if s == "Windows":
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, " ".join('"%s"' % c for c in cmd))
        else:
            try:
                winreg.DeleteValue(key, APP)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    elif s == "Darwin":
        p = os.path.expanduser("~/Library/LaunchAgents/com.layoutfixer.plist")
        if enable:
            args = "".join("<string>%s</string>" % c for c in cmd)
            with open(p, "w") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict><key>Label</key><string>com.layoutfixer</string>'
                        '<key>ProgramArguments</key><array>%s</array>'
                        '<key>RunAtLoad</key><true/></dict></plist>' % args)
        elif os.path.exists(p):
            os.remove(p)
    else:
        p = os.path.expanduser("~/.config/autostart/layoutfixer.desktop")
        if enable:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Layout Fixer\nExec=%s\n"
                        "X-GNOME-Autostart-enabled=true\n" % " ".join('"%s"' % c for c in cmd))
        elif os.path.exists(p):
            os.remove(p)


# ---------------------------------------------------------------- single instance
def claim_instance():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", PORT))
        s.listen(5)
        return s
    except OSError:
        try:
            c = socket.create_connection(("127.0.0.1", PORT), timeout=2)
            c.sendall(b"settings")
            c.close()
        except OSError:
            pass
        return None


# ---------------------------------------------------------------- app
class App:
    def __init__(self, srv):
        import tkinter as tk
        from pynput import keyboard
        import pyperclip
        self.tk, self.keyboard, self.pyperclip = tk, keyboard, pyperclip
        self.srv = srv
        self.root = tk.Tk()
        self.root.withdraw()
        self.first_run = not os.path.exists(cfg_path())
        self.cfg = load_cfg()
        self.q = queue.Queue()
        self.listener = None
        self.win = None
        self.ctl = keyboard.Controller()
        self.mod = keyboard.Key.cmd if platform.system() == "Darwin" else keyboard.Key.ctrl
        self.start_listener()
        threading.Thread(target=self.serve, daemon=True).start()
        if self.first_run:
            self.q.put("settings")
        self.root.after(200, self.poll)

    # hotkey -------------------------------------------------
    def start_listener(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
        try:
            self.listener = self.keyboard.GlobalHotKeys({to_pynput(self.cfg["hotkey"]): self.fix})
            self.listener.start()
        except Exception:
            self.listener = None

    def combo(self, ch):
        with self.ctl.pressed(self.mod):
            self.ctl.press(ch)
            self.ctl.release(ch)

    def fix(self):
        pc = self.pyperclip
        time.sleep(0.4)  # let the hotkey keys be released
        try:
            old = pc.paste()
        except Exception:
            old = ""
        pc.copy("")
        self.combo("c")
        sel = ""
        for _ in range(12):
            time.sleep(0.05)
            sel = pc.paste()
            if sel:
                break
        if sel:
            pc.copy(convert(sel, self.cfg["layout"]))
            time.sleep(0.08)
            self.combo("v")
            time.sleep(0.25)
        pc.copy(old)

    # messages from second launches ---------------------------
    def serve(self):
        while True:
            try:
                conn, _ = self.srv.accept()
                data = conn.recv(64).decode(errors="ignore")
                conn.close()
                self.q.put(data)
            except OSError:
                break

    def poll(self):
        while not self.q.empty():
            if self.q.get() == "settings":
                self.open_settings()
        self.root.after(200, self.poll)

    # settings window -----------------------------------------
    def open_settings(self):
        tk = self.tk
        from tkinter import ttk, messagebox
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            self.win.focus_force()
            return
        w = self.win = tk.Toplevel(self.root)
        w.title("Layout Fixer - Settings")
        w.resizable(False, False)
        f = ttk.Frame(w, padding=18)
        f.grid()

        ttk.Label(f, text="Language to switch with English:").grid(row=0, column=0, sticky="w")
        labels = [v[0] for v in LAYOUTS.values()]
        keys = list(LAYOUTS)
        lang = ttk.Combobox(f, values=labels, state="readonly", width=28)
        lang.current(keys.index(self.cfg["layout"]))
        lang.grid(row=1, column=0, pady=(2, 12), sticky="w")

        ttk.Label(f, text="Hotkey (pick one or type e.g. Ctrl+Alt+H):").grid(row=2, column=0, sticky="w")
        hk = ttk.Combobox(f, values=HOTKEY_PRESETS, width=28)
        hk.set(self.cfg["hotkey"])
        hk.grid(row=3, column=0, pady=(2, 12), sticky="w")

        auto = tk.BooleanVar(value=self.cfg["autostart"])
        ttk.Checkbutton(f, text="Start automatically with the computer", variable=auto).grid(
            row=4, column=0, sticky="w", pady=(0, 14))

        def save():
            hotkey = hk.get().strip()
            try:
                self.keyboard.HotKey.parse(to_pynput(hotkey))
                if not hotkey:
                    raise ValueError
            except Exception:
                messagebox.showerror("Layout Fixer", "Invalid hotkey. Example: Ctrl+Alt+Space", parent=w)
                return
            self.cfg.update(layout=keys[lang.current()], hotkey=hotkey, autostart=auto.get())
            save_cfg(self.cfg)
            try:
                autostart(self.cfg["autostart"])
            except Exception as e:
                messagebox.showwarning("Layout Fixer", "Could not change autostart:\n%s" % e, parent=w)
            self.start_listener()
            w.destroy()

        def quit_app():
            if self.listener:
                self.listener.stop()
            try:
                self.srv.close()
            except OSError:
                pass
            self.root.destroy()

        row = ttk.Frame(f)
        row.grid(row=5, column=0, sticky="we")
        ttk.Button(row, text="Save", command=save).pack(side="left")
        ttk.Button(row, text="Close", command=w.destroy).pack(side="left", padx=6)
        ttk.Button(row, text="Quit program", command=quit_app).pack(side="right")

        ttk.Label(f, foreground="gray",
                  text="Select text, press the hotkey - the text is converted.\n"
                       "Run the program again to open this window.").grid(row=6, column=0, pady=(12, 0), sticky="w")
        w.lift()
        w.focus_force()


def main():
    if "--install" in sys.argv:
        autostart(True)
        print("Autostart enabled")
        return
    if "--uninstall" in sys.argv:
        autostart(False)
        print("Autostart disabled")
        return
    srv = claim_instance()
    if srv is None:
        return  # already running - it was asked to open settings
    App(srv).root.mainloop()


if __name__ == "__main__":
    main()
