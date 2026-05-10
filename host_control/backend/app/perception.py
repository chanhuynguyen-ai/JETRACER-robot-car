import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from .camera import CameraManager
from .state import SharedState


class PerceptionManager:
    def __init__(
        self,
        camera: CameraManager,
        shared_state: SharedState,
        width: int = 640,
        height: int = 480,
        center_angle: int = 90,
        max_steer_delta: int = 18,
    ) -> None:
        self.camera = camera
        self.shared_state = shared_state
        self.width = width
        self.height = height
        self.center_angle = center_angle
        self.max_steer_delta = max_steer_delta

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._overlay_frame: Optional[np.ndarray] = None
        self._last_result = {
            "camera_connected": False,
            "lane_offset": None,
            "lane_confidence": 0.0,
            "obstacle_detected": False,
            "obstacle_distance": None,
            "recommended_speed": 0,
            "recommended_angle": center_angle,
            "updated_at": 0.0,
        }

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

    def get_overlay_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._overlay_frame is None:
                return None
            return self._overlay_frame.copy()

    def get_overlay_jpeg(self) -> Optional[bytes]:
        frame = self.get_overlay_frame()
        if frame is None:
            return None
        return self.camera.encode_jpeg(frame)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._last_result)

    def _fit_line_yx(
        self,
        points: list[Tuple[int, int]],
        y_bottom: int,
        y_top: int,
    ) -> Optional[Tuple[int, int, int, int]]:
        if len(points) < 4:
            return None

        ys = np.array([p[1] for p in points], dtype=np.float32)
        xs = np.array([p[0] for p in points], dtype=np.float32)

        if len(np.unique(ys)) < 2:
            return None

        coeff = np.polyfit(ys, xs, 1)
        x_bottom = int(coeff[0] * y_bottom + coeff[1])
        x_top = int(coeff[0] * y_top + coeff[1])
        return (x_bottom, y_bottom, x_top, y_top)

    def _detect_lane(self, frame: np.ndarray) -> tuple[dict, np.ndarray]:
        frame = cv2.resize(frame, (self.width, self.height))
        overlay = frame.copy()

        h, w = frame.shape[:2]
        y_top = int(h * 0.58)
        y_bottom = h - 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 160)

        roi_mask = np.zeros_like(edges)
        polygon = np.array(
            [[
                (40, h),
                (int(w * 0.38), y_top),
                (int(w * 0.62), y_top),
                (w - 40, h),
            ]],
            dtype=np.int32,
        )
        cv2.fillPoly(roi_mask, polygon, 255)
        roi_edges = cv2.bitwise_and(edges, roi_mask)

        lines = cv2.HoughLinesP(
            roi_edges,
            1,
            np.pi / 180,
            threshold=35,
            minLineLength=35,
            maxLineGap=50,
        )

        left_points: list[Tuple[int, int]] = []
        right_points: list[Tuple[int, int]] = []

        if lines is not None:
            for line in lines[:, 0]:
                x1, y1, x2, y2 = map(int, line)
                if x2 == x1:
                    continue

                slope = (y2 - y1) / (x2 - x1)
                if abs(slope) < 0.35:
                    continue

                if slope < 0:
                    left_points.extend([(x1, y1), (x2, y2)])
                else:
                    right_points.extend([(x1, y1), (x2, y2)])

        left_line = self._fit_line_yx(left_points, y_bottom, y_top)
        right_line = self._fit_line_yx(right_points, y_bottom, y_top)

        lane_center_x = None
        confidence = 0.0

        lane_width_guess = 220

        if left_line and right_line:
            lane_center_x = int((left_line[0] + right_line[0]) / 2)
            confidence = 0.82
        elif left_line:
            lane_center_x = left_line[0] + lane_width_guess // 2
            confidence = 0.38
        elif right_line:
            lane_center_x = right_line[0] - lane_width_guess // 2
            confidence = 0.38
        else:
            confidence = 0.0

        offset_norm = None
        recommended_angle = self.center_angle
        recommended_speed = 0

        if lane_center_x is not None:
            offset_px = lane_center_x - (w // 2)
            offset_norm = float(np.clip(offset_px / (w / 2), -1.0, 1.0))
            recommended_angle = int(
                np.clip(
                    self.center_angle + offset_norm * self.max_steer_delta,
                    60,
                    120,
                )
            )
            recommended_speed = int(np.interp(abs(offset_norm), [0.0, 1.0], [135, 80]))
            if confidence < 0.15:
                recommended_speed = 0

        obstacle_detected = False
        obstacle_distance = None

        cv2.polylines(overlay, polygon, True, (80, 120, 255), 2)

        if left_line:
            cv2.line(
                overlay,
                (left_line[0], left_line[1]),
                (left_line[2], left_line[3]),
                (0, 255, 0),
                3,
            )

        if right_line:
            cv2.line(
                overlay,
                (right_line[0], right_line[1]),
                (right_line[2], right_line[3]),
                (0, 255, 0),
                3,
            )

        frame_center_x = w // 2
        cv2.line(overlay, (frame_center_x, y_top), (frame_center_x, y_bottom), (255, 180, 0), 2)

        if lane_center_x is not None:
            cv2.line(overlay, (lane_center_x, y_top), (lane_center_x, y_bottom), (0, 220, 255), 2)
            cv2.circle(overlay, (lane_center_x, y_bottom - 8), 7, (0, 220, 255), -1)

        cv2.putText(
            overlay,
            f"lane_conf={confidence:.2f}",
            (18, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            f"offset={offset_norm if offset_norm is not None else 'None'}",
            (18, 56),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            f"rec_angle={recommended_angle} rec_speed={recommended_speed}",
            (18, 84),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )

        result = {
            "camera_connected": self.camera.is_connected(),
            "lane_offset": round(offset_norm, 4) if offset_norm is not None else None,
            "lane_confidence": round(float(confidence), 4),
            "obstacle_detected": obstacle_detected,
            "obstacle_distance": obstacle_distance,
            "recommended_speed": int(recommended_speed),
            "recommended_angle": int(recommended_angle),
            "updated_at": time.time(),
        }
        return result, overlay

    def _loop(self) -> None:
        while self._running:
            frame = self.camera.get_frame()
            if frame is None:
                result = {
                    "camera_connected": False,
                    "lane_offset": None,
                    "lane_confidence": 0.0,
                    "obstacle_detected": False,
                    "obstacle_distance": None,
                    "recommended_speed": 0,
                    "recommended_angle": self.center_angle,
                    "updated_at": time.time(),
                }
                with self._lock:
                    self._last_result = result
                    self._overlay_frame = None

                self.shared_state.update_status(
                    camera_connected=False,
                    camera_fps=round(self.camera.get_fps(), 2),
                    latest_frame_ts=0.0,
                    lane_offset=None,
                    lane_confidence=0.0,
                    obstacle_detected=False,
                    obstacle_distance=None,
                    recommended_speed=0,
                    recommended_angle=self.center_angle,
                )
                time.sleep(0.05)
                continue

            result, overlay = self._detect_lane(frame)

            with self._lock:
                self._last_result = result
                self._overlay_frame = overlay

            self.shared_state.update_status(
                camera_connected=result["camera_connected"],
                camera_fps=round(self.camera.get_fps(), 2),
                latest_frame_ts=result["updated_at"],
                lane_offset=result["lane_offset"],
                lane_confidence=result["lane_confidence"],
                obstacle_detected=result["obstacle_detected"],
                obstacle_distance=result["obstacle_distance"],
                recommended_speed=result["recommended_speed"],
                recommended_angle=result["recommended_angle"],
            )
            time.sleep(0.03)