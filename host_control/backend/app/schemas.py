from typing import Literal, Optional
from pydantic import BaseModel, Field


class ModeRequest(BaseModel):
    mode: Literal["MANUAL", "ASSISTED", "AUTO_TEST"]


class MotorRequest(BaseModel):
    speed: int = Field(ge=-300, le=300)


class ServoRequest(BaseModel):
    angle: int = Field(ge=60, le=120)


class DriveRequest(BaseModel):
    speed: int = Field(ge=-300, le=300)
    angle: int = Field(ge=60, le=120)


class TelemRequest(BaseModel):
    enabled: bool
    period_ms: Optional[int] = Field(default=200, ge=50, le=5000)