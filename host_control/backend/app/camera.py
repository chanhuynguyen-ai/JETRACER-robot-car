import platform
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np


class CameraManager:
    def __init__(
        self,
        index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        jpeg_quality: int = 80,
    ) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

        self._frame: Optional[np.ndarray] = None
        self._connected = False
        self._last_frame_ts = 0.0
        self._measured_fps = 0.0
        self._frame_counter = 0
        self._fps_window_start = time.time()

    def _open_camera(self) -> Optional[cv2.VideoCapture]:
        api = cv2.CAP_DSHOW if platform.system().lower() == "windows" else 0
        cap = cv2.VideoCapture(self.index, api)
        if not cap or not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _reader_loop(self) -> None:
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                self._cap = self._open_camera()
                if self._cap is None:
                    with self._lock:
                        self._connected = False
                    time.sleep(1.0)
                    continue

            ok, frame = self._cap.read()
            if not ok or frame is None:
                with self._lock:
                    self._connected = False
                self._cap.release()
                self._cap = None
                time.sleep(0.2)
                continue

            now = time.time()
            self._frame_counter += 1
            elapsed = now - self._fps_window_start
            if elapsed >= 1.0:
                self._measured_fps = self._frame_counter / elapsed
                self._frame_counter = 0
                self._fps_window_start = now

            with self._lock:
                self._frame = frame.copy()
                self._connected = True
                self._last_frame_ts = now

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def get_fps(self) -> float:
        with self._lock:
            return self._measured_fps

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def encode_jpeg(
        self,
        frame: np.ndarray,
        quality: Optional[int] = None,
    ) -> Optional[bytes]:
        q = self.jpeg_quality if quality is None else quality
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(q)],
        )
        if not ok:
            return None
        return encoded.tobytes()

    def get_jpeg(self) -> Optional[bytes]:
        frame = self.get_frame()
        if frame is None:
            return None
        return self.encode_jpeg(frame)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connected": self._connected,
                "index": self.index,
                "width": self.width,
                "height": self.height,
                "target_fps": self.fps,
                "measured_fps": round(self._measured_fps, 2),
                "last_frame_ts": self._last_frame_ts,
            }

    def mjpeg_generator(
        self,
        frame_provider: Optional[Callable[[], Optional[np.ndarray]]] = None,
    ):
        while True:
            frame = frame_provider() if frame_provider else self.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            jpeg = self.encode_jpeg(frame)
            if jpeg is None:
                time.sleep(0.05)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )
            time.sleep(0.03)