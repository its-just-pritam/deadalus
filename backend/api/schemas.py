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


class DutyHistoryResponse(BaseModel):
    date: str
    duty_hours: float
    flight_hours: float


class DutyClockResponse(BaseModel):
    crew_id: str
    as_of_utc: str
    duty_hours_7d: float
    flight_hours_28d: float
    last_rest_ended: str
    daily_history: list[DutyHistoryResponse]


class DutyHeadroomResponse(BaseModel):
    crew_id: str
    as_of_utc: str
    duty_hours_7d: float
    max_duty_hours_7d: float
    headroom_hours: float
    rule_id: str


class RuleResponse(BaseModel):
    rule_id: str
    text: str
    parameters: dict[str, float | int | None]


class FlightResponse(BaseModel):
    flight_id: str
    flight_no: str
    date: str
    dep_station: str
    arr_station: str
    dep_utc: str
    arr_utc: str
    block_hours: float
    aircraft: str
    aircraft_type: str
    seats: int
