import threading
import time
from typing import Optional

import serial
from serial import SerialException

from app.config import Settings
from app.parser import parse_line
from app.state import SharedState


class SerialManager:
    def __init__(self, settings: Settings, state: SharedState) -> None:
        self.settings = settings
        self.state = state
        self.ser: Optional[serial.Serial] = None

        self._running = False
        self._write_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

        self._reader_thread.start()
        self._heartbeat_thread.start()

    def stop(self) -> None:
        self._running = False
        self._close_serial()

    def _open_serial(self) -> None:
        self.ser = serial.Serial(
            self.settings.serial_port,
            self.settings.serial_baud,
            timeout=self.settings.read_timeout_ms / 1000.0,
        )
        self.state.update_connection(True)
        self.state.add_event("INFO", f"Serial connected: {self.settings.serial_port}")

        time.sleep(1.0)
        self.send_command("STATUS")

        if self.settings.auto_enable_telem:
            self.send_command(f"TELEM 1 {self.settings.telem_period_ms}")

    def _close_serial(self) -> None:
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.state.update_connection(False)

    def _reader_loop(self) -> None:
        while self._running:
            if self.ser is None or not self.ser.is_open:
                try:
                    self._open_serial()
                except Exception as e:
                    self.state.add_event("WARN", f"Serial open failed: {e}")
                    self.state.update_connection(False)
                    time.sleep(1.0)
                    continue

            try:
                line = self.ser.readline()
                if line:
                    text = line.decode("utf-8", errors="ignore").strip()
                    if text:
                        parsed = parse_line(text)
                        self.state.apply_message(parsed, text)

            except SerialException as e:
                self.state.add_event("WARN", f"Serial read failed: {e}")
                self._close_serial()
                time.sleep(1.0)

            except Exception as e:
                self.state.add_event("WARN", f"Reader error: {e}")
                self._close_serial()
                time.sleep(1.0)

    def _heartbeat_loop(self) -> None:
        sleep_s = self.settings.heartbeat_period_ms / 1000.0

        while self._running:
            try:
                if self.ser and self.ser.is_open:
                    self.send_command("HEARTBEAT")
            except Exception as e:
                self.state.add_event("WARN", f"Heartbeat failed: {e}")
                self._close_serial()

            time.sleep(sleep_s)

    def send_command(self, cmd: str) -> None:
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial is not connected")

        with self._write_lock:
            self.ser.write((cmd.strip() + "\n").encode("utf-8"))
            self.ser.flush()