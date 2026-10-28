# Vega - personal AI assistant for Windows

A JARVIS-style desktop assistant: talk to it, hear it answer, and let it operate your PC through real Windows tools.
Python 3.10-3.12 + PySide6. Rename it and change its personality in Settings.

## Install and run (Windows 10/11)
```bat
setup.bat      :: creates .venv and installs requirements.txt
run.bat        :: starts Vega (no console window)
```
Manual equivalent:
```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
First launch: click the gear icon > **AI**, pick a provider, paste your API key, press **Test connection**, **Save**.
Keys go to Windows Credential Manager (or environment variables `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` /
`OPENROUTER_API_KEY`) - never into files. Ollama needs no key.
The first time the mic starts, the speech model (~150 MB) downloads once, then speech recognition runs locally.

## Build the .exe
```bat
build.bat      :: -> dist\Vega\Vega.exe  (keep the whole dist\Vega folder)
```
Then in Vega: Settings > Startup & data > **Create desktop shortcut**, and tick **Start with Windows**.

## Using it
* The mic button toggles hands-free mode: just talk. It detects when you stop, thinks, and answers aloud.
* Talk over it to interrupt (use headphones, otherwise its own voice can trigger this; sensitivity is adjustable).
* Typing works too. Status shows IDLE / LISTENING / THINKING / SPEAKING; ■ stops speech and cancels the task.
* Optional wake word: Settings > Microphone > "Require the assistant's name".
* Examples: "Open Chrome." "Open Roblox Studio." "Open Discord and show my messages." "Search the internet for ..."
  "Find my resume in Documents." "Create a folder called Projects on my desktop." "Remind me in 20 minutes to stretch."
  "Take a screenshot." "Switch to Discord." "Close this application." "Tell Alex on Discord I'm running late."

## Safety model
* Always asks first (dialog, or say "yes"/"no"): sending messages, moving/deleting files (Recycle Bin), organizing folders,
  running commands/scripts, installing software (winget), force-quitting, overwriting files.
* Settings > Permissions switches whole tool categories off (the model doesn't even see those tools).
* It never bypasses UAC, passwords or app permissions; commands touching Defender/UAC/boot settings are blocked.
* Messaging works by driving **your own logged-in desktop app** with keyboard shortcuts (no tokens or unofficial APIs).
  It is best-effort: app UIs change, so glance at the screen. Supported: Discord, Slack, WhatsApp, Teams, Telegram.
* Scripts only run from `%APPDATA%\Vega\scripts`.

## Layout
```
main.py                     entry point
vega/app.py                 QApplication, tray, single-instance
vega/controller.py          mic -> STT -> agent -> TTS state machine, confirmations, reminders
vega/ai/                    providers.py (OpenAI-compatible + Anthropic), agent.py loop, prompts.py
vega/voice/                 audio_in.py (VAD + barge-in), stt.py (faster-whisper), tts.py (edge-tts / Windows SAPI)
vega/tools/                 base.py (registry), apps, files, web, input_tools, messaging, shell, system_tools, winutil
vega/ui/                    main_window, orb (animation), settings_dialog, confirm_dialog, theme
tests/                      pytest suite  (pip install pytest; python -m pytest)
```
Data lives in `%APPDATA%\Vega` (settings.json, vega.db history, vega.log, models, scripts, plugins).

## Writing tools
```python
from vega.tools import tool, P

@tool("Describe what it does", {"city": P("string", "City name")}, ["city"], category="web",
      confirm=lambda a: f"Do X for {a['city']}?")   # optional: forces a user confirmation
def my_tool(ctx, city):
    return f"OK: ..."          # start with OK / ERROR so the model reports honestly
```
Put the file in `%APPDATA%\Vega\plugins` (see `examples/example_plugin.py`) or add a module under `vega/tools/`
and import it in `vega/tools/__init__.py`.

## Troubleshooting
* "couldn't open the microphone": Windows Settings > Privacy > Microphone > allow desktop apps; pick the device in Settings.
* Voice sounds robotic / "using the Windows voice": the neural voice needs internet; switch engine in Settings > Voice.
* Replies cut itself off: lower microphone sensitivity or wear headphones.
* Non-English: Settings > Microphone > language (e.g. `ar`) and a non-.en speech model (`base`/`small`).
* Logs: `%APPDATA%\Vega\vega.log`.
