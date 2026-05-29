# JARVIS — AI Desktop Assistant

> *"Sometimes you gotta run before you can walk."*

A production-quality, JARVIS-inspired AI assistant with a futuristic HUD interface,
global hotkey activation, multi-step task planning, and real system control.

---

## Architecture Overview

```
main.py           Entry point — wires all subsystems together
ui.py             PyQt6 HUD overlay with animations & glass morphism
hotkey.py         Global keyboard listener (daemon thread)
brain.py          LLM orchestration via Anthropic API + fallback
planner.py        Converts LLM intent → ordered TaskStep queue
executor.py       Dispatches each step to the correct tool
tools.py          All system actions (files, apps, shell, web, etc.)
memory.py         SQLite persistence (history, preferences)
safety.py         Blocks dangerous commands/paths before execution
config.json       All runtime configuration
requirements.txt  Python dependencies
```

**Data flow:**
```
User types command
  → Brain._call_llm()        (Anthropic API)
  → Brain._parse_response()  (JSON task or plain text)
  → Planner.execute_plan()   (step queue)
  → Executor.run()           (per step)
  → ToolRegistry.get_handler() (dispatch)
  → Tool function            (actual system action)
  → Result bubbles back to HUD
```

---

## Quick Setup

### 1. Install dependencies

```bash
cd jarvis/
pip install -r requirements.txt
```

> **Linux note:** The `keyboard` library requires either root or a udev rule:
> ```bash
> sudo pip install keyboard
> # OR run with: sudo python main.py
> # OR add yourself to the `input` group (see keyboard docs)
> ```

### 2. Set your Anthropic API key

**Option A — Environment variable (recommended):**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python main.py
```

**Option B — config.json:**
```json
{
  "anthropic_api_key": "sk-ant-..."
}
```

> Without an API key, JARVIS runs in **offline/rule-based mode**  
> supporting basic commands (open app, list files, system info, web search).

### 3. Run

```bash
python main.py
```

---

## Hotkey Configuration

Edit `config.json`:

```json
"hotkey": {
  "trigger": "ctrl+space"
}
```

**Examples:**
| Trigger       | config value    |
|---------------|-----------------|
| Ctrl+Space    | `ctrl+space`    |
| F2            | `f2`            |
| Win+C         | `win+c`         |
| Alt+J         | `alt+j`         |
| Insert        | `insert`        |

Press the trigger **anywhere** (even in other apps) to show/hide JARVIS.  
Press **ESC** inside the HUD to dismiss it.

---

## Example Commands

### Direct answers
```
What is 512 * 1024?
What time is it in Tokyo?
Explain quantum entanglement briefly
```

### File operations
```
List files in my Downloads folder
Create a folder called Projects in my Desktop
Show me what's in ~/Documents
```

### App control
```
Open Chrome
Open terminal
Close Spotify
```

### System info
```
Show system info
How much RAM am I using?
```

### Web search
```
Search for Python asyncio best practices
Search for latest news on AI
```

### Multi-step tasks (requires API key)
```
Organize my Downloads folder by file type
Create a project structure for a Python web app in ~/Projects/myapp
Find all log files in /var/log and list their sizes
```

### Shell commands
```
Run: ls -la ~/Desktop
Run: pip list
Run: git status
```

---

## Extending JARVIS with New Tools

### Add a tool function in `tools.py`:

```python
def tool_send_email(to: str, subject: str, body: str) -> dict:
    """Send an email."""
    import smtplib
    # ... your implementation
    return {"success": True, "output": f"Email sent to {to}"}
```

### Register it in `ToolRegistry.register_all()`:

```python
self.register("SEND_EMAIL", tool_send_email)
```

### Tell the LLM about it by updating `SYSTEM_PROMPT` in `brain.py`:

```
- SEND_EMAIL: {"to": "...", "subject": "...", "body": "..."} — send an email
```

That's it — JARVIS will now use your tool automatically.

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `anthropic_api_key` | `""` | API key (or use env var) |
| `model` | `claude-opus-4-5` | Anthropic model to use |
| `context_turns` | `6` | Conversation history turns to send |
| `hotkey.trigger` | `ctrl+space` | Global activation hotkey |
| `show_on_start` | `false` | Show HUD immediately on launch |
| `safety.allow_destructive` | `false` | Allow DELETE without extra check |
| `planner.stop_on_failure` | `false` | Abort plan if a step fails |
| `memory.db_path` | `~/.jarvis/memory.db` | SQLite database location |

---

## Optional Enhancements

| Feature | How to add |
|---------|-----------|
| Voice input | Install `openai-whisper`, add mic recording to `ui.py` |
| Text-to-speech | Install `pyttsx3`, call `engine.say()` after each response |
| System tray | Use `PyQt6.QtWidgets.QSystemTrayIcon` in `main.py` |
| Startup on boot | Add `python /path/to/main.py` to your OS autostart |
| Local LLM | Install Ollama + swap `brain.py` client to `openai` pointed at localhost |
| Wake word | Add `pvporcupine` for "Hey JARVIS" detection |

---

## File & Data Locations

```
~/.jarvis/
├── memory.db      SQLite database (command history, preferences)
└── jarvis.log     Application log
```

---

## Troubleshooting

**HUD doesn't appear:**
- Make sure PyQt6 is installed: `pip install PyQt6`
- Check logs: `tail -f ~/.jarvis/jarvis.log`

**Hotkey doesn't work:**
- Linux: run as root or configure udev input group
- macOS: grant Accessibility permissions in System Preferences → Security & Privacy
- Windows: run as Administrator if needed

**"No API key" message:**
- Set `ANTHROPIC_API_KEY` env var or add to `config.json`
- Rule-based mode still works for basic commands

**Import errors:**
```bash
pip install --upgrade PyQt6 keyboard anthropic psutil
```
