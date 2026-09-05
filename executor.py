"""
JARVIS Executor — Intent Override Engine

Problem this solves:
  The LLM sometimes outputs wrong action names, wrong parameter keys,
  or completely incorrect JSON for simple commands.

Fix:
  Before dispatching to tools, run the command through _override_intent()
  which pattern-matches natural language → guaranteed correct tool call.

  "open opera"     → OPEN_APP(name="opera")      — guaranteed
  "search X"       → WEB_SEARCH(query="X")        — guaranteed
  "take screenshot"→ TAKE_SCREENSHOT()             — guaranteed
  "create file X"  → WRITE_FILE(path=JARVIS_DIR/X)— guaranteed

Threading:
  _blocking_confirm() called from worker thread → emits Qt signal →
  main thread shows YES/NO → blocks via threading.Event → returns result.
  Always times out after 30s (returns False = deny).
"""

import logging
import re
import threading
import pathlib
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger("jarvis.executor")

# Actions requiring user confirmation before execution
DANGEROUS_ACTIONS = {"DELETE_FILE", "RUN_COMMAND"}


class Executor:

    def __init__(self, tool_registry, safety):
        self.tools    = tool_registry
        self.safety   = safety
        self._signals = None

        self._confirm_event  = threading.Event()
        self._confirm_result = False

        try:
            self.tools.set_confirm_callback(self._blocking_confirm)
        except Exception as e:
            logger.warning(f"[Executor] Could not wire confirm callback: {e}")

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def set_signals(self, signals):
        self._signals = signals
        try:
            signals.confirm_response.connect(self._on_confirm_response)
            logger.info("[Executor] Confirmation signals wired")
        except Exception as e:
            logger.error(f"[Executor] Signal wiring failed: {e}")

    # ── Confirmation (blocks worker thread, answered by main thread) ──────────
    def _blocking_confirm(self, question: str) -> bool:
        if not self._signals:
            return False
        self._confirm_event.clear()
        self._confirm_result = False
        try:
            self._signals.confirm_request.emit(question)
        except Exception as e:
            logger.error(f"[Executor] confirm_request emit failed: {e}")
            return False
        answered = self._confirm_event.wait(timeout=30)
        return self._confirm_result if answered else False

    def _on_confirm_response(self, yes: bool):
        self._confirm_result = yes
        self._confirm_event.set()

    # ── Intent override engine ────────────────────────────────────────────────
    def _override_intent(self, action: str, params: Dict[str, Any]) -> tuple:
        """
        Map natural language / partial inputs to guaranteed correct tool+params.
        Returns (corrected_action, corrected_params).

        This runs BEFORE safety checks and tool dispatch, ensuring the LLM's
        wrong outputs are corrected before any execution attempt.
        """
        a = action.upper().strip()

        # ── Normalize aliases ──────────────────────────────────────────────
        alias_map = {
            "CREATE_FILE":    "WRITE_FILE",
            "MAKE_FILE":      "WRITE_FILE",
            "SAVE_FILE":      "WRITE_FILE",
            "SCREENSHOT":     "TAKE_SCREENSHOT",
            "SCREEN_SHOT":    "TAKE_SCREENSHOT",
            "TAKE_SCREENSHOT":"TAKE_SCREENSHOT",
            "CAPTURE_SCREEN": "TAKE_SCREENSHOT",
            "SEARCH":         "WEB_SEARCH",
            "GOOGLE":         "WEB_SEARCH",
            "OPEN":           "OPEN_APP",
            "LAUNCH":         "OPEN_APP",
            "START":          "OPEN_APP",
            "RUN_APP":        "OPEN_APP",
            "CLOSE":          "CLOSE_APP",
            "KILL":           "CLOSE_APP",
            "EMAIL":          "SEND_EMAIL",
            "MAIL":           "SEND_EMAIL",
            "SYSINFO":        "GET_SYSINFO",
            "SYSTEM_INFO":    "GET_SYSINFO",
            "DIR":            "LIST_FILES",
            "LS":             "LIST_FILES",
            "CAT":            "READ_FILE",
        }
        if a in alias_map:
            a = alias_map[a]

        # ── OPEN_APP: ensure 'name' key exists ───────────────────────────
        if a == "OPEN_APP":
            if "name" not in params:
                # Try common alternative keys
                name = (params.get("app") or params.get("application")
                        or params.get("program") or params.get("target", ""))
                params = {"name": str(name).strip()}
            else:
                params["name"] = str(params["name"]).strip()

        # ── WEB_SEARCH: ensure 'query' key exists ────────────────────────
        elif a == "WEB_SEARCH":
            if "query" not in params:
                q = (params.get("q") or params.get("search")
                     or params.get("term") or params.get("text", ""))
                params = {"query": str(q).strip()}

        # ── WRITE_FILE: redirect to JARVIS_DIR if path is relative ───────
        elif a == "WRITE_FILE":
            try:
                from builtins import JARVIS_DIR
            except ImportError:
                JARVIS_DIR = pathlib.Path.home() / "JARVIS"
            path = params.get("path", "")
            if path:
                p = pathlib.Path(path)
                if not p.is_absolute():
                    params["path"] = str(JARVIS_DIR / p.name)
                else:
                    params["path"] = str(p)
            else:
                params["path"] = str(JARVIS_DIR / "untitled.txt")
            if "content" not in params:
                params["content"] = ""

        # ── READ_FILE: resolve relative paths ────────────────────────────
        elif a == "READ_FILE":
            try:
                from builtins import JARVIS_DIR
            except ImportError:
                JARVIS_DIR = pathlib.Path.home() / "JARVIS"
            path = params.get("path", "")
            if path:
                p = pathlib.Path(path)
                if not p.is_absolute():
                    params["path"] = str(JARVIS_DIR / p.name)

        # ── TAKE_SCREENSHOT: no params needed ────────────────────────────
        elif a == "TAKE_SCREENSHOT":
            params = {}

        # ── GET_SYSINFO: no params needed ────────────────────────────────
        elif a == "GET_SYSINFO":
            params = {}

        # ── SEND_EMAIL: normalise key names ──────────────────────────────
        elif a == "SEND_EMAIL":
            p2 = {}
            p2["to"]      = params.get("to") or params.get("recipient") or params.get("email", "")
            p2["subject"] = params.get("subject") or params.get("sub") or params.get("title", "")
            p2["body"]    = params.get("body") or params.get("message") or params.get("text", "")
            params = p2

        # ── LIST_FILES: default to JARVIS_DIR ────────────────────────────
        elif a == "LIST_FILES":
            if not params.get("path"):
                try:
                    from builtins import JARVIS_DIR
                except ImportError:
                    JARVIS_DIR = pathlib.Path.home() / "JARVIS"
                params["path"] = str(JARVIS_DIR)

        return a, params

    # ── Main dispatch ─────────────────────────────────────────────────────────
    def run(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch one tool action. Bulletproof routing + execution.
        """

        # ─────────────────────────────────────────────
        # STEP 0: Normalize
        # ─────────────────────────────────────────────
        action = (action or "").replace("-", "_").upper()
        raw = (params.get("text") or params.get("query") or "").lower()

        logger.info(f"[Executor] RAW='{raw}' INITIAL_ACTION={action}")

        # ─────────────────────────────────────────────
        # STEP 1: HARD INTENT OVERRIDE (PRIORITY FIX)
        # ─────────────────────────────────────────────
        if "email" in raw or "mail" in raw:
            action = "SEND_EMAIL"

        elif "screenshot" in raw:
            action = "TAKE_SCREENSHOT"

        elif any(k in raw for k in ["open", "launch", "start"]):
            action = "OPEN_APP"

        elif any(k in raw for k in ["search", "google", "look up"]):
            action = "WEB_SEARCH"

        elif any(k in raw for k in ["run", "cmd", "command"]):
            action = "RUN_COMMAND"

        elif any(k in raw for k in ["create file", "make file", "write file"]):
            action = "WRITE_FILE"

        logger.info(f"[Executor] AFTER ROUTING → {action}")

        # ─────────────────────────────────────────────
        # STEP 2: PARAM FIXES (CRITICAL)
        # ─────────────────────────────────────────────

        if action == "RUN_COMMAND":
            cmd = (
                params.get("cmd")
                or params.get("command")
                or params.get("text")
                or params.get("query")
                or ""
            )

            if not cmd.strip():
                return {
                    "success": False,
                    "output": "No command provided. What should I run?",
                    "needs_user_input": True,
                }

            params = {"cmd": cmd}

        if action == "SEND_EMAIL":
            params = {
                "to": params.get("to", ""),
                "subject": params.get("subject", ""),
                "body": params.get("body", ""),
            }

        # ─────────────────────────────────────────────
        # STEP 3: INTENT OVERRIDE (LLM CORRECTION)
        # ─────────────────────────────────────────────
        try:
            action, params = self._override_intent(action, params)
        except Exception as e:
            logger.error(f"[Executor] Intent override error: {e}")

        logger.info(f"[Executor] FINAL ACTION → {action} params={params}")

        # ─────────────────────────────────────────────
        # STEP 4: SAFETY CHECK
        # ─────────────────────────────────────────────
        try:
            safe, reason = self.safety.check(action, params)
            if not safe:
                return self._fail(f"Blocked: {reason}")
        except Exception as e:
            logger.error(f"[Executor] Safety check error: {e}")
            return self._fail(f"Safety check failed: {e}")

        # ─────────────────────────────────────────────
        # STEP 5: FORCE CORRECT TOOL EXECUTION
        # ─────────────────────────────────────────────
        try:
            if action == "SEND_EMAIL":
                print("🔥 EMAIL TOOL EXECUTED")
                handler = self.tools.get_handler("SEND_EMAIL")

            elif action == "WRITE_FILE":
                print("⚠️ WRITE FILE TOOL EXECUTED")
                handler = self.tools.get_handler("WRITE_FILE")

            elif action == "RUN_COMMAND":
                handler = self.tools.get_handler("RUN_COMMAND")

            elif action == "OPEN_APP":
                handler = self.tools.get_handler("OPEN_APP")

            elif action == "WEB_SEARCH":
                handler = self.tools.get_handler("WEB_SEARCH")

            elif action == "TAKE_SCREENSHOT":
                handler = self.tools.get_handler("TAKE_SCREENSHOT")

            else:
                handler = self.tools.get_handler(action)

            if not handler:
                return self._fail(f"No handler for action: {action}")

            result = handler(**params)

        except TypeError as e:
            logger.error(f"[Executor] Bad params for {action}: {e}")
            return self._fail(f"Wrong parameters for {action}: {e}")

        except Exception as e:
            logger.error(f"[Executor] {action} raised: {e}", exc_info=True)
            return self._fail(str(e))

        # ─────────────────────────────────────────────
        # STEP 6: NORMALIZE OUTPUT
        # ─────────────────────────────────────────────
        if isinstance(result, dict):
            return {
                "success": bool(result.get("success", True)),
                "output": str(result.get("output", "")),
                "error": result.get("error"),
                "needs_user_input": bool(result.get("needs_user_input", False)),
            }

        return {
            "success": True,
            "output": str(result),
            "error": None,
            "needs_user_input": False,
        }


    @staticmethod
    def _fail(msg: str) -> Dict[str, Any]:
        return {
            "success": False,
            "output": "",
            "error": msg,
            "needs_user_input": False,
        }