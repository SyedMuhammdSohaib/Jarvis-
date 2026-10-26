"""
JARVIS EXTRAS - adds fun features to jarvis.py WITHOUT editing it.

  * Play songs/videos on YouTube
  * Jokes, shayari, stories (via the AI prompt)
  * PC control: lock, screen off, restart/shutdown (with confirmation)
  * Themes (Blue / Iron Man / Matrix)
  * Voice choice: male/female, slow/normal/fast
  * Settings saved in jarvis_settings.json

Keep this file in the same folder as jarvis.py and jarvis_ui.py.
"""

import io
import os
import re
import json
import time
import queue
import asyncio
import threading
import datetime
import platform
import tempfile
import subprocess
import webbrowser
import urllib.parse
import urllib.request

from openai import BadRequestError

import jarvis

OS = platform.system()

# ----------------------------------------------------------------------------
# THEMES
# ----------------------------------------------------------------------------
THEMES = {
    "blue": dict(bg="#060b14", panel="#0b1423", bj="#10213b", bu="#0b4a6e",
                 text="#e6f6ff", accent="#00d4ff", hover="#66e6ff", btn_text="#00131a",
                 think="#ffb300", listen="#00e676", speak="#c77dff"),
    "ironman": dict(bg="#0d0505", panel="#1a0a0a", bj="#2b1111", bu="#7a1c1c",
                    text="#fff3e0", accent="#ffb300", hover="#ffd54f", btn_text="#1a0a00",
                    think="#00d4ff", listen="#00e676", speak="#ff5252"),
    "matrix": dict(bg="#020a03", panel="#06140a", bj="#0b2412", bu="#0f4a22",
                   text="#d6ffe0", accent="#00ff66", hover="#7dffa8", btn_text="#00140a",
                   think="#ffd600", listen="#00e5ff", speak="#e040fb"),
}

# ----------------------------------------------------------------------------
# VOICES
# ----------------------------------------------------------------------------
VOICES = {
    "male": {"en": "en-US-GuyNeural", "ur": "ur-PK-AsadNeural", "hi": "hi-IN-MadhurNeural",
             "zh": "zh-CN-YunxiNeural", "ru": "ru-RU-DmitryNeural", "ar": "ar-SA-HamedNeural"},
    "female": {"en": "en-US-JennyNeural", "ur": "ur-PK-UzmaNeural", "hi": "hi-IN-SwaraNeural",
               "zh": "zh-CN-XiaoxiaoNeural", "ru": "ru-RU-SvetlanaNeural", "ar": "ar-SA-ZariyahNeural"},
}
RATES = {"slow": "-25%", "normal": "+0%", "fast": "+35%"}
LANG_FIX = {"fa": "ur", "ps": "ur", "sd": "ur", "mr": "hi", "ne": "hi"}  # langdetect look-alikes

# ----------------------------------------------------------------------------
# SETTINGS (saved to a small file next to the scripts)
# ----------------------------------------------------------------------------
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_settings.json")
DEFAULTS = {"theme": "blue", "voice": "male", "speed": "normal", "lang": "en", "voice_on": True}
settings = dict(DEFAULTS)


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings.update(json.load(f))
    except Exception:
        pass
    if settings["theme"] not in THEMES:
        settings["theme"] = "blue"
    if settings["voice"] not in VOICES:
        settings["voice"] = "male"
    if settings["speed"] not in RATES:
        settings["speed"] = "normal"
    return settings


def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# HOOKS (the UI fills these in)
# ----------------------------------------------------------------------------
hooks = {"theme": None, "voice": None, "confirm": None}


# ----------------------------------------------------------------------------
# NEW TOOLS
# ----------------------------------------------------------------------------
def play_youtube(query):
    q = urllib.parse.quote(query)
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/results?search_query={q}",
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
        ids = re.findall(r'"videoId":"([\w-]{11})"', html)
        if ids:
            webbrowser.open("https://www.youtube.com/watch?v=" + ids[0])
            return f"Playing '{query}' on YouTube."
    except Exception:
        pass
    webbrowser.open(f"https://www.youtube.com/results?search_query={q}")
    return f"Opened YouTube search for '{query}'."


def lock_pc():
    if OS != "Windows":
        return "Lock is only set up for Windows."
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Computer locked."


def screen_off():
    if OS != "Windows":
        return "Screen off is only set up for Windows."
    import ctypes
    ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
    return "Screen turned off. Move the mouse to wake it."


def power(mode):
    if OS != "Windows":
        return "Power control is only set up for Windows."
    if mode == "cancel":
        subprocess.run("shutdown /a", shell=True)
        return "Shutdown cancelled."
    if mode not in ("restart", "shutdown"):
        return "Unknown power mode."
    word = "restart" if mode == "restart" else "shut down"
    confirm = hooks["confirm"]
    if not confirm or not confirm("Jarvis power request",
                                  f"Do you want to {word} the computer in 15 seconds?\n"
                                  f"(You can cancel by saying 'cancel shutdown'.)"):
        return "Cancelled by user."
    flag = "/r" if mode == "restart" else "/s"
    subprocess.run(f"shutdown {flag} /t 15", shell=True)
    return f"Will {word} in 15 seconds."


def set_theme(name):
    name = (name or "").lower().replace(" ", "")
    if name not in THEMES:
        return "Unknown theme. Choose blue, ironman or matrix."
    if hooks["theme"]:
        hooks["theme"](name)
    return f"Theme changed to {name}."


def set_voice(gender, speed):
    changed = []
    if gender in VOICES:
        settings["voice"] = gender
        changed.append(gender)
    if speed in RATES:
        settings["speed"] = speed
        changed.append(speed)
    if not changed:
        return "Tell me male or female, and slow, normal or fast."
    save_settings()
    if hooks["voice"]:
        hooks["voice"](settings["voice"], settings["speed"])
    return "Voice updated: " + ", ".join(changed)


def run_extra(action, args):
    if action == "play_youtube":
        return play_youtube(args.get("query", ""))
    if action == "lock_pc":
        return lock_pc()
    if action == "screen_off":
        return screen_off()
    if action == "power":
        return power(args.get("mode", ""))
    if action == "set_theme":
        return set_theme(args.get("name", ""))
    if action == "set_voice":
        return set_voice(args.get("gender", ""), args.get("speed", ""))
    return None


# ----------------------------------------------------------------------------
# PROMPT ADD-ON
# ----------------------------------------------------------------------------
EXTRA_PROMPT = """

More actions:
- "play_youtube": play a song or video on YouTube. args: {"query": "song or video name"}
- "lock_pc": lock the computer. args: {}
- "screen_off": turn the monitor off. args: {}
- "power": restart or shut down (the user is asked to confirm). args: {"mode": "restart" | "shutdown" | "cancel"}
- "set_theme": change the app look. args: {"name": "blue" | "ironman" | "matrix"}
- "set_voice": change Jarvis's voice. args: {"gender": "male" | "female" | "", "speed": "slow" | "normal" | "fast" | ""}

Extra rules:
- You can tell jokes, shayari/poetry and short stories in the user's language using action "none". Keep jokes clean. Stories are about 100-150 words and kid-friendly unless asked otherwise.
- If the user writes Urdu or Hindi in English letters (Roman Urdu / Hinglish), reply in proper Urdu script (or Devanagari for Hindi) so the voice can read it correctly.
- Only use "power" when the user clearly asks to restart or shut down.
"""


# ----------------------------------------------------------------------------
# NEW SPEAK  (fast: starts talking after the FIRST sentence is ready)
# ----------------------------------------------------------------------------
def split_sentences(text):
    parts = re.split(r"(?<=[.!?\u06d4\u061f\u3002\uff01\uff1f\n])\s*", text)
    parts = [p.strip() for p in parts if p and p.strip()]
    merged = []
    for p in parts:                      # glue very short pieces to the next one
        if merged and len(merged[-1]) < 25:
            merged[-1] += " " + p
        else:
            merged.append(p)
    return merged or [text]


async def _synth(text, voice, rate):
    buf = bytearray()
    async for chunk in jarvis.edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def speak(text):
    if not jarvis.SPEAK_REPLIES or jarvis.edge_tts is None or jarvis.pygame is None:
        return
    try:
        clean = jarvis.clean_for_speech(text).strip()
        if not clean:
            return
        lang = "en"
        if jarvis.detect:
            lang = jarvis.detect(clean)
            lang = "zh" if lang.startswith("zh") else LANG_FIX.get(lang, lang)
        table = VOICES[settings["voice"]]
        voice = table.get(lang, table["en"])
        rate = RATES[settings["speed"]]

        audio_q = queue.Queue(maxsize=3)

        def producer():                  # makes the next sentence while the current one plays
            for sentence in split_sentences(clean):
                try:
                    data = asyncio.run(_synth(sentence, voice, rate))
                except Exception:
                    data = b""
                audio_q.put(data)
            audio_q.put(None)

        threading.Thread(target=producer, daemon=True).start()

        if not jarvis.pygame.mixer.get_init():
            jarvis.pygame.mixer.init()
        while True:
            data = audio_q.get()
            if data is None:
                break
            if not data:
                continue
            jarvis.pygame.mixer.music.load(io.BytesIO(data), "mp3")
            jarvis.pygame.mixer.music.play()
            while jarvis.pygame.mixer.music.get_busy():
                time.sleep(0.03)
    except Exception as e:
        print(f"  (voice error: {e})")


# ----------------------------------------------------------------------------
# INSTALL INTO jarvis.py
# ----------------------------------------------------------------------------
def install(on_theme=None, on_voice=None, confirm=None):
    hooks["theme"], hooks["voice"], hooks["confirm"] = on_theme, on_voice, confirm

    if "More actions:" not in jarvis.SYSTEM_PROMPT:
        jarvis.SYSTEM_PROMPT = jarvis.SYSTEM_PROMPT + EXTRA_PROMPT

    jarvis.speak = speak

    # Faster answers: ask reasoning models (gpt-oss) to think less
    effort = {"ok": "gpt-oss" in jarvis.MODEL}
    original_ask = jarvis.ask_model

    def ask_model(messages):
        if not effort["ok"]:
            return original_ask(messages)
        system = jarvis.SYSTEM_PROMPT.replace(
            "{today}", datetime.datetime.now().strftime("%A, %d %B %Y, %H:%M"))
        try:
            resp = jarvis.client.chat.completions.create(
                model=jarvis.MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                extra_body={"reasoning_effort": "low"},
            )
            return resp.choices[0].message.content or ""
        except BadRequestError:
            effort["ok"] = False         # this model doesn't support it; use normal call
            return original_ask(messages)

    jarvis.ask_model = ask_model

    original = jarvis.run_tool

    def run_tool(action, args):
        result = run_extra(action, args)
        if result is not None:
            return result
        return original(action, args)

    jarvis.run_tool = run_tool
