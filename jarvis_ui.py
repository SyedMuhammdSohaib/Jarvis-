"""
JARVIS UI - modern desktop window for jarvis.py

Run:   python jarvis_ui.py
Needs: pip install customtkinter
Keep jarvis.py, jarvis_extras.py and this file in the SAME folder.
(your API key, MODEL and BASE_URL are still set inside jarvis.py)
"""

import math
import time
import queue
import threading
import subprocess
from tkinter import messagebox

import customtkinter as ctk
from openai import OpenAI

import jarvis
import jarvis_extras as extras

# ----------------------------------------------------------------------------
# CHOICES
# ----------------------------------------------------------------------------
LANGS = {
    "English": "en",
    "اردو (Urdu)": "ur",
    "हिन्दी (Hindi)": "hi",
    "中文 (Chinese)": "zh",
    "Русский (Russian)": "ru",
    "العربية (Arabic)": "ar",
}
CODE_TO_LANG = {v: k for k, v in LANGS.items()}
THEME_NAMES = {"Blue": "blue", "Iron Man": "ironman", "Matrix": "matrix"}
KEY_TO_THEME = {v: k for k, v in THEME_NAMES.items()}

STATE_TEXT = {"idle": "ONLINE", "thinking": "THINKING...",
              "listening": "LISTENING...", "speaking": "SPEAKING..."}
STATE_KEY = {"thinking": "think", "listening": "listen", "speaking": "speak"}

QUICK = [
    ("Weather", "What's the weather in Multan right now?"),
    ("News", "Tell me today's top news headlines"),
    ("Music", "Play a relaxing song on YouTube"),
    ("Joke", "Tell me a funny joke"),
    ("Shayari", "Koi achi si shayari sunao"),
    ("Screenshot", "take a screenshot"),
    ("Volume +", "volume up"),
    ("Volume -", "volume down"),
]

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def is_rtl(text):
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("J.A.R.V.I.S")
        self.geometry("1020x740")
        self.minsize(800, 580)

        self.cfg = extras.load_settings()
        self.T = extras.THEMES[self.cfg["theme"]]
        jarvis.SPEAK_REPLIES = bool(self.cfg["voice_on"])

        self.q = queue.Queue()
        self.busy = False
        self.ui_state = "idle"
        self.t = 0
        self.angle = 0
        self.live = False            # continuous listening on/off
        self.live_gen = 0
        self.live_lang = self.cfg["lang"]
        self.themed = []             # (widget, {option: theme_key})
        self.msg_themed = []         # same, for chat bubbles

        # ---- API key ----
        if not jarvis.API_KEY:
            key = ctk.CTkInputDialog(text="Paste your API key:", title="Jarvis").get_input()
            if not key:
                raise SystemExit
            jarvis.API_KEY = key.strip()
        jarvis.client = OpenAI(api_key=jarvis.API_KEY, base_url=jarvis.BASE_URL)

        # plug in the extra features (YouTube, PC control, themes, voices ...)
        extras.install(
            on_theme=lambda name: self.q.put(("theme", name)),
            on_voice=lambda g, s: self.q.put(("voice", g, s)),
            confirm=self.ask_confirm,
        )
        # run_command asks through a popup window instead of the console
        jarvis.tool_run_command = self.confirm_and_run

        self.build_ui()
        self.add_message("jarvis", "Jarvis online. Type below, tap a shortcut, "
                                   "or press Mic ONCE and just keep talking.")
        self.animate()
        self.poll()

    # ------------------------------------------------------------- theming
    def reg(self, widget, store=None, **opts):
        (self.themed if store is None else store).append((widget, opts))
        self._apply(widget, opts)
        return widget

    def _apply(self, widget, opts):
        widget.configure(**{k: self.T[v] for k, v in opts.items()})

    def set_theme(self, key):
        if key not in extras.THEMES:
            return
        self.T = extras.THEMES[key]
        extras.settings["theme"] = key
        extras.save_settings()
        for widget, opts in self.themed + self.msg_themed:
            try:
                self._apply(widget, opts)
            except Exception:
                pass
        self.set_state(self.ui_state)
        self.theme_menu.set(KEY_TO_THEME[key])

    def on_theme_menu(self, choice):
        self.set_theme(THEME_NAMES[choice])

    # ------------------------------------------------------------------ UI
    def build_ui(self):
        reg = self.reg
        reg(self, fg_color="bg")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ---- header ----
        header = reg(ctk.CTkFrame(self, corner_radius=0), fg_color="panel")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        self.reactor = ctk.CTkCanvas(header, width=90, height=90, highlightthickness=0)
        reg(self.reactor, bg="panel")
        self.reactor.grid(row=0, column=0, padx=(18, 8), pady=8)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w")
        reg(ctk.CTkLabel(title_box, text="J.A.R.V.I.S", font=("Segoe UI", 26, "bold")),
            text_color="accent").pack(anchor="w")
        self.status = ctk.CTkLabel(title_box, text="ONLINE", font=("Segoe UI", 12, "bold"))
        self.status.pack(anchor="w")
        self.set_state("idle")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=2, padx=14)

        menu_style = dict(fg_color="bj", button_color="accent", button_hover_color="hover",
                          text_color="text", dropdown_fg_color="bj",
                          dropdown_text_color="text", dropdown_hover_color="bu")

        self.lang_menu = ctk.CTkOptionMenu(right, values=list(LANGS.keys()), width=150,
                                           command=self.on_lang_change)
        self.lang_menu.set(CODE_TO_LANG.get(self.cfg["lang"], "English"))
        reg(self.lang_menu, **menu_style).grid(row=0, column=0, padx=4, pady=3)

        self.theme_menu = ctk.CTkOptionMenu(right, values=list(THEME_NAMES.keys()), width=110,
                                            command=self.on_theme_menu)
        self.theme_menu.set(KEY_TO_THEME[self.cfg["theme"]])
        reg(self.theme_menu, **menu_style).grid(row=0, column=1, padx=4, pady=3)

        reg(ctk.CTkButton(right, text="Clear", width=70, fg_color="transparent",
                          border_width=1, command=self.clear_chat),
            border_color="accent", text_color="accent", hover_color="bj"
            ).grid(row=0, column=2, padx=4, pady=3)

        self.voice_switch = ctk.CTkSwitch(right, text="Voice", command=self.toggle_voice)
        if jarvis.SPEAK_REPLIES:
            self.voice_switch.select()
        reg(self.voice_switch, progress_color="accent", text_color="text"
            ).grid(row=1, column=0, padx=4, pady=3)

        self.gender_menu = ctk.CTkOptionMenu(right, values=["Male", "Female"], width=110,
                                             command=self.on_gender)
        self.gender_menu.set(self.cfg["voice"].capitalize())
        reg(self.gender_menu, **menu_style).grid(row=1, column=1, padx=4, pady=3)

        self.speed_menu = ctk.CTkOptionMenu(right, values=["Slow", "Normal", "Fast"], width=100,
                                            command=self.on_speed)
        self.speed_menu.set(self.cfg["speed"].capitalize())
        reg(self.speed_menu, **menu_style).grid(row=1, column=2, padx=4, pady=3)

        # ---- chat area ----
        self.chat = ctk.CTkScrollableFrame(self, corner_radius=0)
        reg(self.chat, fg_color="bg")
        self.chat.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 0))

        # ---- quick buttons ----
        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 0))
        for label, prompt in QUICK:
            b = ctk.CTkButton(chips, text=label, width=84, height=28, corner_radius=14,
                              command=lambda p=prompt: self.send(p))
            reg(b, fg_color="bj", hover_color="bu", text_color="text").pack(side="left", padx=3)

        # ---- input bar ----
        bar = reg(ctk.CTkFrame(self, corner_radius=16), fg_color="panel")
        bar.grid(row=3, column=0, sticky="ew", padx=14, pady=12)
        bar.grid_columnconfigure(1, weight=1)

        self.mic_btn = ctk.CTkButton(bar, text="Mic", width=70, height=40, corner_radius=12,
                                     fg_color="#00a152", hover_color="#00c853",
                                     command=self.on_mic)
        self.mic_btn.grid(row=0, column=0, padx=(10, 6), pady=10)

        self.entry = ctk.CTkEntry(bar, height=40, font=("Segoe UI", 15),
                                  placeholder_text="Type in any language...")
        reg(self.entry, fg_color="bg", border_color="bu", text_color="text")
        self.entry.grid(row=0, column=1, sticky="ew", padx=6, pady=10)
        self.entry.bind("<Return>", lambda e: self.on_send())

        send_btn = ctk.CTkButton(bar, text="Send", width=80, height=40, corner_radius=12,
                                 command=self.on_send)
        reg(send_btn, fg_color="accent", text_color="btn_text", hover_color="hover"
            ).grid(row=0, column=2, padx=(6, 10), pady=10)
        self.entry.focus()

    # ------------------------------------------------------------ animation
    def state_color(self, state):
        return self.T["accent"] if state == "idle" else self.T[STATE_KEY[state]]

    def animate(self):
        c = self.reactor
        c.delete("all")
        cx = cy = 45
        col = self.state_color(self.ui_state)
        self.t += 1
        speed = {"idle": 2, "thinking": 10, "listening": 4, "speaking": 6}[self.ui_state]
        self.angle = (self.angle + speed) % 360
        amp = 3 if self.ui_state in ("listening", "speaking") else 1
        r = 30 + amp * math.sin(self.t / 6)

        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=2)
        c.create_oval(cx - 19, cy - 19, cx + 19, cy + 19, outline=col, width=1)
        c.create_arc(cx - 41, cy - 41, cx + 41, cy + 41, start=self.angle, extent=90,
                     style="arc", outline=col, width=3)
        c.create_arc(cx - 41, cy - 41, cx + 41, cy + 41, start=self.angle + 180, extent=90,
                     style="arc", outline=col, width=3)
        c.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill=col, outline="")
        self.after(40, self.animate)

    def set_state(self, state):
        self.ui_state = state
        self.status.configure(text=STATE_TEXT[state], text_color=self.state_color(state))

    # -------------------------------------------------------------- chat UI
    def add_message(self, role, text):
        store = self.msg_themed
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.pack(fill="x", pady=5, padx=6)
        user = role == "user"
        bubble = self.reg(ctk.CTkFrame(row, corner_radius=16), store,
                          fg_color="bu" if user else "bj")
        bubble.pack(side="right" if user else "left")
        self.reg(ctk.CTkLabel(bubble, text="You" if user else "Jarvis",
                              font=("Segoe UI", 11, "bold")), store, text_color="accent"
                 ).pack(anchor="w", padx=14, pady=(8, 0))
        self.reg(ctk.CTkLabel(bubble, text=text, wraplength=600, font=("Segoe UI", 15),
                              justify="right" if is_rtl(text) else "left"), store,
                 text_color="text").pack(padx=14, pady=(2, 10))
        self.after(60, self.scroll_bottom)

    def scroll_bottom(self):
        try:
            self.update_idletasks()
            self.chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def clear_chat(self):
        for w in self.chat.winfo_children():
            w.destroy()
        self.msg_themed.clear()
        jarvis.history.clear()
        self.add_message("jarvis", "Memory cleared. How can I help?")

    # ------------------------------------------------------ voice settings
    def toggle_voice(self):
        jarvis.SPEAK_REPLIES = bool(self.voice_switch.get())
        extras.settings["voice_on"] = jarvis.SPEAK_REPLIES
        extras.save_settings()

    def on_gender(self, choice):
        extras.settings["voice"] = choice.lower()
        extras.save_settings()

    def on_speed(self, choice):
        extras.settings["speed"] = choice.lower()
        extras.save_settings()

    def refresh_voice_menus(self, gender, speed):
        self.gender_menu.set(gender.capitalize())
        self.speed_menu.set(speed.capitalize())

    # ------------------------------------------------------------- actions
    def on_send(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.send(text)

    def send(self, text, force=False):
        if self.busy and not force:
            return
        self.busy = True
        self.add_message("user", text)
        self.set_state("thinking")
        threading.Thread(target=self.worker, args=(text,), daemon=True).start()

    def worker(self, text):
        try:
            reply = jarvis.think(text)
        except Exception as e:
            reply = f"Error: {e}"
        self.q.put(("msg", "jarvis", reply))
        if jarvis.SPEAK_REPLIES:
            self.q.put(("state", "speaking"))
            jarvis.speak(reply)
        self.q.put(("state", "listening" if self.live else "idle"))
        self.q.put(("free",))

    # ---------------------------------------------------- live microphone
    def on_lang_change(self, choice):
        self.live_lang = LANGS[choice]
        extras.settings["lang"] = self.live_lang
        extras.save_settings()

    def on_mic(self):
        """Press once = continuous listening ON. Press again = OFF."""
        if self.live:
            self.stop_live()
            return
        if jarvis.sr is None:
            self.add_message("jarvis", "Microphone support is not installed. "
                                       "Run: pip install SpeechRecognition pyaudio")
            return
        self.live = True
        self.live_gen += 1
        self.live_lang = LANGS[self.lang_menu.get()]
        self.mic_btn.configure(text="Stop", fg_color="#d50000", hover_color="#ff1744")
        if not self.busy:
            self.set_state("listening")
        threading.Thread(target=self.live_loop, args=(self.live_gen,), daemon=True).start()

    def stop_live(self):
        self.live = False
        self.live_gen += 1
        self.mic_btn.configure(text="Mic", fg_color="#00a152", hover_color="#00c853")
        if not self.busy:
            self.set_state("idle")

    def live_loop(self, gen):
        """Background loop: listen -> answer -> listen again, forever."""
        sr = jarvis.sr
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.pause_threshold = 0.9          # seconds of silence = you finished speaking
        first = True
        try:
            while self.live and gen == self.live_gen:
                # (re)open the microphone fresh so Jarvis never hears its own voice
                with sr.Microphone() as source:
                    if first:
                        r.adjust_for_ambient_noise(source, duration=1)
                        first = False
                    while self.live and gen == self.live_gen and not self.busy:
                        if self.ui_state != "listening":
                            self.q.put(("state", "listening"))
                        try:
                            audio = r.listen(source, timeout=1, phrase_time_limit=25)
                        except sr.WaitTimeoutError:
                            continue
                        if not self.live or gen != self.live_gen:
                            break
                        try:
                            text = r.recognize_google(
                                audio, language=jarvis.STT_CODES[self.live_lang])
                        except sr.UnknownValueError:
                            continue
                        except sr.RequestError:
                            self.q.put(("msg", "jarvis",
                                        "Speech service not reachable. Check your internet."))
                            time.sleep(3)
                            continue
                        text = text.strip()
                        if text:
                            self.busy = True
                            self.q.put(("send", text))
                # wait here while Jarvis thinks and speaks
                while self.busy and self.live and gen == self.live_gen:
                    time.sleep(0.2)
                time.sleep(0.4)
        except Exception as e:
            self.q.put(("msg", "jarvis", f"Microphone error: {e}"))
            self.q.put(("livefail",))

    # -------------------------------------------------------- confirmations
    def ask_confirm(self, title, message):
        """Thread-safe Yes/No popup. Called from background threads."""
        done = threading.Event()
        holder = {}
        self.q.put(("confirm", title, message, done, holder))
        done.wait()
        return holder.get("ok", False)

    def confirm_and_run(self, command):
        """Replacement for jarvis.tool_run_command: asks with a popup."""
        if not self.ask_confirm("Jarvis wants to run a command",
                                f"Allow this command?\n\n{command}"):
            return "User denied the command."
        try:
            r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            return (r.stdout + r.stderr).strip()[:2000] or "Done (no output)."
        except Exception as e:
            return f"Command failed: {e}"

    # ------------------------------------------------- thread -> UI bridge
    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "msg":
                    self.add_message(item[1], item[2])
                elif kind == "state":
                    self.set_state(item[1])
                elif kind == "free":
                    self.busy = False
                elif kind == "send":
                    self.send(item[1], force=True)
                elif kind == "livefail":
                    self.stop_live()
                elif kind == "theme":
                    self.set_theme(item[1])
                elif kind == "voice":
                    self.refresh_voice_menus(item[1], item[2])
                elif kind == "confirm":
                    ok = messagebox.askyesno(item[1], item[2], icon="warning")
                    item[4]["ok"] = ok
                    item[3].set()
        except queue.Empty:
            pass
        self.after(50, self.poll)


if __name__ == "__main__":
    JarvisApp().mainloop()
