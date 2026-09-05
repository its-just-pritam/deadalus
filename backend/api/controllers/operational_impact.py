"""Operational impact and recovery query endpoints."""

from datetime import datetime, timedelta
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    AtRiskCrewResponse,
    CancellationImpactResponse,
    DownstreamRestResponse,
    SeatRiskResponse,
    RankedRecoveryResponse,
    RecoveryOptionResponse,
    JointPlanResponse,
    ReserveEligibilityResponse,
)
from backend.infrastructure.repositories import (
    CertificationRepository,
    CostConfigRepository,
    CrewRepository,
    DutyClockRepository,
    FlightRepository,
    PairingRepository,
    ReserveRepository,
)
from backend.api.controllers.operational import OperationalController


class OperationalImpactController:
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["operational"])
        self.router.add_api_route(
            "/flights/{flight_id}/cancellation-impact",
            self.cancellation_impact,
            methods=["GET"],
            response_model=CancellationImpactResponse,
        )
        self.router.add_api_route(
            "/duty-clocks/at-risk",
            self.at_risk,
            methods=["GET"],
            response_model=list[AtRiskCrewResponse],
        )
        self.router.add_api_route(
            "/reserves/available",
            self.available_reserves,
            methods=["GET"],
            response_model=ReserveEligibilityResponse,
        )
        self.router.add_api_route(
            "/crew/{crew_id}/downstream-rest-check",
            self.downstream_rest,
            methods=["GET"],
            response_model=DownstreamRestResponse,
        )
        self.router.add_api_route(
            "/flights/most-seats",
            self.most_seats,
            methods=["GET"],
            response_model=SeatRiskResponse,
        )
        self.router.add_api_route(
            "/recovery/ranked-options",
            self.ranked_options,
            methods=["GET"],
            response_model=RankedRecoveryResponse,
        )
        self.router.add_api_route(
            "/recovery/joint-plan",
            self.joint_plan,
            methods=["GET"],
            response_model=JointPlanResponse,
        )

    @staticmethod
    def cancellation_impact(
        flight_id: str,
        date: str | None = Query(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> CancellationImpactResponse:
        repository = FlightRepository(connection)
        flight = repository.get(flight_id)
        if flight is None:
            flight = repository.get_by_number(flight_id, date=date)
        elif date is not None and flight.date != date:
            flight = None
        if flight is None:
            raise HTTPException(status_code=404, detail="Flight not found")
        costs = CostConfigRepository(connection).get()
        if costs is None:
            raise HTTPException(status_code=500, detail="Cost configuration not found")
        return CancellationImpactResponse(
            flight_id=flight.flight_id,
            passengers=flight.seats,
            cancellation_cost_inr=costs.cancellation_per_flight,
        )

    @staticmethod
    def at_risk(
        date: str,
        minimum_duty_hours: float = Query(alias="minimumDutyHours"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[AtRiskCrewResponse]:
        target = datetime.fromisoformat(date).date()
        start = target - timedelta(days=6)
        results = []
        crew_repository = CrewRepository(connection)
        pairing_repository = PairingRepository(connection)
        for crew in crew_repository.list():
            clock = DutyClockRepository(connection).get(crew.crew_id)
            if clock is None:
                continue
            total = sum(
                item.duty_hours
                for item in clock.daily_history
                if start.isoformat() <= item.date <= date
            )
            planned = 0.0
            for pairing in pairing_repository.list_by_date(date):
                if any(member.crew_id == crew.crew_id for member in pairing.crew):
                    day = next(item for item in pairing.days if item.date == date)
                    report = datetime.fromisoformat(day.report_utc.replace("Z", "+00:00"))
                    release = datetime.fromisoformat(day.release_utc.replace("Z", "+00:00"))
                    planned += (release - report).total_seconds() / 3600
            total = round(total + planned, 2)
            if total >= minimum_duty_hours:
                results.append(
                    AtRiskCrewResponse(
                        crew_id=crew.crew_id,
                        duty_hours_7d_including_plan=total,
                    )
                )
        return results

    @staticmethod
    def available_reserves(
        date: str,
        base: str,
        rank: str,
        report_time: str = Query(alias="reportTime"),
        aircraft_type: str | None = Query(default=None, alias="aircraftType"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> ReserveEligibilityResponse:
        eligible = []
        excluded: dict[str, str] = {}
        reserves = ReserveRepository(connection).list(date=date, base=base)
        for reserve in reserves:
            crew = CrewRepository(connection).get(reserve.crew_id)
            if crew is None or crew.rank != rank:
                continue
            if reserve.oncall_window_utc is None:
                excluded[reserve.crew_id] = "No on-call window"
                continue
            if not (
                reserve.oncall_window_utc.start <= report_time <= reserve.oncall_window_utc.end
            ):
                excluded[reserve.crew_id] = (
                    f"On-call window {reserve.oncall_window_utc.start}-"
                    f"{reserve.oncall_window_utc.end} does not cover {report_time}"
                )
                continue
            if aircraft_type and aircraft_type not in crew.ratings:
                excluded[reserve.crew_id] = f"RULE-QUAL-05: no {aircraft_type} rating"
                continue
            eligible.append(reserve.crew_id)
        return ReserveEligibilityResponse(eligible=eligible, excluded=excluded)

    @staticmethod
    def downstream_rest(
        crew_id: str,
        date: str,
        pairing_id: str = Query(alias="pairingId"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> DownstreamRestResponse:
        proposed = PairingRepository(connection).get(pairing_id)
        if proposed is None:
            raise HTTPException(status_code=404, detail="Pairing not found")
        crew_pairings = [
            pairing for pairing in PairingRepository(connection).list()
            if any(member.crew_id == crew_id for member in pairing.crew)
        ]
        issues = []
        proposed_last = max(
            (day.release_utc for day in proposed.days if day.date >= date),
            default=None,
        )
        if proposed_last:
            proposed_release = datetime.fromisoformat(proposed_last.replace("Z", "+00:00"))
            for existing in crew_pairings:
                for day in existing.days:
                    if day.date <= date:
                        continue
                    report = datetime.fromisoformat(day.report_utc.replace("Z", "+00:00"))
                    rest = (report - proposed_release).total_seconds() / 3600
                    if rest < 12:
                        issues.append(
                            f"RULE-REST-04: only {rest:.2f}h rest before "
                            f"{existing.pairing_id} on {day.date}"
                        )
        return DownstreamRestResponse(
            crew_id=crew_id,
            pairing_id=pairing_id,
            legal=not issues,
            issues=issues,
        )

    @staticmethod
    def most_seats(
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> SeatRiskResponse:
        row = connection.execute("SELECT MAX(seats) AS seats FROM flights").fetchone()
        seats = int(row["seats"])
        rows = connection.execute(
            "SELECT DISTINCT aircraft_type FROM flights WHERE seats = ? ORDER BY aircraft_type",
            (seats,),
        )
        flights = connection.execute(
            "SELECT flight_no FROM flights WHERE seats = ? GROUP BY flight_no ORDER BY flight_no",
            (seats,),
        )
        return SeatRiskResponse(
            seats=seats,
            aircraft_types=[item["aircraft_type"] for item in rows],
            flights=[item["flight_no"] for item in flights],
        )

    @staticmethod
    def ranked_options(
        pairing_id: str = Query(alias="pairingId"),
        from_date: str = Query(alias="from"),
        to_date: str = Query(alias="to"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> RankedRecoveryResponse:
        pairing = PairingRepository(connection).get(pairing_id)
        if pairing is None:
            raise HTTPException(status_code=404, detail="Pairing not found")
        costs = CostConfigRepository(connection).get()
        if costs is None:
            raise HTTPException(status_code=500, detail="Cost configuration not found")
        role = next((member.role for member in pairing.crew if member.role in {"Captain", "First Officer"}), "Captain")
        first_day = next(day for day in pairing.days if day.date >= from_date)
        first_flight = FlightRepository(connection).get(first_day.flight_ids[0])
        if first_flight is None:
            raise HTTPException(status_code=500, detail="Pairing flight not found")
        required_report = first_day.report_utc[11:16]
        reserve_ids = {
            reserve.crew_id
            for reserve in ReserveRepository(connection).list(
                date=first_day.date, base=first_flight.dep_station
            )
        }
        options = []
        pairing_aircraft_type = first_flight.aircraft_type
        for crew in CrewRepository(connection).list(
            status="active", rank=role, aircraft_type=first_flight.aircraft_type
        ):
            if crew.crew_id in {member.crew_id for member in pairing.crew}:
                continue
            reserve = ReserveRepository(connection).get(crew.crew_id)
            is_reserve = crew.crew_id in reserve_ids and reserve is not None
            if is_reserve and (
                reserve.oncall_window_utc is None
                or not (reserve.oncall_window_utc.start <= required_report <= reserve.oncall_window_utc.end)
            ):
                continue
            legal = all(
                OperationalController.crew_legality(
                    crew.crew_id, day.date, pairing_id, connection
                ).legal
                for day in pairing.days
            )
            if not legal:
                continue
            qualified = all(
                OperationalController.qualification(
                    crew.crew_id,
                    day.date,
                    pairing_aircraft_type,
                    connection,
                ).qualified
                for day in pairing.days
            )
            if not qualified:
                continue
            downstream = OperationalImpactController.downstream_rest(
                crew.crew_id,
                first_day.date,
                pairing_id,
                connection,
            )
            if not downstream.legal:
                continue
            positioning = []
            if crew.base != first_flight.dep_station:
                positioning = FlightRepository(connection).list(
                    date=first_day.date,
                    departure_station=crew.base,
                    arrival_station=first_flight.dep_station,
                )
                if not positioning:
                    continue
            delay_hours = 0.0
            deadhead_cost = 0
            if positioning:
                arrival = datetime.fromisoformat(positioning[0].arr_utc.replace("Z", "+00:00"))
                report = datetime.fromisoformat(first_day.report_utc.replace("Z", "+00:00"))
                delay_hours = max(
                    0.0,
                    (arrival + timedelta(minutes=15) - report).total_seconds() / 3600,
                )
                deadhead_cost = costs.deadhead_positioning
            callout_cost = (
                costs.reserve_callout_pilot if is_reserve
                else costs.dayoff_callout_pilot
            )
            total_cost = round(callout_cost + deadhead_cost + delay_hours * costs.delay_cost_per_duty_hour)
            label = "reserve callout" if is_reserve else "day-off callout"
            if positioning:
                label += f" + deadhead from {crew.base}"
            options.append(RecoveryOptionResponse(
                action=f"Assign {role} {crew.crew_id} ({label})",
                crew_id=crew.crew_id,
                legal=True,
                cost_inr=total_cost,
                delay_hours=round(delay_hours, 2),
                rank=None,
                reasoning="Qualification, certification, duty, rest, base, and reserve-window checks passed.",
            ))
        cancellation_cost = len(
            [flight_id for day in pairing.days for flight_id in day.flight_ids]
        ) * costs.cancellation_per_flight
        options.append(RecoveryOptionResponse(
            action=f"Cancel all {sum(len(day.flight_ids) for day in pairing.days)} flights of the pairing",
            crew_id=None,
            legal=True,
            cost_inr=cancellation_cost,
            delay_hours=0.0,
            rank=None,
            reasoning="Cancellation is the fallback when no crew candidate is selected.",
        ))
        options.sort(key=lambda option: option.cost_inr or 10**9)
        options = [option.model_copy(update={"rank": index}) for index, option in enumerate(options, 1)]
        return RankedRecoveryResponse(pairing_id=pairing_id, options=options)

    @staticmethod
    def joint_plan(
        aircrafts: str,
        date: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> JointPlanResponse:
        assignments = {}
        used_crew: set[str] = set()
        costs = CostConfigRepository(connection).get()
        if costs is None:
            raise HTTPException(status_code=500, detail="Cost configuration not found")
        total = 0
        for aircraft in [item.strip() for item in aircrafts.split(",") if item.strip()]:
            pairings = PairingRepository(connection).list_by_aircraft(aircraft, date=date)
            if not pairings:
                continue
            result = OperationalImpactController.ranked_options(
                pairings[0].pairing_id, date, date, connection
            )
            if result.options:
                option = next(
                    (item for item in result.options if item.crew_id not in used_crew),
                    None,
                )
                if option is None:
                    pairing = pairings[0]
                    first_day = next(day for day in pairing.days if day.date == date)
                    first_flight = FlightRepository(connection).get(first_day.flight_ids[0])
                    role = next(
                        (member.role for member in pairing.crew
                         if member.role in {"Captain", "First Officer"}),
                        "Captain",
                    )
                    for crew in CrewRepository(connection).list(
                        base=first_flight.dep_station,
                        rank=role,
                        status="active",
                        aircraft_type=first_flight.aircraft_type,
                    ):
                        if crew.crew_id in used_crew or crew.crew_id in {
                            item.crew_id for item in result.options
                        }:
                            continue
                        legality = OperationalController.crew_legality(
                            crew.crew_id, date, pairing.pairing_id, connection
                        )
                        if legality.legal:
                            option = RecoveryOptionResponse(
                                action=f"Assign {role} {crew.crew_id} (day-off callout)",
                                crew_id=crew.crew_id,
                                legal=True,
                                cost_inr=costs.dayoff_callout_pilot,
                                delay_hours=0.0,
                                rank=None,
                                reasoning="Active qualified crew member passed duty, rest, and certification checks.",
                            )
                            break
                if option is not None:
                    assignments[aircraft] = option
                    used_crew.add(option.crew_id)
                    total += option.cost_inr or 0
        return JointPlanResponse(date=date, total_cost_inr=total, assignments=assignments)