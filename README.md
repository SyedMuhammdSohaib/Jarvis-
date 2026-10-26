# JARVIS 🤖

A personal AI assistant, inspired by Iron Man's JARVIS, powered by Claude.

## Abhi kya kar sakta hai (Step 1)
- Text me baat karna (English / Urdu / Roman Urdu)
- Time batana
- Kisi bhi shehar ka mausam batana
- Apps kholna (notepad, chrome, VS Code...)
- Websites kholna aur Google search karna
- Aapke baare mein baatein yaad rakhna (`memory.json`)

## Setup
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
copy .env.example .env       # Windows  (Mac/Linux: cp .env.example .env)
```
`.env` file mein apni API key daalein (https://console.anthropic.com se milegi), phir:
```bash
python main.py
```

### Try karein
- `Hello Jarvis, mera naam Sohaib hai aur main developer hoon`
- `Karachi ka mausam kaisa hai?`
- `Notepad kholo`
- `YouTube pe Iron Man trailer search karo`

## Project structure
```
main.py          # chat loop
brain.py         # Claude + tools
tools/
  web.py         # time, weather
  system.py      # apps, websites, search
  memory.py      # remember / recall
```

## Roadmap
- [x] Step 1: text chat + tools + memory
- [ ] Step 2: voice (speech-to-text with faster-whisper, speech with edge-tts)
- [ ] Step 3: "Hey Jarvis" wake word
- [ ] Step 4: Gmail, reminders, Telegram bot
- [ ] Step 5: Iron Man style UI
