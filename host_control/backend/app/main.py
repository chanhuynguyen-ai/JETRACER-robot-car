import asyncio
from typing import Any, Optional, Tuple

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .camera import CameraManager
from .perception import PerceptionManager
from .assisted_driver import AssistedDriver
from .config import settings
from .serial_manager import SerialManager
from .state import shared_state


# =========================
# Request schemas
# =========================

class ModeRequest(BaseModel):
    mode: str = Field(..., description="MANUAL / ASSISTED / AUTO_TEST")


class MotorRequest(BaseModel):
    speed: int = Field(..., ge=-1023, le=1023)


class ServoRequest(BaseModel):
    angle: int = Field(..., ge=0, le=180)


class DriveRequest(BaseModel):
    speed: int = Field(..., ge=-1023, le=1023)
    angle: int = Field(..., ge=0, le=180)


class TelemRequest(BaseModel):
    enabled: bool
    period_ms: int = Field(default=200, ge=50, le=5000)


# =========================
# App
# =========================

app = FastAPI(
    title="Car Host Bridge",
    version="0.2.1",
    description="ESP32 car bridge + camera + perception + assisted mode",
)

# IMPORTANT:
# - allow localhost for laptop dev
# - allow LAN IP frontend such as http://192.168.1.32:5173
# - allow other 192.168.x.x / 10.x.x.x / 172.16-31.x.x dev clients via regex
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://192.168.1.32:5173",
    ],
    allow_origin_regex=r"^https?://((localhost)|(127\.0\.0\.1)|(192\.168\.\d+\.\d+)|(10\.\d+\.\d+\.\d+)|(172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+))(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Shared core objects
# =========================

serial_manager = SerialManager(settings, shared_state)

camera_manager = CameraManager(
    index=0,
    width=640,
    height=480,
    fps=30,
)

perception_manager = PerceptionManager(
    camera=camera_manager,
    shared_state=shared_state,
)


# =========================
# Shared-state helpers
# =========================

def _state_add_event(kind: str, message: str) -> None:
    if hasattr(shared_state, "add_event") and callable(shared_state.add_event):
        shared_state.add_event(kind, message)
        return

    if hasattr(shared_state, "push_event") and callable(shared_state.push_event):
        shared_state.push_event(kind, message)
        return


def _state_update(**kwargs: Any) -> None:
    if hasattr(shared_state, "update_status") and callable(shared_state.update_status):
        shared_state.update_status(**kwargs)
        return

    if hasattr(shared_state, "_lock") and hasattr(shared_state, "_status"):
        with shared_state._lock:
            shared_state._status.update(kwargs)
        return


def _state_get_status() -> dict:
    if hasattr(shared_state, "get_status") and callable(shared_state.get_status):
        return shared_state.get_status()

    if hasattr(shared_state, "snapshot") and callable(shared_state.snapshot):
        snap = shared_state.snapshot()
        if isinstance(snap, dict) and "status" in snap:
            return snap["status"]

    if hasattr(shared_state, "_status"):
        return dict(shared_state._status)

    return {}


def _state_get_events(limit: int = 50) -> list[dict]:
    if hasattr(shared_state, "get_events") and callable(shared_state.get_events):
        try:
            return shared_state.get_events(limit=limit)
        except TypeError:
            return shared_state.get_events()

    if hasattr(shared_state, "snapshot") and callable(shared_state.snapshot):
        try:
            snap = shared_state.snapshot(limit=limit)
        except TypeError:
            snap = shared_state.snapshot()
        if isinstance(snap, dict) and "events" in snap:
            return snap["events"][:limit]

    return []


def _state_snapshot(limit: int = 50) -> dict:
    if hasattr(shared_state, "snapshot") and callable(shared_state.snapshot):
        try:
            return shared_state.snapshot(limit=limit)
        except TypeError:
            return shared_state.snapshot()

    return {
        "status": _state_get_status(),
        "events": _state_get_events(limit=limit),
    }


# =========================
# Serial helpers
# =========================

def _serial_is_connected() -> bool:
    ser = getattr(serial_manager, "ser", None)
    return bool(ser and getattr(ser, "is_open", False))


def _send_command(cmd: str) -> Tuple[bool, Optional[str]]:
    try:
        serial_manager.send_command(cmd)
        return True, None
    except RuntimeError as e:
        _state_update(connected=False)
        _state_add_event("WARN", f"SEND_FAILED {cmd}: {e}")
        return False, str(e)
    except Exception as e:
        _state_add_event("ERROR", f"SEND_EXCEPTION {cmd}: {e}")
        raise HTTPException(status_code=500, detail=f"Send command failed: {e}")


def send_mode(mode: str) -> Tuple[bool, Optional[str]]:
    mode = mode.strip().upper()
    return _send_command(f"MODE {mode}")


def send_motor(speed: int) -> Tuple[bool, Optional[str]]:
    return _send_command(f"MOTOR {speed}")


def send_servo(angle: int) -> Tuple[bool, Optional[str]]:
    return _send_command(f"SERVO {angle}")


def send_drive(speed: int, angle: int) -> Tuple[bool, Optional[str]]:
    return _send_command(f"DRIVE {speed} {angle}")


def send_stop() -> Tuple[bool, Optional[str]]:
    return _send_command("STOP")


def send_telem(enabled: bool, period_ms: int) -> Tuple[bool, Optional[str]]:
    flag = 1 if enabled else 0
    return _send_command(f"TELEM {flag} {period_ms}")


def assisted_send_drive(speed: int, angle: int) -> None:
    ok, err = send_drive(speed, angle)
    if not ok:
        raise RuntimeError(err or "Serial is not connected")


def assisted_send_stop() -> None:
    ok, err = send_stop()
    if not ok:
        raise RuntimeError(err or "Serial is not connected")


assisted_driver = AssistedDriver(
    shared_state=shared_state,
    send_drive=assisted_send_drive,
    send_stop=assisted_send_stop,
)


# =========================
# Startup / Shutdown
# =========================

@app.on_event("startup")
async def startup_event():
    serial_manager.start()
    camera_manager.start()
    perception_manager.start()
    assisted_driver.start()
    _state_add_event("INFO", "Camera + Perception + Assisted started")


@app.on_event("shutdown")
async def shutdown_event():
    assisted_driver.stop()
    perception_manager.stop()
    camera_manager.stop()
    serial_manager.stop()


# =========================
# Root / Health
# =========================

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "car-host-bridge",
        "docs": "/docs",
    }


@app.get("/api/health")
def api_health():
    return {
        "ok": True,
        "serial_connected": _serial_is_connected(),
        "camera": camera_manager.snapshot(),
    }


# =========================
# Core status endpoints
# =========================

@app.get("/api/status")
def get_status():
    return _state_get_status()


@app.get("/api/events")
def get_events(limit: int = 50):
    return _state_get_events(limit=limit)


# =========================
# Manual car control
# =========================

@app.post("/api/mode")
def api_set_mode(payload: ModeRequest):
    mode = payload.mode.upper()
    ok, err = send_mode(mode)

    if ok:
        _state_update(mode=mode)
        _state_add_event("INFO", f"MODE -> {mode}")
    return {
        "ok": ok,
        "mode": mode,
        "connected": _serial_is_connected(),
        "detail": err,
    }


@app.post("/api/motor")
def api_set_motor(payload: MotorRequest):
    ok, err = send_motor(payload.speed)

    if ok:
        _state_update(motor=payload.speed)
        _state_add_event("INFO", f"MOTOR -> {payload.speed}")
    return {
        "ok": ok,
        "speed": payload.speed,
        "connected": _serial_is_connected(),
        "detail": err,
    }


@app.post("/api/servo")
def api_set_servo(payload: ServoRequest):
    ok, err = send_servo(payload.angle)

    if ok:
        _state_update(angle=payload.angle)
        _state_add_event("INFO", f"SERVO -> {payload.angle}")
    return {
        "ok": ok,
        "angle": payload.angle,
        "connected": _serial_is_connected(),
        "detail": err,
    }


@app.post("/api/drive")
def api_set_drive(payload: DriveRequest):
    ok, err = send_drive(payload.speed, payload.angle)

    if ok:
        _state_update(motor=payload.speed, angle=payload.angle)
        _state_add_event("INFO", f"DRIVE -> speed={payload.speed} angle={payload.angle}")
    return {
        "ok": ok,
        "speed": payload.speed,
        "angle": payload.angle,
        "connected": _serial_is_connected(),
        "detail": err,
    }


@app.post("/api/stop")
def api_stop():
    ok, err = send_stop()

    _state_update(motor=0)
    if ok:
        _state_add_event("INFO", "STOP")
    else:
        _state_add_event("WARN", "STOP requested while serial disconnected")

    return {
        "ok": ok,
        "connected": _serial_is_connected(),
        "detail": err,
    }


@app.post("/api/telem")
def api_set_telem(payload: TelemRequest):
    ok, err = send_telem(payload.enabled, payload.period_ms)

    if ok:
        _state_add_event(
            "INFO",
            f"TELEM -> enabled={payload.enabled} period_ms={payload.period_ms}",
        )
    return {
        "ok": ok,
        "enabled": payload.enabled,
        "period_ms": payload.period_ms,
        "connected": _serial_is_connected(),
        "detail": err,
    }


# =========================
# Camera endpoints
# =========================

@app.get("/api/camera/status")
def get_camera_status():
    return camera_manager.snapshot()


@app.get("/api/camera/frame")
def get_camera_frame():
    jpeg = perception_manager.get_overlay_jpeg()
    if jpeg is None:
        jpeg = camera_manager.get_jpeg()

    if jpeg is None:
        raise HTTPException(status_code=503, detail="Camera frame not ready")

    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/api/camera/mjpeg")
def get_camera_mjpeg():
    return StreamingResponse(
        camera_manager.mjpeg_generator(
            frame_provider=perception_manager.get_overlay_frame
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# =========================
# Perception endpoints
# =========================

@app.get("/api/perception/status")
def get_perception_status():
    return perception_manager.snapshot()


# =========================
# Assisted mode endpoints
# =========================

@app.post("/api/assisted/enable")
def enable_assisted():
    _state_update(assisted_enabled=True)
    _state_add_event("INFO", "ASSISTED enabled")
    return {"ok": True, "assisted_enabled": True}


@app.post("/api/assisted/disable")
def disable_assisted():
    _state_update(assisted_enabled=False)
    _state_add_event("INFO", "ASSISTED disabled")
    return {"ok": True, "assisted_enabled": False}


# =========================
# WebSocket state
# =========================

@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(_state_snapshot(limit=30))
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        return
    except Exception:
        return