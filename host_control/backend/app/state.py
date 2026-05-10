import threading
import time
from collections import deque
from copy import deepcopy
from typing import Any, Dict, List, Optional


class SharedState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events = deque(maxlen=200)

        self._status: Dict[str, Any] = {
            # serial / car status
            "connected": False,
            "mode": "UNKNOWN",
            "motor": 0,
            "angle": 90,
            "estop": False,
            "pca": False,
            "watchdog_ms": 0,
            "uptime": 0,
            "last_raw_line": "",
            "last_update_ts": 0.0,
            "last_ack": "",
            "last_error": "",
            "seq": 0,

            # camera / perception
            "camera_connected": False,
            "camera_fps": 0.0,
            "latest_frame_ts": 0.0,
            "lane_offset": None,
            "lane_confidence": 0.0,
            "obstacle_detected": False,
            "obstacle_distance": None,
            "recommended_speed": 0,
            "recommended_angle": 90,

            # assisted
            "assisted_enabled": False,
        }

    # =========================
    # Basic state ops
    # =========================

    def update_status(self, **kwargs: Any) -> None:
        with self._lock:
            self._status.update(kwargs)
            self._status["last_update_ts"] = time.time()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._status)

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)[:limit]

    def snapshot(self, limit: int = 50) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": deepcopy(self._status),
                "events": list(self._events)[:limit],
            }

    # =========================
    # Compatibility methods for serial_manager.py
    # =========================

    def update_connection(self, connected: bool) -> None:
        self.update_status(connected=bool(connected))

    def add_event(self, kind: str, message: str) -> None:
        with self._lock:
            self._events.appendleft(
                {
                    "kind": str(kind),
                    "message": str(message),
                    "ts": time.time(),
                }
            )

    # alias for code written earlier
    def push_event(self, kind: str, message: str) -> None:
        self.add_event(kind, message)

    # =========================
    # Parser helpers
    # =========================

    def _to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "on", "ready"}

    def _to_number_if_possible(self, value: Any) -> Any:
        if isinstance(value, (int, float, bool)) or value is None:
            return value

        text = str(value).strip()
        if text == "":
            return value

        try:
            if "." in text:
                return float(text)
            return int(text)
        except Exception:
            return value

    def _normalize_status_key(self, key: str) -> Optional[str]:
        k = key.strip().lower()

        mapping = {
            "mode": "mode",
            "motor": "motor",
            "angle": "angle",
            "estop": "estop",
            "pca": "pca",
            "wd_ms": "watchdog_ms",
            "watchdog_ms": "watchdog_ms",
            "uptime": "uptime",
            "seq": "seq",
            "connected": "connected",

            "camera_connected": "camera_connected",
            "camera_fps": "camera_fps",
            "latest_frame_ts": "latest_frame_ts",
            "lane_offset": "lane_offset",
            "lane_confidence": "lane_confidence",
            "obstacle_detected": "obstacle_detected",
            "obstacle_distance": "obstacle_distance",
            "recommended_speed": "recommended_speed",
            "recommended_angle": "recommended_angle",
            "assisted_enabled": "assisted_enabled",
        }

        return mapping.get(k)

    def _extract_fields_from_text(self, raw_text: str) -> Dict[str, Any]:
        """
        Parse các dòng kiểu:
        TEL MODE=MANUAL MOTOR=0 ANGLE=90 ESTOP=0 PCA=0 WD_MS=564 UPTIME=162093
        STATUS MODE=MANUAL MOTOR=0 ANGLE=90 ...
        ACK MODE MANUAL
        ERR SOMETHING
        """
        result: Dict[str, Any] = {}
        tokens = raw_text.strip().split()

        for token in tokens:
            if "=" not in token:
                continue

            key, value = token.split("=", 1)
            normalized = self._normalize_status_key(key)
            if normalized is None:
                continue

            parsed_value = self._to_number_if_possible(value)

            if normalized in {"estop", "pca", "connected", "camera_connected", "obstacle_detected", "assisted_enabled"}:
                parsed_value = self._to_bool(parsed_value)

            result[normalized] = parsed_value

        return result

    def _extract_fields_from_parsed(self, parsed: Any) -> Dict[str, Any]:
        """
        Hỗ trợ linh hoạt nếu parse_line(text) trả về dict.
        Không phụ thuộc cứng vào schema của parser.py.
        """
        result: Dict[str, Any] = {}

        if not isinstance(parsed, dict):
            return result

        # nếu parser trả thẳng field status
        for key, value in parsed.items():
            normalized = self._normalize_status_key(str(key))
            if normalized is None:
                continue

            parsed_value = self._to_number_if_possible(value)
            if normalized in {"estop", "pca", "connected", "camera_connected", "obstacle_detected", "assisted_enabled"}:
                parsed_value = self._to_bool(parsed_value)

            result[normalized] = parsed_value

        # nếu parser gói trong payload/data/fields
        for nested_key in ["payload", "data", "fields", "status"]:
            nested = parsed.get(nested_key)
            if isinstance(nested, dict):
                for key, value in nested.items():
                    normalized = self._normalize_status_key(str(key))
                    if normalized is None:
                        continue

                    parsed_value = self._to_number_if_possible(value)
                    if normalized in {"estop", "pca", "connected", "camera_connected", "obstacle_detected", "assisted_enabled"}:
                        parsed_value = self._to_bool(parsed_value)

                    result[normalized] = parsed_value

        return result

    # =========================
    # Main ingestion from serial_manager
    # =========================

    def apply_message(self, parsed: Any, raw_text: str) -> None:
        raw_text = (raw_text or "").strip()
        now = time.time()

        with self._lock:
            self._status["last_raw_line"] = raw_text
            self._status["last_update_ts"] = now

            # seq tăng mỗi lần có message
            current_seq = self._status.get("seq", 0)
            try:
                current_seq = int(current_seq)
            except Exception:
                current_seq = 0
            self._status["seq"] = current_seq + 1

            upper = raw_text.upper()

            # ACK
            if upper.startswith("ACK"):
                self._status["last_ack"] = raw_text

            # ERR
            if upper.startswith("ERR") or upper.startswith("[ERR]"):
                self._status["last_error"] = raw_text
                self._events.appendleft(
                    {
                        "kind": "ERROR",
                        "message": raw_text,
                        "ts": now,
                    }
                )

            # TEL / STATUS -> mặc định coi là còn kết nối
            if upper.startswith("TEL") or upper.startswith("STATUS"):
                self._status["connected"] = True

            # update từ parser dict trước
            parsed_updates = self._extract_fields_from_parsed(parsed)
            self._status.update(parsed_updates)

            # rồi update tiếp từ raw text để bắt các key=value
            text_updates = self._extract_fields_from_text(raw_text)
            self._status.update(text_updates)

            # dọn kiểu dữ liệu chắc chắn hơn
            if "motor" in self._status:
                try:
                    self._status["motor"] = int(self._status["motor"])
                except Exception:
                    pass

            if "angle" in self._status:
                try:
                    self._status["angle"] = int(self._status["angle"])
                except Exception:
                    pass

            if "watchdog_ms" in self._status:
                try:
                    self._status["watchdog_ms"] = int(self._status["watchdog_ms"])
                except Exception:
                    pass

            if "uptime" in self._status:
                try:
                    self._status["uptime"] = int(self._status["uptime"])
                except Exception:
                    pass

            for bool_key in [
                "connected",
                "estop",
                "pca",
                "camera_connected",
                "obstacle_detected",
                "assisted_enabled",
            ]:
                self._status[bool_key] = self._to_bool(self._status.get(bool_key, False))


shared_state = SharedState()