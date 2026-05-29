"""
JARVIS Planner
Converts LLM task plans into sequentially executed steps.

Each step runs with a configurable timeout (default 10s).
If a step hangs, it is aborted and marked as error — the plan never blocks forever.
"""

import logging
import time
import threading
from typing import List, Dict, Callable, Optional

logger = logging.getLogger("jarvis.planner")

# Per-step execution timeout in seconds
STEP_TIMEOUT = 10


class TaskStep:
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE    = "done"
    STATUS_ERROR   = "error"
    STATUS_SKIPPED = "skipped"
    STATUS_TIMEOUT = "timeout"

    def __init__(self, index: int, action: str, params: dict, description: str):
        self.index       = index
        self.action      = action
        self.params      = params
        self.description = description
        self.status      = self.STATUS_PENDING
        self.result      = None
        self.error       = None
        self.start_time: Optional[float] = None
        self.end_time:   Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return round(self.end_time - self.start_time, 3)
        return None

    def to_dict(self) -> dict:
        return {
            "index":       self.index,
            "action":      self.action,
            "params":      self.params,
            "description": self.description,
            "status":      self.status,
            "result":      str(self.result) if self.result else None,
            "error":       self.error,
            "duration":    self.duration,
        }


class Planner:
    """
    Sequential step executor.
    Each step runs in a thread with STEP_TIMEOUT seconds before being abandoned.
    All callbacks are called from the worker thread — they must be signal emitters, not UI calls.
    """

    def __init__(self, config: dict):
        self.config           = config
        self._current_plan: List[TaskStep] = []
        self._abort_flag      = False
        self._step_timeout    = config.get("step_timeout", STEP_TIMEOUT)

    def execute_plan(
        self,
        raw_steps:  List[Dict],
        executor,
        on_step:    Optional[Callable] = None,
        on_status:  Optional[Callable] = None,
    ) -> List[Dict]:
        """
        Execute all steps sequentially. Each step has STEP_TIMEOUT second hard limit.

        Returns list of step result dicts — always returns, never hangs.
        """
        self._abort_flag   = False
        self._current_plan = []
        results: List[Dict] = []

        # Build TaskStep objects from raw dicts
        for i, raw in enumerate(raw_steps):
            step = TaskStep(
                index       = i,
                action      = raw.get("action", "ANSWER"),
                params      = raw.get("params", {}),
                description = raw.get("description", raw.get("action", f"Step {i+1}")),
            )
            self._current_plan.append(step)

        logger.info(f"[Planner] Starting plan: {len(self._current_plan)} steps")

        for step in self._current_plan:
            if self._abort_flag:
                step.status = TaskStep.STATUS_SKIPPED
                if on_step:
                    try: on_step(step.index, step.description, "skipped")
                    except Exception: pass
                results.append(step.to_dict())
                continue

            # Notify: step starting
            step.status     = TaskStep.STATUS_RUNNING
            step.start_time = time.time()
            logger.info(f"[Planner] Step {step.index+1}/{len(self._current_plan)}: "
                        f"{step.action} — {step.description}")

            if on_step:
                try: on_step(step.index, step.description, "running")
                except Exception: pass
            if on_status:
                try: on_status(f"Step {step.index+1}/{len(self._current_plan)}")
                except Exception: pass

            # Execute with timeout
            result_container: Dict = {}
            exception_container: list = []

            def _run():
                try:
                    result_container["r"] = executor.run(step.action, step.params)
                except Exception as e:
                    exception_container.append(e)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=self._step_timeout)

            step.end_time = time.time()

            if t.is_alive():
                # Step timed out
                step.status = TaskStep.STATUS_TIMEOUT
                step.error  = f"Step timed out after {self._step_timeout}s"
                logger.warning(f"[Planner] Step {step.index+1} TIMED OUT")
                if self.config.get("planner", {}).get("stop_on_failure", False):
                    self._abort_flag = True
            elif exception_container:
                step.status = TaskStep.STATUS_ERROR
                step.error  = str(exception_container[0])
                logger.error(f"[Planner] Step {step.index+1} exception: {step.error}")
            else:
                r = result_container.get("r", {"success": False, "output": "", "error": "No result"})
                step.result = r.get("output", "")
                if r.get("success", False):
                    step.status = TaskStep.STATUS_DONE
                else:
                    step.status = TaskStep.STATUS_ERROR
                    step.error  = r.get("error") or "Step failed"
                    if self.config.get("planner", {}).get("stop_on_failure", False):
                        self._abort_flag = True

            # Notify: step complete
            notify_status = "done" if step.status == TaskStep.STATUS_DONE else "error"
            if on_step:
                try: on_step(step.index, step.description, notify_status)
                except Exception: pass

            results.append(step.to_dict())

        ok   = sum(1 for r in results if r["status"] == "done")
        fail = len(results) - ok
        logger.info(f"[Planner] Complete — {ok}/{len(results)} succeeded, {fail} failed")
        return results

    def abort(self):
        """Signal the plan to stop after the current step."""
        self._abort_flag = True
        logger.info("[Planner] Abort requested")

    def get_plan_summary(self) -> List[Dict]:
        return [s.to_dict() for s in self._current_plan]
