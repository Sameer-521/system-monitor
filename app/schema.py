from pydantic import BaseModel, Field


class Register(BaseModel):
    username: str


class Snapshot(BaseModel):
    info: dict


class TicketResponse(BaseModel):
    ticket: str


class MetricsParams(BaseModel):
    cpu: bool = Field(default=False)
    memory: bool = Field(default=False)
    disk: bool = Field(default=False)
    network: bool = Field(default=False)
    processes: bool = Field(default=False)
    containers: bool = Field(default=False)
    alerts: bool = Field(default=False)
