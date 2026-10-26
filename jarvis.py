"""
JARVIS - a personal desktop assistant powered by an AI model on Groq.

Features
  * Chat in English, Urdu, Hindi, Chinese, Russian, Arabic (type or speak)
  * Speaks answers back in the language of the reply
  * Real-time info: web search, weather, date/time
  * Device control: open apps/websites, screenshots, volume/media keys,
    typing text, system info, and shell commands (always asks you first)

Run:  python jarvis.py
"""

import os
import re
import sys
import json
import time
import shutil
import asyncio
import platform
import datetime
import subprocess
import tempfile
import webbrowser
import urllib.parse
import urllib.request

from openai import OpenAI, BadRequestError

# load GROQ_API_KEY from a .env file next to this script (if python-dotenv is installed)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

# ----------------------------------------------------------------------------
# SETTINGS  (you can edit these)
# ----------------------------------------------------------------------------
# Never paste the key here - put it in the .env file (see .env.example)
API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = "openai/gpt-oss-120b"           # Faster but less smart: "openai/gpt-oss-20b"
BASE_URL = "https://api.groq.com/openai/v1"
MAX_TOOL_STEPS = 6                      # how many tool calls Jarvis may chain for one request
SPEAK_REPLIES = True                                # False = text only
USE_MICROPHONE = False                              # True = press Enter, then talk
CURRENT_LANG = "en"                                 # language used for the microphone

# speech-to-text codes and text-to-speech voices per language
STT_CODES = {"en": "en-US", "ur": "ur-PK", "hi": "hi-IN",
             "zh": "zh-CN", "ru": "ru-RU", "ar": "ar-SA"}
VOICES = {"en": "en-US-GuyNeural", "ur": "ur-PK-AsadNeural",
          "hi": "hi-IN-MadhurNeural", "zh": "zh-CN-YunxiNeural",
          "ru": "ru-RU-DmitryNeural", "ar": "ar-SA-HamedNeural"}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ----------------------------------------------------------------------------
# OPTIONAL LIBRARIES (Jarvis still works if some are missing)
# ----------------------------------------------------------------------------
try:
    import pyautogui
except Exception:
    pyautogui = None
try:
    from ddgs import DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None
try:
    import edge_tts
    import pygame
except Exception:
    edge_tts = None
    pygame = None
try:
    import speech_recognition as sr
except Exception:
    sr = None
try:
    from langdetect import detect
except Exception:
    detect = None

OS = platform.system()  # Windows / Darwin / Linux
HOME = os.path.expanduser("~")

SYSTEM_PROMPT = f"""You are JARVIS, a smart, polite personal assistant running on the user's computer ({OS}).
Always reply in the SAME language the user wrote in (English, Urdu, Hindi, Chinese, Russian or Arabic).
Today is {{today}}. The user's home folder is {HOME}.

You have tools to control the computer and to get live information. Use them whenever they help.

Rules:
- For anything about news, prices, scores, sports, current events or anything that may have changed, use web_search first.
- If no other tool fits the task (maths, renaming or sorting many files, Excel/CSV/PDF work, image resizing,
  checking something on the system...), write a short Python script and run it with run_python.
  Print the result at the end of the script. Prefer the standard library.
- For files, look first (list_files / find_files) so you use real paths, then act.
- Never delete files unless the user clearly asked for it.
- If a tool fails, read the error, fix the problem and try again once before giving up.
- Never claim you did something unless you called the tool for it.
- Keep replies short and natural because they will be spoken aloud. No markdown, tables or long lists.
"""


def tool(name, description, params=None, required=None):
    """Build one tool definition in the format the API expects."""
    return {"type": "function", "function": {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": params or {},
                       "required": required or []},
    }}


TOOLS = [
    tool("web_search", "Look up live information on the web (news, prices, scores, facts).",
         {"query": {"type": "string"}}, ["query"]),
    tool("weather", "Get the current weather for a city.",
         {"city": {"type": "string"}}, ["city"]),
    tool("system_info", "Get battery, CPU, memory and time info of this computer."),
    tool("open_app", "Open an app on this computer.",
         {"name": {"type": "string", "description": "e.g. notepad, chrome, calculator"}}, ["name"]),
    tool("open_url", "Open a website in the browser.",
         {"url": {"type": "string"}}, ["url"]),
    tool("google_search", "Open a Google search in the browser for the user to see.",
         {"query": {"type": "string"}}, ["query"]),
    tool("screenshot", "Take a screenshot and save it to the Pictures folder."),
    tool("press_key", "Press a media or keyboard key, e.g. to change the volume.",
         {"key": {"type": "string", "enum": ["volumeup", "volumedown", "volumemute", "playpause",
                                             "nexttrack", "prevtrack", "enter", "esc"]}}, ["key"]),
    tool("type_text", "Type text where the cursor is.",
         {"text": {"type": "string"}}, ["text"]),
    tool("run_command", "Run a shell command. The user is asked to confirm first.",
         {"command": {"type": "string"}}, ["command"]),
    tool("run_python", "Write and run a Python script on this computer and get its printed output. "
                       "The user is asked to confirm first.",
         {"code": {"type": "string", "description": "Full Python script. Use print() for results."}},
         ["code"]),
    tool("list_files", "List the files and folders inside a folder.",
         {"folder": {"type": "string",
                     "description": "Folder path, or a name like Desktop, Downloads, Documents"}},
         ["folder"]),
    tool("find_files", "Search for files by name inside a folder and all its subfolders.",
         {"name": {"type": "string", "description": "Part of the file name, e.g. 'resume' or '.pdf'"},
          "folder": {"type": "string", "description": "Where to search. Default: the home folder"}},
         ["name"]),
    tool("read_file", "Read a text file (txt, py, csv, json, md, html...).",
         {"path": {"type": "string"}}, ["path"]),
    tool("write_file", "Create or overwrite a text file. Asks the user before overwriting.",
         {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    tool("move_file", "Move or rename a file or folder. The user is asked to confirm first.",
         {"source": {"type": "string"}, "destination": {"type": "string"}},
         ["source", "destination"]),
]

client = None
history = []


# ----------------------------------------------------------------------------
# TOOLS
# ----------------------------------------------------------------------------
def tool_search(query):
    if DDGS is None:
        return "Search library not installed. Run: pip install ddgs"
    try:
        with DDGS() as d:
            results = list(d.text(query, max_results=5))
        if not results:
            return "No results found."
        out = []
        for r in results:
            out.append(f"- {r.get('title','')}: {r.get('body','')} ({r.get('href','')})")
        return "\n".join(out)
    except Exception as e:
        return f"Search failed: {e}"


def tool_weather(city):
    try:
        url = "https://wttr.in/" + urllib.parse.quote(city) + "?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        c = data["current_condition"][0]
        return (f"{city}: {c['temp_C']}°C, feels like {c['FeelsLikeC']}°C, "
                f"{c['weatherDesc'][0]['value']}, humidity {c['humidity']}%, "
                f"wind {c['windspeedKmph']} km/h")
    except Exception as e:
        return f"Weather failed: {e}"


def tool_system_info():
    info = [f"OS: {OS} {platform.release()}",
            f"Time: {datetime.datetime.now().strftime('%A %d %B %Y, %H:%M')}"]
    try:
        import psutil
        info.append(f"CPU: {psutil.cpu_percent(interval=0.5)}%")
        m = psutil.virtual_memory()
        info.append(f"RAM: {m.percent}% used")
        b = psutil.sensors_battery()
        if b:
            info.append(f"Battery: {int(b.percent)}% ({'charging' if b.power_plugged else 'not charging'})")
    except Exception:
        info.append("(install psutil for CPU/RAM/battery: pip install psutil)")
    return "\n".join(info)


def tool_open_app(name):
    try:
        if OS == "Windows":
            subprocess.Popen(f'start "" "{name}"', shell=True)
        elif OS == "Darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            exe = shutil.which(name.lower()) or name.lower()
            subprocess.Popen([exe])
        return f"Opened {name}."
    except Exception as e:
        return f"Could not open {name}: {e}"


def tool_open_url(url):
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


def tool_screenshot():
    if pyautogui is None:
        return "pyautogui not installed."
    folder = os.path.join(os.path.expanduser("~"), "Pictures")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"jarvis_{int(time.time())}.png")
    pyautogui.screenshot(path)
    return f"Screenshot saved to {path}"


def tool_key(key):
    if pyautogui is None:
        return "pyautogui not installed."
    allowed = {"volumeup", "volumedown", "volumemute", "playpause",
               "nexttrack", "prevtrack", "enter", "esc"}
    if key not in allowed:
        return "Key not allowed."
    times = 5 if key in ("volumeup", "volumedown") else 1
    for _ in range(times):
        pyautogui.press(key)
    return f"Pressed {key}."


def tool_type_text(text):
    if pyautogui is None:
        return "pyautogui not installed."
    time.sleep(2)  # time to click into a text box
    pyautogui.write(text, interval=0.02)
    return "Typed the text."


def confirm(title, message):
    """Ask the user Yes/No. The UI replaces this with a popup window."""
    print(f"\n  {title}:\n{message}")
    return input("  Allow? (y/n): ").strip().lower() == "y"


def tool_run_command(command):
    if not confirm("JARVIS wants to run this command", command):
        return "User denied the command."
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip()[:2000] or "Done (no output)."
    except Exception as e:
        return f"Command failed: {e}"


def tool_run_python(code):
    shown = code if len(code) < 1500 else code[:1500] + "\n..."
    if not confirm("JARVIS wants to run this Python code", shown):
        return "User denied running the code."
    path = os.path.join(tempfile.gettempdir(), "jarvis_task.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        # same Python as Jarvis, so everything installed in the venv is available
        r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=HOME)
        out = (r.stdout + r.stderr).strip()
        return out[-4000:] or "Done (no output)."
    except subprocess.TimeoutExpired:
        return "The script took longer than 2 minutes and was stopped."
    except Exception as e:
        return f"Could not run the code: {e}"


# ----------------------------------------------------------------------------
# FILES
# ----------------------------------------------------------------------------
SPECIAL_FOLDERS = ("desktop", "downloads", "documents", "pictures", "music", "videos")
SKIP_DIRS = {"venv", ".venv", "node_modules", "__pycache__", "AppData", "$Recycle.Bin", ".git"}


def resolve_path(p):
    """Turn 'Downloads', '~/x' or a relative path into a full path."""
    p = os.path.expandvars(os.path.expanduser((p or "").strip().strip('"')))
    if not p:
        return HOME
    if os.path.isabs(p):
        return p
    first = p.replace("\\", "/").split("/")[0].lower()
    if first in SPECIAL_FOLDERS:
        # on many Windows PCs Desktop/Documents live inside OneDrive
        onedrive = os.path.join(HOME, "OneDrive", p)
        if not os.path.exists(os.path.join(HOME, p)) and os.path.exists(onedrive):
            return onedrive
    return os.path.join(HOME, p)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def tool_list_files(folder):
    path = resolve_path(folder)
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except Exception as e:
        return f"Could not open {path}: {e}"
    lines = [f"{path} ({len(entries)} items)"]
    for e in entries[:200]:
        try:
            lines.append(f"[folder] {e.name}" if e.is_dir()
                         else f"{e.name}  ({human_size(e.stat().st_size)})")
        except OSError:
            lines.append(e.name)
    if len(entries) > 200:
        lines.append(f"... and {len(entries) - 200} more")
    return "\n".join(lines)


def tool_find_files(name, folder=""):
    root = resolve_path(folder)
    needle = name.lower()
    found, start = [], time.time()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if needle in f.lower():
                found.append(os.path.join(dirpath, f))
                if len(found) >= 50:
                    return "\n".join(found) + "\n(stopped at 50 results)"
        if time.time() - start > 20:
            break
    return "\n".join(found) if found else f"No files matching '{name}' in {root}."


def tool_read_file(path):
    path = resolve_path(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(20001)
    except Exception as e:
        return f"Could not read {path}: {e}"
    return text[:20000] + ("\n... (file is longer, only the start is shown)" if len(text) > 20000 else "")


def tool_write_file(path, content):
    path = resolve_path(path)
    if os.path.exists(path) and not confirm("JARVIS wants to overwrite a file", path):
        return "User did not allow overwriting the file."
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Saved {path}"
    except Exception as e:
        return f"Could not write {path}: {e}"


def tool_move_file(source, destination):
    src, dst = resolve_path(source), resolve_path(destination)
    if not os.path.exists(src):
        return f"{src} does not exist."
    if not confirm("JARVIS wants to move a file", f"From: {src}\nTo:   {dst}"):
        return "User did not allow the move."
    try:
        return f"Moved to {shutil.move(src, dst)}"
    except Exception as e:
        return f"Could not move: {e}"


def run_tool(action, args):
    if action == "web_search":
        return tool_search(args.get("query", ""))
    if action == "weather":
        return tool_weather(args.get("city", ""))
    if action == "system_info":
        return tool_system_info()
    if action == "open_app":
        return tool_open_app(args.get("name", ""))
    if action == "open_url":
        return tool_open_url(args.get("url", ""))
    if action == "google_search":
        return tool_open_url("https://www.google.com/search?q=" +
                             urllib.parse.quote(args.get("query", "")))
    if action == "screenshot":
        return tool_screenshot()
    if action == "press_key":
        return tool_key(args.get("key", ""))
    if action == "type_text":
        return tool_type_text(args.get("text", ""))
    if action == "run_command":
        return tool_run_command(args.get("command", ""))
    if action == "run_python":
        return tool_run_python(args.get("code", ""))
    if action == "list_files":
        return tool_list_files(args.get("folder", ""))
    if action == "find_files":
        return tool_find_files(args.get("name", ""), args.get("folder", ""))
    if action == "read_file":
        return tool_read_file(args.get("path", ""))
    if action == "write_file":
        return tool_write_file(args.get("path", ""), args.get("content", ""))
    if action == "move_file":
        return tool_move_file(args.get("source", ""), args.get("destination", ""))
    return None


# ----------------------------------------------------------------------------
# BRAIN (uses the API's built-in tool calling)
# ----------------------------------------------------------------------------
def ask_model(messages):
    system = SYSTEM_PROMPT.replace("{today}", datetime.datetime.now().strftime("%A, %d %B %Y, %H:%M"))
    # gpt-oss models answer faster when asked to think less
    extra = {"reasoning_effort": "low"} if "gpt-oss" in MODEL else None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                tools=TOOLS,
                extra_body=extra,
            )
            return resp.choices[0].message
        except BadRequestError as e:
            # Groq rejects a badly formed tool call with "tool_use_failed"; one retry usually fixes it
            if attempt == 0 and "tool_use_failed" in str(e):
                continue
            raise


def recent_history(limit=30):
    """Last messages of the chat, always starting at a user message so tool replies stay paired."""
    start = max(0, len(history) - limit)
    while start > 0 and history[start]["role"] != "user":
        start -= 1
    return history[start:]


def think(user_text):
    history.append({"role": "user", "content": user_text})
    for _ in range(MAX_TOOL_STEPS):
        msg = ask_model(recent_history())

        if not msg.tool_calls:
            reply = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S).strip()
            history.append({"role": "assistant", "content": reply})
            return reply or "Sorry, I could not finish that."

        history.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls]})

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            print(f"  [{name}] {args}")
            result = run_tool(name, args)
            if result is None:
                result = f"Unknown tool: {name}"
            history.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})
    return "Sorry, I could not finish that."


# ----------------------------------------------------------------------------
# VOICE
# ----------------------------------------------------------------------------
def clean_for_speech(text):
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"[*_`#>]", "", text)


def speak(text):
    if not SPEAK_REPLIES or edge_tts is None or pygame is None:
        return
    try:
        lang = "en"
        if detect:
            lang = detect(text)
            lang = "zh" if lang.startswith("zh") else lang
        voice = VOICES.get(lang, VOICES["en"])
        path = os.path.join(tempfile.gettempdir(), "jarvis_voice.mp3")
        asyncio.run(edge_tts.Communicate(clean_for_speech(text), voice).save(path))
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"  (voice error: {e})")


def listen():
    if sr is None:
        print("  SpeechRecognition not installed; type instead.")
        return input("You: ")
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print(f"  Listening ({CURRENT_LANG})...")
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=8, phrase_time_limit=20)
        text = r.recognize_google(audio, language=STT_CODES.get(CURRENT_LANG, "en-US"))
        print(f"You: {text}")
        return text
    except Exception as e:
        print(f"  (could not hear you: {e})")
        return ""


# ----------------------------------------------------------------------------
# MAIN LOOP
# ----------------------------------------------------------------------------
HELP = """
Commands:
  /voice on|off   - use the microphone (press Enter, then speak)
  /lang xx        - microphone language: en ur hi zh ru ar
  /mute  /unmute  - turn spoken replies off / on
  /clear          - forget the conversation
  /quit           - exit
Or just type anything in any language. Example requests:
  "open notepad" | "what's the weather in Multan" | "latest cricket news"
  "take a screenshot" | "volume up" | "اردو میں بتاؤ آج کیا تاریخ ہے"
"""


def main():
    global client, API_KEY, SPEAK_REPLIES, USE_MICROPHONE, CURRENT_LANG
    if not API_KEY:
        API_KEY = input("Paste your Groq API key: ").strip()
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    print("=" * 60)
    print(" JARVIS online. Type /help for commands.")
    print("=" * 60)
    speak("Jarvis online. How can I help you?")

    while True:
        try:
            if USE_MICROPHONE:
                input("\n[Press Enter and speak] ")
                user = listen()
            else:
                user = input("\nYou: ")
        except (EOFError, KeyboardInterrupt):
            break

        user = (user or "").strip()
        if not user:
            continue

        if user.startswith("/"):
            parts = user.split()
            cmd = parts[0].lower()
            if cmd == "/quit":
                break
            elif cmd == "/help":
                print(HELP)
            elif cmd == "/clear":
                history.clear()
                print("Memory cleared.")
            elif cmd == "/mute":
                SPEAK_REPLIES = False
            elif cmd == "/unmute":
                SPEAK_REPLIES = True
            elif cmd == "/voice" and len(parts) > 1:
                USE_MICROPHONE = parts[1] == "on"
                print("Microphone", "ON" if USE_MICROPHONE else "OFF")
            elif cmd == "/lang" and len(parts) > 1 and parts[1] in STT_CODES:
                CURRENT_LANG = parts[1]
                print("Microphone language:", CURRENT_LANG)
            else:
                print("Unknown command. Type /help")
            continue

        try:
            print("Jarvis is thinking...")
            reply = think(user)
            print(f"\nJarvis: {reply}")
            speak(reply)
        except Exception as e:
            print(f"Error: {e}")

    print("Goodbye.")


if __name__ == "__main__":
    main()
