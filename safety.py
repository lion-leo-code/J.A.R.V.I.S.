"""
JARVIS Safety Layer
Validates all actions before execution.
Blocks or flags destructive / dangerous operations.
"""

import logging
import re
from typing import Tuple, List

logger = logging.getLogger("jarvis.safety")


class SafetyLayer:
    """
    Validates (action, params) pairs before they reach tools.
    Returns (allowed: bool, reason: str).
    """

    # Actions that require extra scrutiny
    DESTRUCTIVE_ACTIONS = {"DELETE_FILE", "RUN_COMMAND", "CLOSE_APP"}

    # Shell commands that are always blocked
    BLOCKED_COMMANDS = [
        r"rm\s+-rf\s+/",           # rm -rf /
        r"dd\s+if=",               # disk dump
        r"mkfs",                   # format disk
        r":(){ :|:& };:",          # fork bomb
        r">\s*/dev/sd",            # write to raw disk
        r"chmod\s+-R\s+777\s+/",   # recursive chmod root
        r"sudo\s+rm",              # sudo delete
        r"shutdown",
        r"reboot",
        r"halt",
    ]

    # Paths that are always protected
    PROTECTED_PATHS = ["/", "/etc", "/bin", "/usr", "/sys", "/proc", "/dev",
                       "/boot", "C:\\Windows", "C:\\System32"]

    def __init__(self, config: dict):
        self.config           = config
        self._block_patterns  = [re.compile(p, re.IGNORECASE)
                                  for p in self.BLOCKED_COMMANDS]
        self._allow_destructive = config.get("allow_destructive", False)
        logger.info(f"[Safety] Initialized. allow_destructive={self._allow_destructive}")

    def check(self, action: str, params: dict) -> Tuple[bool, str]:
        """
        Returns (True, "") if safe, (False, reason) if blocked.
        """
        action = action.upper()

        # ── Block unknown / empty actions ──────────────────────────────────
        if not action:
            return False, "Empty action"

        # ── Shell command checks ───────────────────────────────────────────
        if action == "RUN_COMMAND":
            cmd = params.get("cmd", "")
            blocked, reason = self._check_command(cmd)
            if blocked:
                return False, reason

        # ── File path protection ───────────────────────────────────────────
        for key in ["path", "src", "dst"]:
            if key in params:
                blocked, reason = self._check_path(params[key])
                if blocked:
                    return False, reason

        # ── Destructive action gate ────────────────────────────────────────
        if action == "DELETE_FILE" and not self._allow_destructive:
            path = params.get("path", "")
            # Only block truly dangerous deletes; home dir files are okay
            if self._is_system_path(path):
                return False, f"Refusing to delete system path: {path}"
            logger.warning(f"[Safety] DELETE_FILE on {path} — proceeding")

        logger.debug(f"[Safety] Approved: {action}")
        return True, ""

    def _check_command(self, cmd: str) -> Tuple[bool, str]:
        """Scan a shell command against blocked patterns."""
        for pattern in self._block_patterns:
            if pattern.search(cmd):
                logger.warning(f"[Safety] Blocked command: {cmd!r}")
                return True, f"Command matches blocked pattern: {pattern.pattern}"
        return False, ""

    def _check_path(self, path: str) -> Tuple[bool, str]:
        """Ensure path is not a protected system path."""
        if self._is_system_path(path):
            logger.warning(f"[Safety] Blocked system path: {path}")
            return True, f"Path is protected: {path}"
        return False, ""

    def _is_system_path(self, path: str) -> bool:
        """Return True if path matches a protected root."""
        normalized = path.strip().rstrip("/\\")
        for protected in self.PROTECTED_PATHS:
            if normalized == protected or normalized.startswith(protected + "/"):
                return True
        return False
