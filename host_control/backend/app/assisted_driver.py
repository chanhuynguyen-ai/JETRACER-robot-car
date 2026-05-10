import threading
import time
from typing import Callable, Optional

from .state import SharedState


class AssistedDriver:
    def __init__(
        self,
        shared_state: SharedState,
        send_drive: Callable[[int, int], None],
        send_stop: Callable[[], None],
        interval_s: float = 0.12,
        min_confidence: float = 0.18,
    ) -> None:
        self.shared_state = shared_state
        self.send_drive = send_drive
        self.send_stop = send_stop
        self.interval_s = interval_s
        self.min_confidence = min_confidence

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_sent = None
        self._last_stop_reason = None

    def _add_event(self, kind: str, message: str) -> None:
        if hasattr(self.shared_state, "add_event") and callable(self.shared_state.add_event):
            self.shared_state.add_event(kind, message)
            return

        if hasattr(self.shared_state, "push_event") and callable(self.shared_state.push_event):
            self.shared_state.push_event(kind, message)
            return

    def _get_status(self) -> dict:
        if hasattr(self.shared_state, "get_status") and callable(self.shared_state.get_status):
            return self.shared_state.get_status()
        return {}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _safe_stop(self, reason: str) -> None:
        if self._last_stop_reason != reason:
            self._add_event("WARN", f"ASSISTED_STOP: {reason}")
            self._last_stop_reason = reason

        try:
            self.send_stop()
            self._last_sent = ("STOP", 0)
        except Exception as e:
            self._add_event("WARN", f"ASSISTED_STOP_FAILED: {e}")

    def _loop(self) -> None:
        while self._running:
            status = self._get_status()

            assisted_enabled = bool(status.get("assisted_enabled", False))
            mode = str(status.get("mode", "UNKNOWN"))
            serial_connected = bool(status.get("connected", False))
            estop = bool(status.get("estop", False))
            obstacle = bool(status.get("obstacle_detected", False))
            conf = float(status.get("lane_confidence") or 0.0)

            if not assisted_enabled or mode != "ASSISTED":
                time.sleep(self.interval_s)
                continue

            if not serial_connected:
                self._safe_stop("SERIAL_DISCONNECTED")
                time.sleep(self.interval_s)
                continue

            if estop:
                self._safe_stop("ESTOP")
                time.sleep(self.interval_s)
                continue

            if obstacle:
                self._safe_stop("OBSTACLE")
                time.sleep(self.interval_s)
                continue

            if conf < self.min_confidence:
                self._safe_stop("LOW_LANE_CONFIDENCE")
                time.sleep(self.interval_s)
                continue

            speed = int(status.get("recommended_speed") or 0)
            angle = int(status.get("recommended_angle") or 90)

            cmd = (speed, angle)
            if cmd != self._last_sent:
                try:
                    self.send_drive(speed, angle)
                    self._add_event("INFO", f"ASSISTED_CMD speed={speed} angle={angle}")
                    self._last_sent = cmd
                    self._last_stop_reason = None
                except Exception as e:
                    self._add_event("WARN", f"ASSISTED_CMD_FAILED: {e}")

            time.sleep(self.interval_s)