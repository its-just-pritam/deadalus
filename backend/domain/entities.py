"""Database-independent entities used by application services and APIs."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Crew:
    crew_id: str
    name: str
    rank: str
    base: str
    seniority: int
    reachability_minutes: int
    status: str
    ratings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Flight:
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


@dataclass(frozen=True)
class PairingCrew:
    crew_id: str
    role: str


@dataclass(frozen=True)
class PairingDay:
    date: str
    report_utc: str
    release_utc: str
    flight_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pairing:
    pairing_id: str
    aircraft: str
    crew: tuple[PairingCrew, ...] = ()
    days: tuple[PairingDay, ...] = ()


@dataclass(frozen=True)
class FlaggedException:
    crew_id: str
    date: str
    rule: str
    note: str


@dataclass(frozen=True)
class Roster:
    note: str | None
    pairings: tuple[Pairing, ...] = ()
    flagged_exceptions: tuple[FlaggedException, ...] = ()


@dataclass(frozen=True)
class ReserveWindow:
    start: str
    end: str


@dataclass(frozen=True)
class Reserve:
    crew_id: str
    base: str
    note: str | None
    dates: tuple[str, ...] = ()
    oncall_window_utc: ReserveWindow | None = None


@dataclass(frozen=True)
class Certification:
    crew_id: str
    cert_type: str
    valid_from: str
    valid_to: str


@dataclass(frozen=True)
class DutyHistory:
    date: str
    duty_hours: float
    flight_hours: float


@dataclass(frozen=True)
class DutyClock:
    crew_id: str
    as_of_utc: str
    duty_hours_7d: float
    flight_hours_28d: float
    last_rest_ended: str
    daily_history: tuple[DutyHistory, ...] = ()


@dataclass(frozen=True)
class RiskSignal:
    crew_id: str
    as_of_utc: str
    disruption_risk_score: float
    drivers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostConfig:
    currency: str
    reserve_callout_pilot: int
    reserve_callout_cabin: int
    dayoff_callout_pilot: int
    dayoff_callout_cabin: int
    deadhead_positioning: int
    delay_cost_per_duty_hour: int
    cancellation_per_flight: int
    hotel_overnight: int
    notes: str | None


@dataclass(frozen=True)
class RuleParameters:
    base_fdp_hours: float | None = None
    reduction_per_extra_sector_hours: float | None = None
    free_sectors: int | None = None
    max_duty_hours: int | None = None
    window_days: int | None = None
    max_flight_hours: int | None = None
    min_rest_hours: int | None = None


@dataclass(frozen=True)
class Rule:
    rule_id: str
    text: str
    parameters: RuleParameters = field(default_factory=RuleParameters)


@dataclass(frozen=True)
class Ruleset:
    time_convention: str
    definitions: dict[str, str] = field(default_factory=dict)
    rules: tuple[Rule, ...] = ()


@dataclass(frozen=True)
class ScenarioEvent:
    type: str
    crew_id: str | None
    pairing_id: str | None
    reported_utc: str | None
    narrative: str | None
    station: str | None
    aircraft: str | None
    date: str | None
    delay_hours: float | None


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    difficulty: str
    title: str
    event: ScenarioEvent | None = None
    answer_key: "ScenarioAnswerKey | None" = None


@dataclass(frozen=True)
class Question:
    question_id: str
    tier: int
    prompt: str
    expected_answer: object
    explanation: str
    rules_ref: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioOption:
    action: str
    crew_id: str | None
    legal: bool
    cost_inr: int | None
    delay_hours: float | None
    rank: int | None
    reasoning: str | None = None
    rules_checked: tuple[str, ...] = ()


@dataclass(frozen=True)
class PerFlightAssessment:
    flight_id: str
    pairing_id: str | None
    min_delay_hours: float | None
    crew_fdp_after_delay: float | None
    fdp_limit: float | None
    action: str | None


@dataclass(frozen=True)
class ScenarioAnswerKey:
    passengers_at_risk_day1: int | None = None
    note: str | None = None
    fdp_after_delay: float | None = None
    fdp_limit: float | None = None
    breach: bool | None = None
    breach_detail: str | None = None
    affected_flights: tuple[str, ...] = ()
    uncovered_flights: tuple[str, ...] = ()
    uncovered_flights_day1: tuple[str, ...] = ()
    uncovered_flights_day2: tuple[str, ...] = ()
    options: tuple[ScenarioOption, ...] = ()
    expected_choice: ScenarioOption | None = None
    excluded_candidates: tuple[tuple[str, str], ...] = ()
    excluded_dxa: tuple[tuple[str, str], ...] = ()
    excluded_dxb: tuple[tuple[str, str], ...] = ()
    illegal_assignment: tuple[str, str, str] | None = None
    per_flight_assessment: tuple[PerFlightAssessment, ...] = ()
    optimal_joint_plan_total_cost_inr: int | None = None
    optimal_joint_plan_dxa: ScenarioOption | None = None
    optimal_joint_plan_dxb: ScenarioOption | None = None
