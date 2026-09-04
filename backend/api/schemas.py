"""API response schemas."""

from pydantic import BaseModel


class OnCallWindowResponse(BaseModel):
    start: str
    end: str


class CrewResponse(BaseModel):
    crew_id: str
    name: str
    rank: str
    base: str
    seniority: int
    reachability_minutes: int
    status: str
    ratings: list[str]


class ReserveResponse(BaseModel):
    crew_id: str
    rank: str
    base: str
    note: str | None
    dates: list[str]
    oncall_window_utc: OnCallWindowResponse | None
