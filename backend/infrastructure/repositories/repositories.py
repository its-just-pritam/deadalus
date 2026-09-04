"""Read repositories over the generated crew_operations SQLite schema."""

import json
import sqlite3
from typing import Any

from backend.domain.entities import (
    Certification,
    CostConfig,
    Crew,
    DutyClock,
    DutyHistory,
    Flight,
    Pairing,
    PairingCrew,
    PairingDay,
    Reserve,
    ReserveWindow,
    RiskSignal,
    Rule,
    RuleParameters,
    Ruleset,
    Scenario,
    ScenarioAnswerKey,
    ScenarioEvent,
    ScenarioOption,
    PerFlightAssessment,
    Question,
    Roster,
    FlaggedException,
)


class CrewRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, crew_id: str) -> Crew | None:
        row = self.connection.execute(
            "SELECT * FROM crew WHERE crew_id = ?", (crew_id,)
        ).fetchone()
        if row is None:
            return None
        ratings = self.connection.execute(
            "SELECT value FROM crew_ratings WHERE parent_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        return Crew(
            crew_id=row["crew_id"], name=row["name"], rank=row["rank"],
            base=row["base"], seniority=row["seniority"],
            reachability_minutes=row["reachability_minutes"], status=row["status"],
            ratings=tuple(item["value"] for item in ratings),
        )

    def list(self, *, status: str | None = None) -> list[Crew]:
        query = "SELECT crew_id FROM crew"
        args: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            args = (status,)
        query += " ORDER BY crew_id"
        return [crew for row in self.connection.execute(query, args)
                if (crew := self.get(row["crew_id"])) is not None]


class FlightRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, flight_id: str) -> Flight | None:
        row = self.connection.execute(
            "SELECT * FROM flights WHERE flight_id = ?", (flight_id,)
        ).fetchone()
        if row is None:
            return None
        return Flight(**{key: row[key] for key in (
            "flight_id", "flight_no", "date", "dep_station", "arr_station",
            "dep_utc", "arr_utc", "block_hours", "aircraft", "aircraft_type",
            "seats")})

    def list(
        self,
        *,
        date: str | None = None,
        departure_station: str | None = None,
        arrival_station: str | None = None,
    ) -> list[Flight]:
        query = "SELECT flight_id FROM flights"
        conditions: list[str] = []
        args: list[str] = []
        if date is not None:
            conditions.append("date = ?")
            args.append(date)
        if departure_station is not None:
            conditions.append("dep_station = ?")
            args.append(departure_station)
        if arrival_station is not None:
            conditions.append("arr_station = ?")
            args.append(arrival_station)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY dep_utc, flight_id"
        return [flight for row in self.connection.execute(query, args)
                if (flight := self.get(row["flight_id"])) is not None]


class PairingRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, pairing_id: str) -> Pairing | None:
        row = self.connection.execute(
            "SELECT * FROM rosters_pairings WHERE pairing_id = ?", (pairing_id,)
        ).fetchone()
        if row is None:
            return None
        crew = tuple(PairingCrew(item["crew_id"], item["role"]) for item in
                     self.connection.execute(
                         "SELECT crew_id, role FROM rosters_pairings_crew "
                         "WHERE parent_id = ? ORDER BY id", (row["id"],)))
        days = []
        for day in self.connection.execute(
            "SELECT * FROM rosters_pairings_days WHERE parent_id = ? ORDER BY date",
            (row["id"],),
        ):
            flights = tuple(item["value"] for item in self.connection.execute(
                "SELECT value FROM rosters_pairings_days_flights "
                "WHERE parent_id = ? ORDER BY id", (day["id"],)))
            days.append(PairingDay(day["date"], day["report_utc"],
                                   day["release_utc"], flights))
        return Pairing(row["pairing_id"], row["aircraft"], crew, tuple(days))

    def list(self) -> list[Pairing]:
        return [pairing for row in self.connection.execute(
            "SELECT pairing_id FROM rosters_pairings ORDER BY pairing_id"
        ) if (pairing := self.get(row["pairing_id"])) is not None]


class RosterRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self) -> Roster | None:
        root = self.connection.execute("SELECT * FROM rosters LIMIT 1").fetchone()
        if root is None:
            return None
        pairings = PairingRepository(self.connection).list()
        exceptions = tuple(FlaggedException(*row) for row in self.connection.execute(
            "SELECT crew_id, date, rule, note FROM rosters_flagged_exceptions "
            "WHERE parent_id = ? ORDER BY id", (root["id"],)))
        return Roster(root["note"], tuple(pairings), exceptions)


class ReserveRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, crew_id: str) -> Reserve | None:
        row = self.connection.execute(
            "SELECT * FROM reserve_pool WHERE crew_id = ?", (crew_id,)
        ).fetchone()
        if row is None:
            return None
        window = self.connection.execute(
            "SELECT start, end FROM reserve_pool_oncall_window_utc "
            "WHERE parent_id = ?", (row["id"],)
        ).fetchone()
        dates = tuple(item["value"] for item in self.connection.execute(
            "SELECT value FROM reserve_pool_dates WHERE parent_id = ? ORDER BY id",
            (row["id"],)))
        return Reserve(row["crew_id"], row["base"], row["note"], dates,
                       ReserveWindow(window["start"], window["end"]) if window else None)

    def list(self, *, date: str | None = None, base: str | None = None) -> list[Reserve]:
        query = "SELECT crew_id FROM reserve_pool"
        conditions: list[str] = []
        args: list[str] = []
        if base is not None:
            conditions.append("base = ?")
            args.append(base)
        if date is not None:
            conditions.append(
                "EXISTS (SELECT 1 FROM reserve_pool_dates d "
                "WHERE d.parent_id = reserve_pool.id AND d.value = ?)"
            )
            args.append(date)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY crew_id"
        return [
            reserve for row in self.connection.execute(query, args)
            if (reserve := self.get(row["crew_id"])) is not None
        ]


class CertificationRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def list_for_crew(self, crew_id: str) -> list[Certification]:
        rows = self.connection.execute(
            "SELECT crew_id, cert_type, valid_from, valid_to FROM certifications "
            "WHERE crew_id = ? ORDER BY valid_to, cert_type", (crew_id,))
        return [Certification(*row) for row in rows]


class DutyClockRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, crew_id: str) -> DutyClock | None:
        row = self.connection.execute(
            "SELECT * FROM duty_clocks WHERE crew_id = ?", (crew_id,)
        ).fetchone()
        if row is None:
            return None
        history = tuple(DutyHistory(item["date"], item["duty_hours"],
                                     item["flight_hours"]) for item in
                        self.connection.execute(
                            "SELECT date, duty_hours, flight_hours "
                            "FROM duty_clocks_daily_history WHERE parent_id = ? "
                            "ORDER BY date", (row["id"],)))
        return DutyClock(row["crew_id"], row["as_of_utc"], row["duty_hours_7d"],
                         row["flight_hours_28d"], row["last_rest_ended"], history)


class RiskSignalRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, crew_id: str) -> RiskSignal | None:
        row = self.connection.execute(
            "SELECT * FROM risk_signals WHERE crew_id = ?", (crew_id,)
        ).fetchone()
        if row is None:
            return None
        drivers = tuple(item["value"] for item in self.connection.execute(
            "SELECT value FROM risk_signals_drivers WHERE parent_id = ? ORDER BY id",
            (row["id"],)))
        return RiskSignal(row["crew_id"], row["as_of_utc"],
                          row["disruption_risk_score"], drivers)


class CostConfigRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, currency: str = "INR") -> CostConfig | None:
        row = self.connection.execute(
            "SELECT * FROM costs WHERE currency = ?", (currency,)
        ).fetchone()
        if row is None:
            return None
        return CostConfig(*(row[key] for key in (
            "currency", "reserve_callout_pilot", "reserve_callout_cabin",
            "dayoff_callout_pilot", "dayoff_callout_cabin",
            "deadhead_positioning", "delay_cost_per_duty_hour",
            "cancellation_per_flight", "hotel_overnight", "notes")))


class RulesetRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self) -> Ruleset | None:
        root = self.connection.execute("SELECT * FROM rules LIMIT 1").fetchone()
        if root is None:
            return None
        definitions_row = self.connection.execute(
            "SELECT duty_period, fdp, sector, reserve_callout "
            "FROM rules_definitions WHERE parent_id = ?", (root["id"],)
        ).fetchone()
        definitions = dict(definitions_row) if definitions_row else {}
        rules = []
        for row in self.connection.execute(
            "SELECT * FROM rules_rules WHERE parent_id = ? ORDER BY id",
            (root["id"],),
        ):
            params = self.connection.execute(
                "SELECT * FROM rules_rules_params WHERE parent_id = ?",
                (row["id"],),
            ).fetchone()
            values = {key: params[key] for key in (
                "base_fdp_hours", "reduction_per_extra_sector_hours", "free_sectors",
                "max_duty_hours", "window_days", "max_flight_hours",
                "min_rest_hours")} if params else {}
            rules.append(Rule(row["rule_id"], row["text"], RuleParameters(**values)))
        return Ruleset(root["time_convention"], definitions, tuple(rules))

    def get_rule(self, rule_id: str) -> Rule | None:
        ruleset = self.get()
        if ruleset is None:
            return None
        return next((rule for rule in ruleset.rules if rule.rule_id == rule_id), None)


class QuestionRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, question_id: str) -> Question | None:
        row = self.connection.execute(
            "SELECT * FROM questions WHERE question_id = ?", (question_id,)
        ).fetchone()
        if row is None:
            return None
        refs = tuple(item["value"] for item in self.connection.execute(
            "SELECT value FROM questions_rules_ref WHERE parent_id = ? ORDER BY id",
            (row["id"],)))
        return Question(row["question_id"], row["tier"], row["prompt"],
                        json.loads(row["expected_answer"]),
                        row["explanation"], refs)

    def list(self, *, tier: int | None = None) -> list[Question]:
        query = "SELECT question_id FROM questions"
        args: tuple[Any, ...] = ()
        if tier is not None:
            query += " WHERE tier = ?"
            args = (tier,)
        query += " ORDER BY question_id"
        return [question for row in self.connection.execute(query, args)
                if (question := self.get(row["question_id"])) is not None]


class ScenarioRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, scenario_id: str) -> Scenario | None:
        row = self.connection.execute(
            "SELECT * FROM scenarios WHERE scenario_id = ?", (scenario_id,)
        ).fetchone()
        if row is None:
            return None
        event = self.connection.execute(
            "SELECT * FROM scenarios_event WHERE parent_id = ?", (row["id"],)
        ).fetchone()
        answer = self._answer_key(row["id"])
        return Scenario(
            row["scenario_id"], row["difficulty"], row["title"],
            ScenarioEvent(*(event[key] for key in (
                "type", "crew_id", "pairing_id", "reported_utc", "narrative",
                "station", "aircraft", "date", "delay_hours"))) if event else None,
            answer,
        )

    def _values(self, table: str, parent_id: int) -> tuple[str, ...]:
        return tuple(row["value"] for row in self.connection.execute(
            f"SELECT value FROM {table} WHERE parent_id = ? ORDER BY id",
            (parent_id,)))

    def _options(self, table: str, parent_id: int) -> tuple[ScenarioOption, ...]:
        has_reasoning = table in (
            "scenarios_answer_key_options",
            "scenarios_answer_key_expected_choice",
        )
        columns = "id, action, crew_id, legal, cost_inr, delay_hours, rank"
        if has_reasoning:
            columns += ", reasoning"
        rows = self.connection.execute(
            f"SELECT {columns} FROM {table} WHERE parent_id = ? ORDER BY id",
            (parent_id,))
        rules_table = table + "_rules_checked"
        has_rules = table in (
            "scenarios_answer_key_options",
            "scenarios_answer_key_options_dxa",
            "scenarios_answer_key_options_dxb",
            "scenarios_answer_key_expected_choice",
            "scenarios_answer_key_optimal_joint_plan_assign_dxa",
            "scenarios_answer_key_optimal_joint_plan_assign_dxb",
        )
        return tuple(ScenarioOption(
            row["action"], row["crew_id"], bool(row["legal"]),
            row["cost_inr"], row["delay_hours"], row["rank"],
            row["reasoning"] if has_reasoning else None,
            self._values(rules_table, row["id"]) if has_rules else (),
        ) for row in rows)

    def _answer_key(self, scenario_parent_id: int) -> ScenarioAnswerKey | None:
        root = self.connection.execute(
            "SELECT * FROM scenarios_answer_key WHERE parent_id = ?",
            (scenario_parent_id,),
        ).fetchone()
        if root is None:
            return None
        def pairs(table: str) -> tuple[tuple[str, str], ...]:
            return tuple((row["crew_id"], row["reason"]) for row in
                         self.connection.execute(
                             f"SELECT crew_id, reason FROM {table} "
                             "WHERE parent_id = ? ORDER BY id", (root["id"],)))
        expected = self._options("scenarios_answer_key_expected_choice", root["id"])
        expected_choice = expected[0] if expected else None
        assessment = tuple(PerFlightAssessment(*row) for row in self.connection.execute(
            "SELECT flight_id, pairing_id, min_delay_hours, crew_fdp_after_delay, "
            "fdp_limit, action FROM scenarios_answer_key_per_flight_assessment "
            "WHERE parent_id = ? ORDER BY id", (root["id"],)))
        illegal = self.connection.execute(
            "SELECT crew_id, date, rule FROM scenarios_answer_key_illegal_assignment "
            "WHERE parent_id = ?", (root["id"],)).fetchone()
        joint = self.connection.execute(
            "SELECT * FROM scenarios_answer_key_optimal_joint_plan "
            "WHERE parent_id = ?", (root["id"],)).fetchone()
        dxa = self._options("scenarios_answer_key_optimal_joint_plan_assign_dxa",
                            joint["id"])[0] if joint else None
        dxb = self._options("scenarios_answer_key_optimal_joint_plan_assign_dxb",
                            joint["id"])[0] if joint else None
        return ScenarioAnswerKey(
            root["passengers_at_risk_day1"], root["note"], root["fdp_after_delay"],
            root["fdp_limit"], bool(root["breach"]) if root["breach"] is not None else None,
            root["breach_detail"], self._values("scenarios_answer_key_affected_flights", root["id"]),
            self._values("scenarios_answer_key_uncovered_flights", root["id"]),
            self._values("scenarios_answer_key_uncovered_flights_day1", root["id"]),
            self._values("scenarios_answer_key_uncovered_flights_day2", root["id"]),
            self._options("scenarios_answer_key_options", root["id"]), expected_choice,
            pairs("scenarios_answer_key_excluded_candidates"),
            pairs("scenarios_answer_key_excluded_dxa"), pairs("scenarios_answer_key_excluded_dxb"),
            tuple(illegal) if illegal else None, assessment,
            joint["total_cost_inr"] if joint else None, dxa, dxb,
        )

    def list(self) -> list[Scenario]:
        return [scenario for row in self.connection.execute(
            "SELECT scenario_id FROM scenarios ORDER BY scenario_id"
        ) if (scenario := self.get(row["scenario_id"])) is not None]
