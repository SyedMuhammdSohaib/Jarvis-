# J.A.R.V.I.S

A personal desktop assistant for Windows, with voice, a themed UI and PC control. It runs on an AI model hosted by Groq.

## Features
- Chat in English, Urdu, Hindi, Chinese, Russian and Arabic (type or speak)
- Speaks replies aloud (male/female voice, slow/normal/fast)
- Live info: web search, weather, date/time, system info
- PC control: open apps and websites, play YouTube, screenshots, volume and media keys, typing text, lock, screen off, restart/shutdown
- Shell commands (always asks you first)
- Themes: Blue, Iron Man, Matrix

## Setup (Windows)
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
```
Put your Groq API key in `.env` (get it from https://console.groq.com/keys). **Never paste the key into the code**, because `.env` is kept out of GitHub but the code is not.

## Run
- With the window: `python jarvis_ui.py` (or double-click `start_jarvis.bat`)
- In the terminal: `python jarvis.py`

## Files
| File | What it does |
|---|---|
| `jarvis.py` | Brain, tools, voice and the terminal version |
| `jarvis_extras.py` | Extra tools (YouTube, lock, power, themes, voices) and faster speech |
| `jarvis_ui.py` | Desktop window |
| `jarvis_settings.json` | Your saved theme, voice and language |

## Adding a new tool
1. Write a function, e.g. `def tool_joke(): ...`
2. Add its definition to `TOOLS` in `jarvis.py` with the `tool(...)` helper
3. Add a line for it in `run_tool`

## Roadmap
- [x] Built-in tool calling
- [ ] Long-term memory
- [ ] "Hey Jarvis" wake word
- [ ] Reminders and alarms
