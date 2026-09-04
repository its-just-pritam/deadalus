"""Operational legality, disruption, and rest query endpoints."""

from datetime import datetime, timedelta
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    AffectedFlightResponse,
    FdpCheckResponse,
    LegalityResponse,
    UncrewedFlightsResponse,
    QualificationResponse,
    PairingLegalityResponse,
    RestCheckResponse,
)
from backend.infrastructure.repositories import (
    CrewRepository,
    DutyClockRepository,
    FlightRepository,
    CertificationRepository,
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
        self.router.add_api_route(
            "/crew/{crew_id}/qualification",
            self.qualification,
            methods=["GET"],
            response_model=QualificationResponse,
        )
        self.router.add_api_route(
            "/pairings/{pairing_id}/legality",
            self.pairing_legality,
            methods=["GET"],
            response_model=PairingLegalityResponse,
        )
        self.router.add_api_route(
            "/pairings/{pairing_id}/rest-check",
            self.rest_check,
            methods=["GET"],
            response_model=RestCheckResponse,
        )
        self.router.add_api_route(
            "/rest-check",
            self.rest_check_from_release,
            methods=["GET"],
            response_model=RestCheckResponse,
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
        if rule is None or rule.parameters.max_duty_hours is None:
            raise HTTPException(status_code=500, detail="RULE-DUTY-02 is not configured")
        limit = float(rule.parameters.max_duty_hours)
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
        if (
            rule is None
            or rule.parameters.base_fdp_hours is None
            or rule.parameters.reduction_per_extra_sector_hours is None
            or rule.parameters.free_sectors is None
        ):
            raise HTTPException(status_code=500, detail="RULE-FDP-01 is not configured")
        base = float(rule.parameters.base_fdp_hours)
        reduction = float(rule.parameters.reduction_per_extra_sector_hours)
        free = int(rule.parameters.free_sectors)
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

    @staticmethod
    def qualification(
        crew_id: str,
        date: str,
        aircraft_type: str = Query(alias="aircraftType"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> QualificationResponse:
        crew = CrewRepository(connection).get(crew_id)
        if crew is None:
            raise HTTPException(status_code=404, detail="Crew not found")
        issues = []
        if aircraft_type not in crew.ratings:
            issues.append(f"RULE-QUAL-05: no {aircraft_type} rating")
        for certification in CertificationRepository(connection).list_for_crew(crew_id):
            if certification.valid_to < date and certification.cert_type in {
                "licence", "medical_class1", "recurrent_training", "dangerous_goods"
            }:
                issues.append(
                    f"RULE-CERT-06: {certification.cert_type} expired {certification.valid_to}"
                )
        return QualificationResponse(
            crew_id=crew_id,
            aircraft_type=aircraft_type,
            date=date,
            qualified=not issues,
            ratings=list(crew.ratings),
            certification_issues=issues,
        )

    @classmethod
    def pairing_legality(
        cls,
        pairing_id: str,
        date: str,
        crew_id: str = Query(alias="crewId"),
        delay_hours: float = Query(default=0.0, alias="delayHours"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> PairingLegalityResponse:
        result = cls.crew_legality(crew_id, date, pairing_id, connection)
        pairing = cls._pairing(pairing_id, connection)
        issues = list(result.issues)
        consequence = None
        crew = CrewRepository(connection).get(crew_id)
        day = next((item for item in pairing.days if item.date == date), None)
        if crew is None:
            raise HTTPException(status_code=404, detail="Crew not found")
        if day is None:
            raise HTTPException(status_code=404, detail="Pairing date not found")
        first_flight = FlightRepository(connection).get(day.flight_ids[0])
        if first_flight is None:
            raise HTTPException(status_code=500, detail="Pairing flight not found")
        if crew.base != first_flight.dep_station:
            positioning = FlightRepository(connection).list(
                date=date,
                departure_station=crew.base,
                arrival_station=first_flight.dep_station,
            )
            if positioning:
                arrival = datetime.fromisoformat(
                    positioning[0].arr_utc.replace("Z", "+00:00")
                )
                report = datetime.fromisoformat(
                    day.report_utc.replace("Z", "+00:00")
                )
                delay_hours = max(0.0, (arrival + timedelta(minutes=15) - report).total_seconds() / 3600)
                consequence = (
                    f"Deadhead positioning on {positioning[0].flight_no} (arrives "
                    f"{positioning[0].arr_utc[11:16]}Z) delays the first departure by "
                    f"approximately {delay_hours:.1f} hours; RULE-BASE-07 deadhead cost applies."
                )
        return PairingLegalityResponse(
            crew_id=crew_id,
            pairing_id=pairing_id,
            date=date,
            legal=not issues,
            issues=issues,
            consequence=consequence,
        )

    @staticmethod
    def rest_check(
        pairing_id: str,
        date: str,
        crew_id: str | None = Query(default=None, alias="crewId"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> RestCheckResponse:
        pairing = PairingRepository(connection).get(pairing_id)
        if pairing is None:
            raise HTTPException(status_code=404, detail="Pairing not found")
        day = next((item for item in pairing.days if item.date == date), None)
        if day is None:
            raise HTTPException(status_code=404, detail="Pairing date not found")
        release = datetime.fromisoformat(day.release_utc.replace("Z", "+00:00"))
        rule = RulesetRepository(connection).get_rule("RULE-REST-04")
        if rule is None or rule.parameters.min_rest_hours is None:
            raise HTTPException(status_code=500, detail="RULE-REST-04 is not configured")
        minimum_rest = float(rule.parameters.min_rest_hours)
        earliest = release + timedelta(hours=minimum_rest)
        return RestCheckResponse(
            crew_id=crew_id,
            release_utc=day.release_utc,
            minimum_rest_hours=minimum_rest,
            earliest_next_report_utc=earliest.isoformat().replace("+00:00", "Z"),
            legal=True,
        )

    @staticmethod
    def rest_check_from_release(
        release_utc: str = Query(alias="releaseUtc"),
        crew_id: str | None = Query(default=None, alias="crewId"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> RestCheckResponse:
        try:
            release = datetime.fromisoformat(release_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="releaseUtc must be an ISO-8601 UTC timestamp",
            ) from exc
        rule = RulesetRepository(connection).get_rule("RULE-REST-04")
        minimum_rest = float(rule.parameters.min_rest_hours) if rule else 12.0
        earliest = release + timedelta(hours=minimum_rest)
        return RestCheckResponse(
            crew_id=crew_id,
            release_utc=release_utc,
            minimum_rest_hours=minimum_rest,
            earliest_next_report_utc=earliest.isoformat().replace("+00:00", "Z"),
            legal=True,
        )