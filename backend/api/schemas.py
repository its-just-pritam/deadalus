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


class ReserveDetailResponse(ReserveResponse):
    name: str
    seniority: int
    reachability_minutes: int
    status: str
    ratings: list[str]


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


class FlightCountResponse(BaseModel):
    date: str
    flight_count: int


class LongestBlockResponse(BaseModel):
    block_hours: float
    flights: list[str]


class CertificationResponse(BaseModel):
    crew_id: str
    cert_type: str
    valid_from: str
    valid_to: str


class PairingCrewResponse(BaseModel):
    crew_id: str
    role: str


class PairingDayResponse(BaseModel):
    date: str
    report_utc: str
    release_utc: str
    flight_ids: list[str]


class PairingResponse(BaseModel):
    pairing_id: str
    aircraft: str
    crew: list[PairingCrewResponse]
    days: list[PairingDayResponse]


class RiskSignalResponse(BaseModel):
    crew_id: str
    as_of_utc: str
    disruption_risk_score: float
    drivers: list[str]


class StationDestinationsResponse(BaseModel):
    station: str
    destinations: list[str]


class UncrewedFlightsResponse(BaseModel):
    crew_id: str
    pairing_id: str
    day1: list[str]
    day2_also_at_risk: list[str]
    passengers_day1: int


class LegalityResponse(BaseModel):
    crew_id: str
    pairing_id: str
    legal: bool
    issues: list[str]


class AffectedFlightResponse(BaseModel):
    flight_id: str
    flight_no: str
    date: str
    dep_station: str
    arr_station: str
    dep_utc: str
    arr_utc: str


class FdpCheckResponse(BaseModel):
    aircraft: str
    date: str
    delay_hours: float
    sectors: int
    fdp_after_delay: float
    fdp_limit: float
    breach: bool


class QualificationResponse(BaseModel):
    crew_id: str
    aircraft_type: str
    date: str
    qualified: bool
    ratings: list[str]
    certification_issues: list[str]


class PairingLegalityResponse(BaseModel):
    crew_id: str
    pairing_id: str
    date: str
    legal: bool
    issues: list[str]
    consequence: str | None = None


class RestCheckResponse(BaseModel):
    crew_id: str | None
    release_utc: str
    minimum_rest_hours: float
    earliest_next_report_utc: str
    legal: bool


class CancellationImpactResponse(BaseModel):
    flight_id: str
    passengers: int
    cancellation_cost_inr: int


class AtRiskCrewResponse(BaseModel):
    crew_id: str
    duty_hours_7d_including_plan: float


class ReserveEligibilityResponse(BaseModel):
    eligible: list[str]
    excluded: dict[str, str]


class DownstreamRestResponse(BaseModel):
    crew_id: str
    pairing_id: str
    legal: bool
    issues: list[str]


class SeatRiskResponse(BaseModel):
    seats: int
    aircraft_types: list[str]
    flights: list[str]


class RecoveryOptionResponse(BaseModel):
    action: str
    crew_id: str | None
    legal: bool
    cost_inr: int | None
    delay_hours: float | None
    rank: int | None
    reasoning: str


class RankedRecoveryResponse(BaseModel):
    pairing_id: str
    options: list[RecoveryOptionResponse]


class JointPlanResponse(BaseModel):
    date: str
    total_cost_inr: int
    assignments: dict[str, RecoveryOptionResponse]
