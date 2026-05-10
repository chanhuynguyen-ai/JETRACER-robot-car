import sys
import time
import threading
import serial


class SerialCarClient:
    def __init__(self, port: str, baudrate: int = 115200, heartbeat_period: float = 0.25):
        self.port = port
        self.baudrate = baudrate
        self.heartbeat_period = heartbeat_period
        self.ser = serial.Serial(port, baudrate, timeout=0.1)
        self._running = True
        self._hb_enabled = True

        self.show_heartbeat_ack = False
        self.show_telemetry = True

        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

        self._reader_thread.start()
        self._hb_thread.start()

    def _reader_loop(self):
        while self._running:
            try:
                line = self.ser.readline()
                if line:
                    text = line.decode("utf-8", errors="ignore").strip()
                    if not text:
                        continue

                    if text == "ACK HEARTBEAT" and not self.show_heartbeat_ack:
                        continue

                    if text.startswith("TEL ") and not self.show_telemetry:
                        continue

                    print(f"<< {text}")
            except Exception as e:
                print(f"[READER ERROR] {e}")
                break

    def _heartbeat_loop(self):
        while self._running:
            try:
                if self._hb_enabled and self.ser.is_open:
                    self.send("HEARTBEAT", echo=False)
                time.sleep(self.heartbeat_period)
            except Exception as e:
                print(f"[HEARTBEAT ERROR] {e}")
                break

    def send(self, cmd: str, echo: bool = True):
        if not self.ser.is_open:
            raise RuntimeError("Serial port is closed")
        data = (cmd.strip() + "\n").encode("utf-8")
        self.ser.write(data)
        if echo:
            print(f">> {cmd}")

    def close(self):
        self._running = False
        time.sleep(0.2)
        try:
            if self.ser.is_open:
                self.ser.close()
        except Exception:
            pass


def print_help():
    print("""
Commands:
  ping
  status
  help
  stop
  mode manual
  mode assisted
  mode auto_test
  motor <speed>
  servo <angle>
  drive <speed> <angle>
  telem on <ms>
  telem off
  hb on
  hb off
  show tel
  hide tel
  show hb
  hide hb
  quit
""")


def main():
    if len(sys.argv) < 2:
        print("Usage: python serial_car_client.py COM5")
        return

    port = sys.argv[1]
    client = SerialCarClient(port=port)

    print(f"Connected to {port}")
    print_help()

    time.sleep(1.0)
    client.send("STATUS")
    client.send("TELEM 1 1000")
    client.send("MODE MANUAL")

    try:
        while True:
            raw = input("cmd> ").strip()
            if not raw:
                continue

            low = raw.lower()

            if low == "quit":
                client.send("STOP")
                break

            if low == "help":
                print_help()
                continue

            if low == "ping":
                client.send("PING")
                continue

            if low == "status":
                client.send("STATUS")
                continue

            if low == "stop":
                client.send("STOP")
                continue

            if low.startswith("mode "):
                _, arg = raw.split(maxsplit=1)
                client.send(f"MODE {arg.upper()}")
                continue

            if low.startswith("motor "):
                _, arg = raw.split(maxsplit=1)
                client.send(f"MOTOR {arg}")
                continue

            if low.startswith("servo "):
                _, arg = raw.split(maxsplit=1)
                client.send(f"SERVO {arg}")
                continue

            if low.startswith("drive "):
                parts = raw.split()
                if len(parts) != 3:
                    print("Usage: drive <speed> <angle>")
                    continue
                client.send(f"DRIVE {parts[1]} {parts[2]}")
                continue

            if low.startswith("telem "):
                parts = raw.split()
                if len(parts) == 2 and parts[1].lower() == "off":
                    client.send("TELEM 0")
                    continue
                if len(parts) == 3 and parts[1].lower() == "on":
                    client.send(f"TELEM 1 {parts[2]}")
                    continue
                print("Usage: telem on <ms> | telem off")
                continue

            if low == "hb on":
                client._hb_enabled = True
                print("[INFO] heartbeat enabled")
                continue

            if low == "hb off":
                client._hb_enabled = False
                print("[INFO] heartbeat disabled")
                continue

            if low == "show tel":
                client.show_telemetry = True
                print("[INFO] telemetry visible")
                continue

            if low == "hide tel":
                client.show_telemetry = False
                print("[INFO] telemetry hidden")
                continue

            if low == "show hb":
                client.show_heartbeat_ack = True
                print("[INFO] heartbeat ACK visible")
                continue

            if low == "hide hb":
                client.show_heartbeat_ack = False
                print("[INFO] heartbeat ACK hidden")
                continue

            print("Unknown command. Type 'help'.")

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    finally:
        try:
            client.send("STOP")
        except Exception:
            pass
        client.close()
        print("Disconnected")


if __name__ == "__main__":
    main()