import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


@dataclass
class Settings:
    serial_port: str = os.getenv("CAR_SERIAL_PORT", "COM6")
    serial_baud: int = _env_int("CAR_SERIAL_BAUD", 115200)
    heartbeat_period_ms: int = _env_int("CAR_HEARTBEAT_PERIOD_MS", 250)
    read_timeout_ms: int = _env_int("CAR_READ_TIMEOUT_MS", 100)
    telem_period_ms: int = _env_int("CAR_TELEM_PERIOD_MS", 200)
    auto_enable_telem: bool = os.getenv("CAR_AUTO_ENABLE_TELEM", "1") == "1"
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = _env_int("API_PORT", 8000)


settings = Settings()