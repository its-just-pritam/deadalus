"""Operational query endpoints for Q17-Q20."""

from datetime import datetime, timedelta
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    AffectedFlightResponse,
    FdpCheckResponse,
    LegalityResponse,
    UncrewedFlightsResponse,
)
from backend.infrastructure.repositories import (
    CrewRepository,
    DutyClockRepository,
    FlightRepository,
    PairingRepository,
    RulesetRepository,
)


def _duty_hours_for_date(clock, target_date: str) -> float:
    return sum(
        item.duty_hours for item in clock.daily_history if item.date == target_date
    )


class OperationalController:
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["operational"])
        self.router.add_api_route(
            "/disruptions/uncrewed-flights",
            self.uncrewed_flights,
            methods=["GET"],
            response_model=UncrewedFlightsResponse,
        )
        self.router.add_api_route(
            "/crew/{crew_id}/legality",
            self.crew_legality,
            methods=["GET"],
            response_model=LegalityResponse,
        )
        self.router.add_api_route(
            "/flights/affected",
            self.affected_flights,
            methods=["GET"],
            response_model=list[AffectedFlightResponse],
        )
        self.router.add_api_route(
            "/pairings/{pairing_id}/fdp-check",
            self.fdp_check,
            methods=["GET"],
            response_model=FdpCheckResponse,
        )

    @staticmethod
    def _pairing(pairing_id: str, connection: sqlite3.Connection):
        pairing = PairingRepository(connection).get(pairing_id)
        if pairing is None:
            raise HTTPException(status_code=404, detail="Pairing not found")
        return pairing

    @classmethod
    def uncrewed_flights(
        cls,
        date: str,
        crew_id: str = Query(alias="crewId"),
        pairing_id: str = Query(alias="pairingId"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> UncrewedFlightsResponse:
        pairing = cls._pairing(pairing_id, connection)
        if not any(member.crew_id == crew_id for member in pairing.crew):
            raise HTTPException(status_code=404, detail="Crew is not assigned to pairing")
        days = [day for day in pairing.days if day.date >= date]
        if not days:
            raise HTTPException(status_code=404, detail="Pairing date not found")
        flight_repo = FlightRepository(connection)
        day1 = list(days[0].flight_ids)
        day2 = list(days[1].flight_ids) if len(days) > 1 else []
        passengers = sum(
            flight_repo.get(flight_id).seats
            for flight_id in day1
            if flight_repo.get(flight_id) is not None
        )
        return UncrewedFlightsResponse(
            crew_id=crew_id,
            pairing_id=pairing_id,
            day1=day1,
            day2_also_at_risk=day2,
            passengers_day1=passengers,
        )

    @classmethod
    def crew_legality(
        cls,
        crew_id: str,
        date: str,
        pairing_id: str = Query(alias="pairingId"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> LegalityResponse:
        pairing = cls._pairing(pairing_id, connection)
        clock = DutyClockRepository(connection).get(crew_id)
        if clock is None:
            raise HTTPException(status_code=404, detail="Duty clock not found")
        rule = RulesetRepository(connection).get_rule("RULE-DUTY-02")
        limit = float(rule.parameters.max_duty_hours) if rule else 60.0
        start = datetime.fromisoformat(date).date()
        issues = []
        cumulative_new = 0.0
        for day in pairing.days:
            if day.date < date:
                continue
            report = datetime.fromisoformat(day.report_utc.replace("Z", "+00:00"))
            release = datetime.fromisoformat(day.release_utc.replace("Z", "+00:00"))
            duty_hours = (release - report).total_seconds() / 3600
            cumulative_new += duty_hours
            day_date = datetime.fromisoformat(day.date).date()
            window_start = day_date - timedelta(days=6)
            historical = sum(
                item.duty_hours
                for item in clock.daily_history
                if window_start.isoformat() <= item.date < date
            )
            total = round(historical + cumulative_new, 2)
            if total > limit:
                excess = total - limit
                hours = int(excess)
                minutes = round((excess - hours) * 60)
                issues.append(
                    f"RULE-DUTY-02: would exceed 60h/7d by {hours}h{minutes:02d}m "
                    f"on {day.date} (total {total:.2f}h)"
                )
        return LegalityResponse(
            crew_id=crew_id,
            pairing_id=pairing_id,
            legal=not issues,
            issues=issues,
        )

    @staticmethod
    def affected_flights(
        station: str,
        from_utc: str = Query(alias="from"),
        to_utc: str = Query(alias="to"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[AffectedFlightResponse]:
        flights = FlightRepository(connection).affected_by_station_window(
            station=station, from_utc=from_utc, to_utc=to_utc
        )
        return [
            AffectedFlightResponse(
                flight_id=flight.flight_id,
                flight_no=flight.flight_no,
                date=flight.date,
                dep_station=flight.dep_station,
                arr_station=flight.arr_station,
                dep_utc=flight.dep_utc,
                arr_utc=flight.arr_utc,
            )
            for flight in flights
        ]

    @classmethod
    def fdp_check(
        cls,
        pairing_id: str,
        date: str,
        crew_id: str = Query(alias="crewId"),
        delay_hours: float = Query(default=0.0, alias="delayHours"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> FdpCheckResponse:
        pairing = cls._pairing(pairing_id, connection)
        day = next((item for item in pairing.days if item.date == date), None)
        if day is None:
            raise HTTPException(status_code=404, detail="Pairing date not found")
        sectors = len(day.flight_ids)
        report = datetime.fromisoformat(day.report_utc.replace("Z", "+00:00"))
        release = datetime.fromisoformat(day.release_utc.replace("Z", "+00:00"))
        fdp = (release - report).total_seconds() / 3600 + delay_hours
        rule = RulesetRepository(connection).get_rule("RULE-FDP-01")
        base = float(rule.parameters.base_fdp_hours) if rule else 13.0
        reduction = float(rule.parameters.reduction_per_extra_sector_hours) if rule else 0.5
        free = int(rule.parameters.free_sectors) if rule else 2
        limit = base - max(0, sectors - free) * reduction
        return FdpCheckResponse(
            aircraft=pairing.aircraft,
            date=date,
            delay_hours=delay_hours,
            sectors=sectors,
            fdp_after_delay=round(fdp, 2),
            fdp_limit=round(limit, 2),
            breach=fdp > limit,
        )