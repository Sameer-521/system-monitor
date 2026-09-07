from typing import Any

from pydantic import BaseModel, Field, PositiveInt


class Register(BaseModel):
    username: str


class Snapshot(BaseModel):
    info: dict[str, Any]


class TicketResponse(BaseModel):
    ticket: str


class TicketHeader(BaseModel):
    x_ticket: str


class ProcessPidParam(BaseModel):
    model_config = {"extra": "forbid"}
    pid: PositiveInt


class MetricsParams(BaseModel):
    model_config = {"extra": "forbid"}
    cpu: bool = Field(default=True)
    memory: bool = Field(default=True)
    disk: bool = Field(default=True)
    network: bool = Field(default=True)
    processes: bool = Field(default=False)
    containers: bool = Field(default=False)
    alerts: bool = Field(default=True)
