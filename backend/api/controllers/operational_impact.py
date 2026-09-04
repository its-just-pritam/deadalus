"""Operational impact and recovery query endpoints."""

from datetime import datetime, timedelta
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    AtRiskCrewResponse,
    CancellationImpactResponse,
    DownstreamRestResponse,
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