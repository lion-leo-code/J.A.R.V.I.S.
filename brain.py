"""
JARVIS Brain — Complete Pipeline
Ollama LLM (llama3.2) with 12-second hard timeout.
Handles: direct answers, task planning, incomplete-command prompting.
Generates jarvis_requirements.txt on every startup.
Natural JARVIS personality — no prefixes, no labels.
"""

import json
import logging
import re
import sys
import os
import platform
import urllib.request
import urllib.error
from typing import Callable, Optional, List

logger = logging.getLogger("jarvis.brain")

# Hard ceiling for LLM call — matches config ollama_timeout: 12
LLM_TIMEOUT = 12

SYSTEM_PROMPT = """You are JARVIS, a sophisticated AI desktop assistant.
Personality: confident, efficient, occasionally witty — like JARVIS from Iron Man.
Speak naturally. Never use prefixes like "[JARVIS] ->", "Assistant:", or labels of any kind.

Decide how to respond:

━━━ A) DIRECT ANSWER ━━━
For greetings, facts, questions, calculations, opinions:
Reply with natural plain text only. No JSON.

━━━ B) INCOMPLETE COMMAND ━━━
If the user's intent is clear but required parameters are missing:
Reply ONLY with this JSON (no other text):
{"type":"ask","prompt":"<what specifically is needed, in a natural friendly sentence>"}

Examples:
  "send email" → {"type":"ask","prompt":"Sure! Who should I send it to, what's the subject, and what should the message say?"}
  "open" alone → {"type":"ask","prompt":"Which application would you like me to open?"}
  "write file" → {"type":"ask","prompt":"What should the file be called and what content should I write?"}

━━━ C) SYSTEM TASK ━━━
For actions requiring tool execution:
Reply ONLY with valid JSON (no other text, no markdown):
{
  "type": "task",
  "summary": "one sentence describing what you'll do",
  "steps": [
    {"action": "ACTION_NAME", "params": {}, "description": "human-readable step"}
  ]
}

AVAILABLE ACTIONS:
  OPEN_APP        {"name": "chrome"}              — launch application
  CLOSE_APP       {"name": "spotify"}             — kill process
  LIST_FILES      {"path": "~/Desktop"}           — list directory
  CREATE_DIR      {"path": "~/Projects/new"}      — create folder
  READ_FILE       {"path": "~/notes.txt"}         — read file contents
  WRITE_FILE      {"path": "~/file.txt", "content": "text here"}
  MOVE_FILE       {"src": "~/a.txt", "dst": "~/b.txt"}
  COPY_FILE       {"src": "~/a.txt", "dst": "~/b.txt"}
  DELETE_FILE     {"path": "~/old.txt"}           — DANGEROUS, will confirm
  RUN_COMMAND     {"cmd": "ipconfig /all"}        — shell command
  WEB_SEARCH      {"query": "latest AI models"}
  SEND_EMAIL      {"to": "user@example.com", "subject": "Hi", "body": "Hello there"}
  CALENDAR        {"action": "list"}              — not configured yet
  LISTEN_VOICE    {}                              — activate microphone
  GET_SYSINFO     {}                              — CPU/RAM/battery
  TAKE_SCREENSHOT {}
  ASK_USER        {"prompt": "What file path?"}  — ask user for info
  ANSWER          {"text": "your response"}      — for direct text responses

JSON RULES:
  - Output JSON for tasks/asks ONLY — zero extra text before or after
  - Output plain text for direct answers
  - Always syntactically valid JSON
  - Never add markdown code fences

PERSONALITY EXAMPLES:
  "Alright, opening Chrome."
  "Done. File created at ~/Desktop/notes.txt."
  "On it. Searching for that now."
  "Found 3 results for your query."
"""


class Brain:

    def __init__(self, config: dict, memory, planner, executor):
        self.config   = config
        self.memory   = memory
        self.planner  = planner
        self.executor = executor
        self._history: List[dict] = []

        self._base_url = config.get("ollama_url",    "http://localhost:11434")
        self._model    = config.get("model",         "llama3.2")
        self._timeout  = min(int(config.get("ollama_timeout", 12)), LLM_TIMEOUT)

        self._ollama_online = False
        self._check_ollama()
        self._write_requirements_file()
        self._log_startup()

    # ── Ollama availability check ─────────────────────────────────────────────
    def _check_ollama(self):
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            if models:
                self._ollama_online = True
                short = [m.split(":")[0] for m in models]
                if self._model.split(":")[0] not in short:
                    old = self._model
                    self._model = models[0]
                    logger.info(f"[Brain] Model '{old}' not found, using '{self._model}'")
                logger.info(f"[Brain] Ollama online — model: {self._model}")
            else:
                logger.warning(f"[Brain] Ollama running but no models. "
                               f"Run: ollama pull {self._model}")
        except Exception as e:
            logger.warning(f"[Brain] Ollama not reachable ({e}). Rule-based fallback active.")

    # ── jarvis_requirements.txt ───────────────────────────────────────────────
    def _write_requirements_file(self):
        def _has(name):
            try: __import__(name); return True
            except ImportError: return False

        _sys    = platform.system()
        _py     = sys.version.split()[0]
        online  = self._ollama_online
        m       = self._model

        lines = [
            "=" * 70,
            "  JARVIS SYSTEM CAPABILITIES REPORT",
            f"  Platform : {_sys} / Python {_py}",
            f"  LLM      : {'Ollama — ' + m if online else 'OFFLINE (Ollama not running)'}",
            f"  Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 70,
            "",
            "─── SECTION 1: CURRENT CAPABILITIES ──────────────────────────────",
            "",
            "  ALWAYS AVAILABLE (no LLM needed):",
            "    ✓ Open / close applications",
            "    ✓ File system: read, write, copy, move, delete",
            "    ✓ Directory: create, list, navigate",
            "    ✓ Shell command execution (with safety confirmation)",
            "    ✓ Web search (DuckDuckGo, no key needed)",
            "    ✓ System info: CPU, RAM, disk, battery",
            "    ✓ Screenshot capture",
            "    ✓ Email via Gmail SMTP (credentials configured ✓)",
            "    ✓ Global hotkey activation (Ctrl+Space)",
            "    ✓ Full-screen HUD overlay with live system stats",
            "    ✓ Command history (SQLite)",
            "    ✓ System tray icon",
            "",
            "  AI-POWERED (requires Ollama):",
            f"    {'✓' if online else '✗'} Natural language understanding",
            f"    {'✓' if online else '✗'} Multi-step autonomous task planning",
            f"    {'✓' if online else '✗'} Contextual conversation memory",
            f"    {'✓' if online else '✗'} Incomplete command detection and follow-up",
            "",
            "  OPTIONAL HARDWARE/SERVICES:",
            f"    {'✓' if _has('speech_recognition') else '✗'} Voice input  "
            f"(pip install SpeechRecognition pyaudio)",
            f"    {'✓' if _has('psutil')             else '✗'} System monitor "
            f"(pip install psutil)",
            f"    {'✓' if _has('GPUtil')             else '○'} GPU stats  "
            f"(pip install GPUtil)",
            f"    {'✓' if _has('serial')             else '○'} Serial ports "
            f"(pip install pyserial)",
            f"    {'✓' if _has('bleak')              else '○'} Bluetooth devices "
            f"(pip install bleak)",
            "",
            "─── SECTION 2: MISSING / NOT CONFIGURED ──────────────────────────",
            "",
            "  CALENDAR: Not configured.",
            "    Requires Google Calendar API OAuth2 credentials.",
            "    Steps: console.cloud.google.com → create project → enable Calendar API",
            "           → create OAuth2 credentials → download credentials.json",
            "           pip install google-auth-oauthlib google-api-python-client",
            "",
            "  BROWSER AUTOMATION: Not installed.",
            "    pip install playwright && playwright install chromium",
            "",
            "  BETTER WEB SEARCH: SerpAPI key not configured.",
            "    Sign up at serpapi.com → add key to config.json → web_search.serpapi_key",
            "",
            "─── SECTION 3: SETUP STEPS ────────────────────────────────────────",
            "",
            "  1. Install Ollama (local LLM, completely free):",
            "       macOS/Linux: curl -fsSL https://ollama.com/install.sh | sh",
            "       Windows    : https://ollama.com/download",
            f"     Pull model  : ollama pull {m}",
            "",
            "  2. Core Python dependencies:",
            "       pip install PyQt6 keyboard psutil",
            "",
            "  3. Voice input:",
            "       pip install SpeechRecognition pyaudio",
            "       (Windows: pyaudio may need: pip install pipwin && pipwin install pyaudio)",
            "",
            "  4. Gmail App Password (already configured):",
            "       If auth fails: myaccount.google.com → Security → 2-Step → App passwords",
            "       Create password for 'Mail' → paste into config.json → email.app_password",
            "",
            "─── SECTION 4: NEAR-AGI ROADMAP ───────────────────────────────────",
            "",
            "  Current level: Reactive assistant (explicit commands only)",
            "",
            "  Level 2 — Proactive:",
            "    Monitor system events, suggest actions, schedule reminders",
            "",
            "  Level 3 — Persistent autonomy:",
            "    Background agents, cron-style tasks, watchdog processes",
            "",
            "  Level 4 — Multi-agent:",
            "    Specialized sub-agents (research, coding, email, calendar)",
            "    Agent-to-agent communication and delegation",
            "",
            "  Level 5 — AGI:",
            f"    Requires: upgrade {m} → larger model (70B+)",
            "    Continuous learning, world model, real-time sensor fusion",
            "",
            "  Current gaps:",
            f"    Reasoning : Single-pass LLM ({m}), no chain-of-thought loop",
            "    Context   : Bounded by model context window",
            "    Learning  : Static weights — no online training",
            "    Execution : Sequential steps only — no parallel agents",
            "    Grounding : No real-world sensors (camera, GPS, etc.)",
            "",
            "=" * 70,
        ]

        try:
            out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "jarvis_requirements.txt")
            with open(out, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info(f"[Brain] Requirements → {out}")
        except Exception as e:
            logger.warning(f"[Brain] Could not write requirements file: {e}")

    def _log_startup(self):
        mode = f"Ollama/{self._model} ({self._timeout}s timeout)" \
               if self._ollama_online else "rule-based fallback"
        logger.info("=" * 55)
        logger.info("[JARVIS] ONLINE")
        logger.info(f"  LLM  : {mode}")
        logger.info(f"  Email: {self.config.get('email',{}).get('address','not configured')}")
        logger.info(f"  Voice: {'enabled' if self.config.get('voice',{}).get('input_enabled') else 'disabled'}")
        logger.info("  See  : jarvis_requirements.txt")
        logger.info("=" * 55)

    # ── Main processing pipeline ──────────────────────────────────────────────
    def process(
        self,
        command: str,
        on_status: Optional[Callable] = None,
        on_step:   Optional[Callable] = None,
        on_done:   Optional[Callable] = None,
    ):
        logger.info(f"[Brain] Processing: {command!r}")
        self.memory.log_command(command)

        if on_status:
            try: on_status("Thinking")
            except Exception: pass

        try:
            raw    = self._call_llm(command)
            parsed = self._parse_response(raw)

            # ── Incomplete command: ask for missing info ────────────────────
            if parsed and parsed.get("type") == "ask":
                prompt = parsed.get("prompt", "Could you give me a bit more detail?")
                logger.info(f"[Brain] Asking user: {prompt!r}")
                self.memory.log_response(command, prompt)
                if on_done: on_done(prompt, [])
                return

            # ── Task plan: execute steps ───────────────────────────────────
            if parsed and parsed.get("type") == "task":
                steps   = parsed.get("steps", [])
                summary = parsed.get("summary", "Done.")

                if not steps:
                    if on_done: on_done(summary, [])
                    return

                if on_status:
                    try: on_status("Planning")
                    except Exception: pass

                # Announce all steps upfront so HUD renders them immediately
                if on_step:
                    for i, s in enumerate(steps):
                        try: on_step(i, s.get("description", s.get("action","")), "init")
                        except Exception: pass

                results = self.planner.execute_plan(
                    steps, executor=self.executor,
                    on_step=on_step, on_status=on_status,
                )

                final = self._build_summary(summary, results)
                self.memory.log_response(command, final)
                if on_done: on_done(final, steps)
                return

            # ── Direct text answer ────────────────────────────────────────
            clean = re.sub(r"^\[?JARVIS\]?\s*[-:>]+\s*", "", raw).strip()
            self.memory.log_response(command, clean)
            if on_done: on_done(clean, [])

        except Exception as e:
            logger.error(f"[Brain] process() crashed: {e}", exc_info=True)
            msg = f"Something went wrong on my end: {e}"
            try: self.memory.log_response(command, msg)
            except Exception: pass
            if on_done: on_done(msg, [])

    # ── LLM call with hard timeout ────────────────────────────────────────────
    def _call_llm(self, command: str) -> str:
        """
        POST to Ollama /api/chat with a {self._timeout}s hard timeout.
        Falls back to rule-based on ANY error.
        """
        self._history.append({"role": "user", "content": command})
        max_turns = self.config.get("context_turns", 6)
        history   = self._history[-(max_turns * 2):]

        payload = json.dumps({
            "model":    self._model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
            "stream":   False,
            "options":  {
                "temperature": 0.35,
                "num_predict": 700,
            },
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/chat",
                data    = payload,
                method  = "POST",
                headers = {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())

            text = data.get("message", {}).get("content", "").strip()
            if text:
                self._history.append({"role": "assistant", "content": text})
                return text

        except urllib.error.URLError as e:
            logger.warning(f"[Brain] Ollama unreachable: {e}")
        except Exception as e:
            logger.error(f"[Brain] LLM call error ({type(e).__name__}): {e}")

        return self._rule_based_fallback(command)

    # ── Response parser ───────────────────────────────────────────────────────
    def _parse_response(self, raw: str) -> Optional[dict]:
        """
        Try to parse JSON from LLM output.
        Returns dict with type in ("task", "ask") or None for plain text.
        """
        text = raw.strip()
        # Strip accidental markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text).strip()

        # Direct text answers start with normal words, not {
        if not text.startswith("{"):
            return None

        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("type") in ("task", "ask"):
                return data
        except (json.JSONDecodeError, ValueError):
            # Try to extract the first JSON object embedded in prose
            m = re.search(r'\{.*?"type"\s*:\s*"(?:task|ask)".*?\}', text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
        return None

    # ── Summary builder ───────────────────────────────────────────────────────
    def _build_summary(self, summary: str, results: list) -> str:
        ok   = sum(1 for r in results if r.get("status") == "done")
        fail = len(results) - ok

        lines = [summary]
        if results:
            if fail == 0:
                lines.append(f"All {ok} step{'s' if ok != 1 else ''} completed successfully.")
            else:
                lines.append(f"{ok}/{len(results)} steps completed. {fail} failed.")

        # Include non-empty outputs from each step
        for r in results:
            out = str(r.get("result") or "").strip()
            if out and len(out) < 500 and out != summary:
                lines.append(f"\n{out}")

        return "\n".join(lines)

    # ── Rule-based fallback ───────────────────────────────────────────────────
    def _rule_based_fallback(self, command: str) -> str:
        """
        Works without Ollama. Handles common commands via keyword matching.
        Natural JARVIS personality, no prefixes.
        """
        cmd = command.lower().strip()

        # ── Greetings ─────────────────────────────────────────────────────
        if any(w in cmd for w in ["hello", "hi ", "hey", "howdy", "good morning", "good evening"]):
            mode = f"AI mode (model: {self._model})" if self._ollama_online else "rule-based mode"
            return f"Online and ready in {mode}. What can I do for you?"

        if any(w in cmd for w in ["what can you do", "help", "capabilities", "commands"]):
            return (
                "Here's what I can do right now:\n\n"
                "  • Open or close applications  (e.g. 'open Chrome')\n"
                "  • File operations: read, write, copy, move, delete\n"
                "  • Run shell commands  (e.g. 'run: ipconfig')\n"
                "  • Web search  (e.g. 'search for Python tutorials')\n"
                "  • Send email  (e.g. 'send email to bob@example.com')\n"
                "  • System info  (CPU, RAM, battery)\n"
                "  • Screenshot\n"
                "  • Create folders\n\n"
                "With Ollama running, I handle full natural language for any of these."
            )

        if any(w in cmd for w in ["diagnose", "status", "audit", "capabilities report"]):
            mode = f"Ollama/{self._model}" if self._ollama_online else "offline"
            return (
                f"System status:\n"
                f"  LLM:    {mode}\n"
                f"  Email:  {self.config.get('email',{}).get('address','not configured')}\n"
                f"  Voice:  {'enabled' if self.config.get('voice',{}).get('input_enabled') else 'disabled'}\n"
                f"  Full report: jarvis_requirements.txt"
            )

        # ── App control ───────────────────────────────────────────────────
        m = re.search(r"(?:^|\s)open\s+(.+)$", cmd)
        if m:
            app = m.group(1).strip().split()[0]
            return json.dumps({
                "type": "task", "summary": f"Opening {app}.",
                "steps": [{"action": "OPEN_APP", "params": {"name": app},
                           "description": f"Open {app}"}],
            })

        m = re.search(r"(?:^|\s)close\s+(.+)$", cmd)
        if m:
            app = m.group(1).strip().split()[0]
            return json.dumps({
                "type": "task", "summary": f"Closing {app}.",
                "steps": [{"action": "CLOSE_APP", "params": {"name": app},
                           "description": f"Close {app}"}],
            })

        # ── File listing ──────────────────────────────────────────────────
        if any(w in cmd for w in ["list files", "ls ", "show files", "what's in", "whats in"]):
            pm = re.search(r"(?:in|of|from|at)\s+([^\s,]+)", cmd)
            path = pm.group(1) if pm else "~"
            return json.dumps({
                "type": "task", "summary": f"Listing contents of {path}.",
                "steps": [{"action": "LIST_FILES", "params": {"path": path},
                           "description": f"List files in {path}"}],
            })

        # ── System info ───────────────────────────────────────────────────
        if any(w in cmd for w in ["sysinfo", "system info", "system information",
                                   "cpu usage", "ram usage", "memory usage", "battery"]):
            return json.dumps({
                "type": "task", "summary": "Fetching system information.",
                "steps": [{"action": "GET_SYSINFO", "params": {},
                           "description": "Get CPU, RAM, disk, battery"}],
            })

        # ── Screenshot ────────────────────────────────────────────────────
        if "screenshot" in cmd or "screen shot" in cmd or "screen capture" in cmd:
            return json.dumps({
                "type": "task", "summary": "Taking a screenshot.",
                "steps": [{"action": "TAKE_SCREENSHOT", "params": {},
                           "description": "Capture the screen"}],
            })

        # ── Email ─────────────────────────────────────────────────────────
        if "send email" in cmd or "send mail" in cmd or "email to" in cmd:
            # Try to extract address
            tm = re.search(r"(?:to|email to)\s+([\w._%+\-]+@[\w.\-]+\.[a-z]{2,})", cmd)
            to = tm.group(1) if tm else ""
            if not to:
                return json.dumps({
                    "type": "ask",
                    "prompt": "Sure! Who should I send it to, what's the subject, "
                              "and what should the message say?",
                })
            return json.dumps({
                "type": "task", "summary": f"Sending email to {to}.",
                "steps": [{"action": "SEND_EMAIL",
                           "params": {"to": to, "subject": "", "body": ""},
                           "description": f"Send email to {to}"}],
            })

        # ── Web search ────────────────────────────────────────────────────
        if any(w in cmd for w in ["search for", "look up", "google", "find online", "search "]):
            q = re.sub(r".*(search\s*(for)?|look\s*up|google|find\s*online)\s*",
                       "", cmd).strip() or command
            return json.dumps({
                "type": "task", "summary": f"Searching for: {q}",
                "steps": [{"action": "WEB_SEARCH", "params": {"query": q},
                           "description": f"Search: {q}"}],
            })

        # ── Shell command ─────────────────────────────────────────────────
        if cmd.startswith("run:") or re.match(r"^run\s+.+", cmd):
            sc = re.sub(r"^run[:\s]+", "", command, flags=re.IGNORECASE).strip()
            return json.dumps({
                "type": "task", "summary": "Executing command.",
                "steps": [{"action": "RUN_COMMAND", "params": {"cmd": sc},
                           "description": f"Run: {sc}"}],
            })

        # ── Create directory ──────────────────────────────────────────────
        if "create" in cmd and any(w in cmd for w in ["folder", "dir", "directory"]):
            pm = re.search(r"(?:folder|dir(?:ectory)?)\s+(?:called\s+|named\s+)?([^\s]+)", cmd)
            path = pm.group(1) if pm else "~/NewFolder"
            return json.dumps({
                "type": "task", "summary": f"Creating directory {path}.",
                "steps": [{"action": "CREATE_DIR", "params": {"path": path},
                           "description": f"Create {path}"}],
            })

        # ── Calendar ──────────────────────────────────────────────────────
        if "calendar" in cmd or "schedule" in cmd or "appointment" in cmd:
            return json.dumps({
                "type": "task", "summary": "Checking calendar.",
                "steps": [{"action": "CALENDAR", "params": {"action": "list"},
                           "description": "Check calendar"}],
            })

        # ── Offline catch-all ─────────────────────────────────────────────
        if not self._ollama_online:
            return (
                "Ollama isn't running, so I'm in rule-based mode. "
                f"Start Ollama and run 'ollama pull {self._model}' for full AI. "
                "Type 'help' to see what I can do right now."
            )

        return "I didn't quite understand that. Could you rephrase, or type 'help' for a list of commands?"
