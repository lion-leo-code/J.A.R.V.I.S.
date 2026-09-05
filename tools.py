"""
JARVIS Tool Registry — Full Implementation

Storage: ALL files use JARVIS_DIR = C:\\Users\\aniak\\Documents\\J.A.R.V.I.S
Email:   akshay.banga09@gmail.com / Gmail App Password / smtp.gmail.com:587
Search:  SerpAPI (optional) → DuckDuckGo scraping fallback
Apps:    5-strategy Windows launcher with learned path cache
"""

import os
import sys
import shutil
import platform
import subprocess
import logging
import pathlib
import time
import re
import html
import json
import urllib.request
import urllib.parse
from typing import Dict, Callable, Any, Optional
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from email.message import EmailMessage
import base64

logger = logging.getLogger("jarvis.tools")

def _get_google_service(api_name, api_version):
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.compose', 
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/calendar'
    ]
    creds = None
    
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            # FIX: We use 127.0.0.1 and a specific port. 
            # This is the "Desktop App" standard that Google expects.
            creds = flow.run_local_server(
                host='127.0.0.1', 
                port=8080, 
                open_browser=True,
                authorization_prompt_message='JARVIS is authenticating...'
            )
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build(api_name, api_version, credentials=creds)


# ── Global storage directory (set from builtins by main.py) ──────────────────
def _jarvis_dir() -> pathlib.Path:
    """Return JARVIS_DIR — from builtins (set by main.py) or a safe default."""
    try:
        import builtins
        if hasattr(builtins, "JARVIS_DIR"):
            d = builtins.JARVIS_DIR
            d.mkdir(parents=True, exist_ok=True)
            return d
    except Exception:
        pass
    fallback = pathlib.Path.home() / "JARVIS"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# ── Module-level config ───────────────────────────────────────────────────────
_EMAIL_CFG:  dict = {}
_SEARCH_CFG: dict = {}
_VOICE_CFG:  dict = {}
_CONFIRM_CB: Optional[Callable[[str], bool]] = None

_SYSTEM = platform.system()

# ── Learned app paths cache (persisted between runs) ─────────────────────────
def _app_cache_path() -> pathlib.Path:
    return _jarvis_dir() / "app_paths.json"

def _load_app_cache() -> dict:
    p = _app_cache_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_app_cache(cache: dict):
    try:
        _app_cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[Tools] Could not save app cache: {e}")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  APP LAUNCHER — 5-STRATEGY WINDOWS LAUNCHER                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Common application name → executable mappings for Windows
_WIN_APP_ALIASES = {
    "notepad":       "notepad.exe",
    "notepad++":     "notepad++.exe",
    "chrome":        "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox":       "firefox.exe",
    "opera":         "opera.exe",
    "edge":          "msedge.exe",
    "microsoft edge":"msedge.exe",
    "steam":         "steam.exe",
    "whatsapp":      "whatsapp.exe",
    "discord":       "discord.exe",
    "spotify":       "spotify.exe",
    "vscode":        "code.exe",
    "visual studio code": "code.exe",
    "code":          "code.exe",
    "explorer":      "explorer.exe",
    "calculator":    "calc.exe",
    "calc":          "calc.exe",
    "paint":         "mspaint.exe",
    "word":          "winword.exe",
    "excel":         "excel.exe",
    "powerpoint":    "powerpnt.exe",
    "outlook":       "outlook.exe",
    "teams":         "teams.exe",
    "zoom":          "zoom.exe",
    "vlc":           "vlc.exe",
    "cmd":           "cmd.exe",
    "powershell":    "powershell.exe",
    "terminal":      "wt.exe",
    "taskmgr":       "taskmgr.exe",
    "task manager":  "taskmgr.exe",
    "control panel": "control.exe",
    "settings":      "ms-settings:",
    "obs":           "obs64.exe",
    "blender":       "blender.exe",
    "gimp":          "gimp-2.10.exe",
    "telegram":      "telegram.exe",
    "skype":         "skype.exe",
}

# Common install path roots to search for executables
_WIN_SEARCH_ROOTS = [
    pathlib.Path(r"C:\Program Files"),
    pathlib.Path(r"C:\Program Files (x86)"),
    pathlib.Path(os.environ.get("LOCALAPPDATA", r"C:\Users\aniak\AppData\Local")),
    pathlib.Path(os.environ.get("APPDATA", r"C:\Users\aniak\AppData\Roaming")),
    pathlib.Path(r"C:\Users\aniak\AppData\Local\Programs"),
    pathlib.Path(r"C:\Users\aniak\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
]


def _find_exe_in_path(exe_name: str) -> Optional[str]:
    """Search PATH environment for an executable."""
    import shutil as sh
    found = sh.which(exe_name)
    return found


def _search_install_dirs(app_name: str) -> Optional[str]:
    """
    Search common Windows install directories for the app executable.
    Tries both the alias lookup and a directory name search.
    """
    key = app_name.lower().strip()
    exe = _WIN_APP_ALIASES.get(key, "")

    # Also try adding .exe if no extension
    candidates = []
    if exe:
        candidates.append(exe)
    if not key.endswith(".exe"):
        candidates.append(key + ".exe")
    candidates.append(key)

    for root in _WIN_SEARCH_ROOTS:
        if not root.exists():
            continue
        try:
            # Check direct files in root
            for c in candidates:
                direct = root / c
                if direct.exists() and direct.is_file():
                    return str(direct)

            # Walk one level deep (app folder → exe)
            for subdir in root.iterdir():
                if not subdir.is_dir():
                    continue
                # Check if subdir name contains the app name
                if key.replace(" ", "").replace("-", "") in \
                        subdir.name.lower().replace(" ", "").replace("-", ""):
                    for c in candidates:
                        candidate = subdir / c
                        if candidate.exists():
                            return str(candidate)
                    # Try any .exe in this folder
                    for f in subdir.glob("*.exe"):
                        if key.split()[0] in f.stem.lower():
                            return str(f)
        except (PermissionError, OSError):
            continue

    return None


def tool_open_app(name: str = "", **kwargs) -> dict:
    """Strategy 3 (Windows Start) is the most reliable. **kwargs absorbs LLM garbage."""
    if not name:
        name = kwargs.get("app", kwargs.get("query", ""))
    if not name:
        return {"success": False, "output": "No app name provided."}
    
    exe = _WIN_APP_ALIASES.get(name.lower().strip(), name.strip())
    
    try:
        if _SYSTEM == "Windows":
            # Using 'start "" "app"' routes through Windows Registry correctly
            subprocess.Popen(f'start "" "{exe}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "output": f"Sent launch command for {name}."}
        else:
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "output": f"Opening {name}."}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FILE SYSTEM — ALL paths rooted in JARVIS_DIR                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _resolve(path: str, must_exist: bool = False) -> pathlib.Path:
    """
    Resolve a path. Relative paths are placed inside JARVIS_DIR.
    Absolute paths are used as-is.
    """
    p = pathlib.Path(path).expanduser()
    if not p.is_absolute():
        p = _jarvis_dir() / p
    if must_exist and not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p


def tool_close_app(name: str) -> dict:
    try:
        if _SYSTEM == "Windows":
            exe = _WIN_APP_ALIASES.get(name.lower(), name)
            if not exe.endswith(".exe"):
                exe += ".exe"
            subprocess.run(["taskkill", "/IM", exe, "/F"],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(["pkill", "-f", name], capture_output=True, timeout=5)
        return {"success": True, "output": f"Closed {name}."}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_list_files(path: str = "") -> dict:
    try:
        p = _resolve(path) if path else _jarvis_dir()
        if not p.exists():
            return {"success": False, "output": "", "error": f"Path not found: {p}"}
        if p.is_file():
            return {"success": True, "output": f"{p} — {p.stat().st_size:,} bytes"}
        entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines   = []
        for e in entries[:60]:
            icon = "📁" if e.is_dir() else "📄"
            size = f"  ({e.stat().st_size:,} B)" if e.is_file() else ""
            lines.append(f"{icon} {e.name}{size}")
        total   = sum(1 for _ in p.iterdir())
        summary = f"{p}  ({total} items):\n" + "\n".join(lines)
        if total > 60:
            summary += f"\n  … and {total - 60} more"
        return {"success": True, "output": summary}
    except PermissionError:
        return {"success": False, "output": "", "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_create_dir(path: str) -> dict:
    try:
        p = _resolve(path)
        p.mkdir(parents=True, exist_ok=True)
        return {"success": True, "output": f"Directory created: {p}"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_move_file(src: str, dst: str) -> dict:
    try:
        sp = _resolve(src, must_exist=True)
        dp = _resolve(dst)
        shutil.move(str(sp), str(dp))
        return {"success": True, "output": f"Moved {sp.name} → {dp}"}
    except FileNotFoundError as e:
        return {"success": False, "output": "", "error": str(e)}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_copy_file(src: str, dst: str) -> dict:
    try:
        sp = _resolve(src, must_exist=True)
        dp = _resolve(dst)
        shutil.copytree(str(sp), str(dp)) if sp.is_dir() else shutil.copy2(str(sp), str(dp))
        return {"success": True, "output": f"Copied {sp.name} → {dp}"}
    except FileNotFoundError as e:
        return {"success": False, "output": "", "error": str(e)}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_delete_file(path: str) -> dict:
    """Delete — always requests confirmation."""
    try:
        p = _resolve(path, must_exist=True)
        if _CONFIRM_CB:
            if not _CONFIRM_CB(f"Permanently delete '{p}'?"):
                return {"success": False, "output": "Cancelled — nothing deleted.", "error": None}
        shutil.rmtree(str(p)) if p.is_dir() else p.unlink()
        return {"success": True, "output": f"Deleted: {p.name}"}
    except FileNotFoundError as e:
        return {"success": False, "output": "", "error": str(e)}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_read_file(path: str, max_chars: int = 4000) -> dict:
    try:
        p = _resolve(path, must_exist=True)
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n… [truncated — {len(content):,} total chars]"
        return {"success": True, "output": content}
    except FileNotFoundError as e:
        return {"success": False, "output": "", "error": str(e)}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_write_file(path: str = "", content: str = "") -> dict:
    """
    Write a file — always in JARVIS_DIR.
    If path is just a filename, saves to JARVIS_DIR/filename.
    """
    try:
        p = _resolve(path if path else "output.txt")
        # Confirm overwrite only for existing non-empty files
        if p.exists() and p.stat().st_size > 0 and _CONFIRM_CB:
            if not _CONFIRM_CB(f"Overwrite existing file '{p.name}'?"):
                return {"success": False, "output": "Cancelled — file unchanged.", "error": None}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "output": f"File saved: {p}\n({len(content):,} characters)"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_run_command(cmd: str = "", timeout: int = 10) -> dict:
    dangerous_patterns = ["rm -rf", "del /f", "format c:", "mkfs", "dd if=",
                          "shutdown", "reboot", "rmdir /s", "rd /s /q"]
    is_dangerous = any(kw in cmd.lower() for kw in dangerous_patterns)
    if is_dangerous and _CONFIRM_CB:
        if not _CONFIRM_CB(f"Run this command?\n  {cmd}"):
            return {"success": False, "output": "Cancelled by user.", "error": None}
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if len(output) > 3000:
            output = output[:3000] + "\n… [truncated]"
        return {
            "success": result.returncode == 0,
            "output":  output or "(no output)",
            "error":   None if result.returncode == 0 else f"Exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def tool_get_sysinfo() -> dict:
    try:
        import psutil
        cpu   = psutil.cpu_percent(interval=0.4)
        mem   = psutil.virtual_memory()
        disk  = psutil.disk_usage("C:\\" if _SYSTEM == "Windows" else "/")
        bat   = psutil.sensors_battery()
        bat_s = (f"\nBattery: {bat.percent:.0f}%  "
                 f"{'charging ⚡' if bat.power_plugged else 'on battery'}"
                 ) if bat else ""
        out = (
            f"OS:     {platform.system()} {platform.release()}\n"
            f"CPU:    {cpu:.1f}%  ({psutil.cpu_count()} cores)\n"
            f"RAM:    {mem.percent:.1f}%  ({mem.used/1e9:.1f} / {mem.total/1e9:.1f} GB)\n"
            f"Disk:   {disk.percent:.1f}%  ({disk.used/1e9:.1f} / {disk.total/1e9:.1f} GB)"
            f"{bat_s}\nPython: {sys.version.split()[0]}"
        )
    except ImportError:
        out = (f"OS: {platform.system()} {platform.release()}\n"
               f"Python: {sys.version.split()[0]}\n"
               "(pip install psutil for detailed stats)")
    return {"success": True, "output": out}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  SCREENSHOT — saves to JARVIS_DIR                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def tool_take_screenshot() -> dict:
    """Take a screenshot and save it to JARVIS_DIR."""
    try:
        ts      = int(time.time())
        outfile = _jarvis_dir() / f"screenshot_{ts}.png"

        if _SYSTEM == "Windows":
            # PowerShell screenshot — reliable, no extra deps
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "Add-Type -AssemblyName System.Drawing;"
                "$s=[System.Windows.Forms.Screen]::PrimaryScreen;"
                "$b=New-Object System.Drawing.Bitmap($s.Bounds.Width,$s.Bounds.Height);"
                "$g=[System.Drawing.Graphics]::FromImage($b);"
                "$g.CopyFromScreen([System.Drawing.Point]::Empty,"
                "[System.Drawing.Point]::Empty,$s.Bounds.Size);"
                f"$b.Save('{outfile}');"
                "$g.Dispose();$b.Dispose()"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or "PowerShell screenshot failed")

        elif _SYSTEM == "Darwin":
            subprocess.run(["screencapture", "-x", str(outfile)], check=True, timeout=10)
        else:
            # Try scrot, then gnome-screenshot
            try:
                subprocess.run(["scrot", str(outfile)], check=True, timeout=10)
            except Exception:
                subprocess.run(["gnome-screenshot", "-f", str(outfile)], check=True, timeout=10)

        if not outfile.exists():
            raise RuntimeError(f"Screenshot file not created at {outfile}")

        size_kb = outfile.stat().st_size // 1024
        return {
            "success": True,
            "output": f"Screenshot saved to:\n{outfile}\n({size_kb} KB)"
        }
    except Exception as e:
        logger.error(f"[Tools/Screenshot] {e}")
        return {"success": False, "output": "", "error": str(e)}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  EMAIL — Preview + Signature + Edit + Send                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

DEFAULT_SIGNATURE = (
    "\n\n-----\n"
    "Message relayed via J.A.R.V.I.S. protocols.\n\n"
    "Standing by for your response,\n"
    "Akshay"
)

def tool_send_email(to: str = "", subject: str = "", body: str = "", confirmed: bool = False, **kwargs) -> dict:
    """
    Two-stage logic: 
    1. If NOT confirmed: Return the DRAFT text to the result bar.
    2. If confirmed: Trigger the HUD buttons and send.
    """
    if not to or not subject or not body:
        return {"success": False, "output": "Protocol requires recipient, subject, and body."}

    full_body = body + DEFAULT_SIGNATURE
    preview_text = (
        "DRAFT\n"
        "-----------------------------------\n"
        f"TO: {to}\n"
        f"SUBJECT: {subject}\n"
        "-----------------------------------\n"
        f"{full_body}"
    )

    # STAGE 2: THE SENDING LOGIC (Triggers after the preview is already visible)
    if confirmed:
        try:
            if _CONFIRM_CB:
                # The HUD buttons appear now
                is_ok = _CONFIRM_CB("INITIATE EMAIL TRANSMISSION?")
                
                if is_ok:
                    service = _get_google_service('gmail', 'v1')
                    msg = EmailMessage()
                    msg.set_content(full_body)
                    msg['To'] = to
                    msg['Subject'] = subject
                    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                    
                    service.users().messages().send(userId='me', body={'raw': raw}).execute()
                    return {"success": True, "output": f"[SYSTEM]: Transmission successful. Sent to {to}."}
                else:
                    return {"success": False, "output": "[SYSTEM]: Transmission aborted by user."}
            
            return {"success": False, "output": "HUD confirmation system not found."}
        except Exception as e:
            return {"success": False, "error": f"Gmail Protocol Error: {str(e)}"}

    # STAGE 1: THE PREVIEW (This runs first)
    # This returns the text to the 'result bar' and stops.
    return {
        "success": True, 
        "output": preview_text, 
        "needs_user_input": True 
    }

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  WEB SEARCH — SerpAPI + DuckDuckGo fallback                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def tool_web_search(query: str = "") -> dict:
    query = str(query).strip()
    if not query:
        return {"success": False, "output": "", "error": "Empty search query"}

    # SerpAPI (if key configured)
    api_key = _SEARCH_CFG.get("serpapi_key", "").strip()
    if api_key:
        try:
            params = urllib.parse.urlencode({
                "engine": "google", "q": query, "api_key": api_key, "num": 5,
            })
            req = urllib.request.Request(
                f"https://serpapi.com/search?{params}",
                headers={"User-Agent": "JARVIS/4.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            hits = []
            for r in data.get("organic_results", [])[:4]:
                t, s = r.get("title", ""), r.get("snippet", "")
                if t and s:
                    hits.append(f"• {t}\n  {s}")
            if hits:
                return {"success": True,
                        "output": f"Results for \"{query}\":\n\n" + "\n\n".join(hits)}
        except Exception as e:
            logger.warning(f"[Tools/Search] SerpAPI failed ({e}), trying DuckDuckGo")

    # DuckDuckGo fallback
    try:
        encoded = urllib.parse.quote_plus(query)
        url     = f"https://html.duckduckgo.com/html/?q={encoded}"
        req     = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; JARVIS/4.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")

        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.DOTALL)[:5]
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>',       body, re.DOTALL)[:5]
        hits     = []
        for t, s in zip(titles, snippets):
            t = html.unescape(re.sub(r'<[^>]+>', '', t)).strip()
            s = html.unescape(re.sub(r'<[^>]+>', '', s)).strip()
            if t and s:
                hits.append(f"• {t}\n  {s}")

        if hits:
            return {"success": True,
                    "output": f"Results for \"{query}\":\n\n" + "\n\n".join(hits)}
        return {"success": True, "output": f"No results found for: {query}"}
    except Exception as e:
        return {"success": False, "output": "", "error": f"Search failed: {e}"}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  CALENDAR                                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def tool_calendar(action: str = "list", summary: str = "", time: str = "", **kwargs) -> dict:
    """Uses credentials.json to list or add events."""
    try:
        service = _get_google_service('calendar', 'v3')
        
        if action.upper() == "ADD":
            if not summary or not time:
                return {"success": False, "output": "I need both an event summary and a time to add it."}
            event_body = {
                'summary': summary,
                'start': {'dateTime': time, 'timeZone': 'Asia/Kolkata'},
                'end': {'dateTime': time, 'timeZone': 'Asia/Kolkata'},
            }
            service.events().insert(calendarId='primary', body=event_body).execute()
            return {"success": True, "output": f"Added '{summary}' to your Calendar."}
        
        # Default behavior: List upcoming events
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=3, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        if not events:
            return {"success": True, "output": "You have no upcoming events."}
            
        out_str = "Upcoming Schedule:\n"
        for e in events:
            start_val = e['start'].get('dateTime', e['start'].get('date'))
            out_str += f"- {start_val}: {e['summary']}\n"
            
        return {"success": True, "output": out_str}
    except Exception as e:
        return {"success": False, "output": "", "error": f"Calendar API Error: {str(e)}"}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  VOICE INPUT                                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def tool_listen_voice(duration: int = 6) -> dict:
    if not _VOICE_CFG.get("input_enabled", False):
        return {"success": False, "output": "", "error": "Voice input disabled in config."}
    try:
        import speech_recognition as sr   # type: ignore
        r = sr.Recognizer()
        r.energy_threshold = 300
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, duration=0.4)
            audio = r.listen(src, timeout=duration, phrase_time_limit=duration)
        text = r.recognize_google(audio)
        return {"success": True, "output": text}
    except ImportError:
        return {"success": False, "output": "",
                "error": "Install: pip install SpeechRecognition pyaudio"}
    except Exception as e:
        return {"success": False, "output": "", "error": f"Voice failed: {e}"}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  UTILITY                                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def tool_ask_user(prompt: str) -> dict:
    return {"success": True, "output": prompt, "needs_user_input": True}

def tool_answer(text: str) -> dict:
    return {"success": True, "output": text}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL REGISTRY                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class ToolRegistry:

    def __init__(self, config: dict):
        global _EMAIL_CFG, _SEARCH_CFG, _VOICE_CFG
        self._handlers: Dict[str, Callable] = {}
        self._config    = config

        _EMAIL_CFG  = config.get("email",      {})
        _SEARCH_CFG = config.get("web_search", {})
        _VOICE_CFG  = config.get("voice",      {})

        self._register_all()
        logger.info(f"[Tools] {len(self._handlers)} tools registered")

    def _register_all(self):
        self.register("OPEN_APP",           tool_open_app)
        self.register("CLOSE_APP",          tool_close_app)
        self.register("LIST_FILES",         tool_list_files)
        self.register("CREATE_DIR",         tool_create_dir)
        self.register("MOVE_FILE",          tool_move_file)
        self.register("COPY_FILE",          tool_copy_file)
        self.register("DELETE_FILE",        tool_delete_file)
        self.register("READ_FILE",          tool_read_file)
        self.register("WRITE_FILE",         tool_write_file)
        self.register("RUN_COMMAND",        tool_run_command)
        self.register("GET_SYSINFO",        tool_get_sysinfo)
        self.register("TAKE_SCREENSHOT",    tool_take_screenshot)
        self.register("SEND_EMAIL",         tool_send_email)
        self.register("WEB_SEARCH",         tool_web_search)
        self.register("CALENDAR",           tool_calendar)
        self.register("LISTEN_VOICE",       tool_listen_voice)
        self.register("ASK_USER",           tool_ask_user)
        self.register("ANSWER",             tool_answer)

    def register(self, name: str, fn: Callable):
        self._handlers[name.upper()] = fn

    def get_handler(self, name: str) -> Optional[Callable]:
        return self._handlers.get(name.upper())

    def set_confirm_callback(self, cb: Callable[[str], bool]):
        global _CONFIRM_CB
        _CONFIRM_CB = cb

    def list_tools(self) -> list:
        return sorted(self._handlers.keys())
