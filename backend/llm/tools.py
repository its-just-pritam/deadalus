"""LangChain tools that retrieve facts through the public HTTP API."""

import json
import logging
import os
import sys
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


def _api_base_url() -> str:
    return os.environ.get("CREW_OPERATIONS_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _get_json(
    tool_name: str,
    path: str,
    params: dict[str, str | None] | None = None,
) -> str:
    filtered_params = {
        key: value for key, value in (params or {}).items() if value is not None
    }
    url = f"{_api_base_url()}{path}"
    query_string = urlencode(filtered_params)
    request_url = f"{url}?{query_string}" if query_string else url
    started_at = time.perf_counter()
    logger.info(
        "[INVOKE_TOOL] tool=%s curl.exe -sS -X GET \"%s\"",
        tool_name,
        request_url,
    )
    logger.info(
        "retrieval_tool_call tool=%s method=GET path=%s params=%s",
        tool_name,
        path,
        filtered_params,
    )
    try:
        response = httpx.get(
            url,
            params=filtered_params,
            timeout=float(os.environ.get("CREW_OPERATIONS_API_TIMEOUT", "10")),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "retrieval_tool_failure tool=%s status=%s duration_ms=%.1f",
            tool_name,
            exc.response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        raise RuntimeError(
            f"Retrieval API returned {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "retrieval_tool_failure tool=%s error=%s duration_ms=%.1f",
            tool_name,
            type(exc).__name__,
            (time.perf_counter() - started_at) * 1000,
        )
        raise RuntimeError(f"Retrieval API is unavailable: {exc}") from exc
    logger.info(
        "retrieval_tool_success tool=%s status=%s duration_ms=%.1f",
        tool_name,
        response.status_code,
        (time.perf_counter() - started_at) * 1000,
    )
    return json.dumps(response.json())


class ReserveSearchInput(BaseModel):
    base: str = Field(description="Crew base, for example BLR")
    date: str | None = Field(
        default=None,
        description="UTC date in YYYY-MM-DD format; omit to retrieve all reserve dates",
    )


class CrewInput(BaseModel):
    crew_id: str = Field(description="Crew identifier, for example C-1042")


class DutyHeadroomInput(BaseModel):
    crew_id: str = Field(description="Crew identifier, for example C-1042")
    as_of: str | None = Field(
        default=None,
        description="UTC snapshot timestamp in ISO format, for example 2026-09-14T18:00:00Z",
    )


class RuleInput(BaseModel):
    rule_id: str = Field(description="Rule identifier, for example RULE-DUTY-02")


class FlightSearchInput(BaseModel):
    date: str = Field(description="UTC date in YYYY-MM-DD format")
    departure_station: str = Field(
        description="Departure station code, for example DEL"
    )
    arrival_station: str | None = Field(
        default=None,
        description="Optional arrival station code, for example BLR",
    )


class FlightDepartureInput(BaseModel):
    date: str = Field(description="UTC date in YYYY-MM-DD format")
    station: str = Field(description="Departure station code, for example DEL")


class FlightLookupInput(BaseModel):
    flight_id: str = Field(
        description="Flight number or stored flight ID, for example DX412"
    )
    date: str = Field(
        description="Operating date in YYYY-MM-DD format, for example 2026-09-15"
    )


class CertificationRangeInput(BaseModel):
    from_date: str = Field(
        description="Inclusive start date in YYYY-MM-DD format, for example 2026-09-15"
    )
    to_date: str = Field(
        description="Inclusive end date in YYYY-MM-DD format, for example 2026-10-15"
    )


class PairingInput(BaseModel):
    pairing_id: str = Field(description="Pairing identifier, for example P-2291")


class CrewSearchInput(BaseModel):
    base: str | None = None
    rank: str | None = None
    status: str | None = None
    aircraft_type: str | None = None


class FlightRouteInput(BaseModel):
    date: str
    departure_station: str
    arrival_station: str


class FlightDateInput(BaseModel):
    date: str


class AircraftPairingInput(BaseModel):
    aircraft: str = Field(description="Aircraft registration, for example VT-DXB")
    date: str | None = Field(default=None, description="Optional UTC date in YYYY-MM-DD format")


class StationInput(BaseModel):
    station: str = Field(description="Station code, for example BLR")


class UncrewedFlightsInput(BaseModel):
    crew_id: str
    pairing_id: str
    date: str


class CrewLegalityInput(BaseModel):
    crew_id: str
    pairing_id: str
    date: str


class AffectedFlightsInput(BaseModel):
    station: str
    from_utc: str
    to_utc: str


class FdpCheckInput(BaseModel):
    pairing_id: str
    crew_id: str
    date: str
    delay_hours: float = 0.0


class QualificationInput(BaseModel):
    crew_id: str
    aircraft_type: str
    date: str


class PairingLegalityInput(BaseModel):
    pairing_id: str
    crew_id: str
    date: str
    delay_hours: float = 0.0


class RestCheckInput(BaseModel):
    release_utc: str = Field(
        description="UTC release timestamp in ISO-8601 format, for example 2026-09-16T15:30:00Z"
    )
    crew_id: str | None = None


def _list_reserves(base: str, date: str | None = None) -> str:
    return _get_json("list_reserves", "/api/reserves", {"base": base, "date": date})


def _get_crew(crew_id: str) -> str:
    return _get_json("get_crew_profile", f"/api/crew/{crew_id}")


def _get_crew_ratings(crew_id: str) -> str:
    return _get_json("get_crew_ratings", f"/api/crew/{crew_id}/ratings")


def _get_on_call_window(crew_id: str) -> str:
    return _get_json(
        "get_reserve_on_call_window",
        f"/api/reserves/{crew_id}/on-call-window",
    )


def _get_reserve(crew_id: str) -> str:
    return _get_json("get_reserve", f"/api/reserves/{crew_id}")


def _get_duty_clock(crew_id: str) -> str:
    return _get_json("get_duty_clock", f"/api/crew/{crew_id}/duty-clock")


def _get_duty_history(crew_id: str) -> str:
    return _get_json("get_duty_history", f"/api/crew/{crew_id}/duty-history")


def _get_duty_headroom(crew_id: str, as_of: str | None = None) -> str:
    return _get_json(
        "get_duty_headroom",
        f"/api/duty-clocks/{crew_id}/headroom",
        {"asOf": as_of},
    )


def _get_rule(rule_id: str) -> str:
    return _get_json("get_rule", f"/api/rules/{rule_id}")


def _list_flights(
    date: str,
    departure_station: str,
    arrival_station: str | None = None,
) -> str:
    return _get_json(
        "list_flights",
        "/api/flights",
        {
            "date": date,
            "departureStation": departure_station,
            "arrivalStation": arrival_station,
        },
    )


def _list_departures(date: str, station: str) -> str:
    return _get_json(
        "list_departures",
        "/api/flights/departures",
        {"date": date, "station": station},
    )


def _get_flight(flight_id: str, date: str) -> str:
    return _get_json(
        "get_flight",
        f"/api/flights/{flight_id}",
        {"date": date},
    )


def _list_expiring_certifications(from_date: str, to_date: str) -> str:
    return _get_json(
        "list_expiring_certifications",
        "/api/certifications/expiring",
        {"from": from_date, "to": to_date},
    )


def _get_pairing(pairing_id: str) -> str:
    return _get_json("get_pairing", f"/api/pairings/{pairing_id}")


def _get_pairing_crew(pairing_id: str) -> str:
    return _get_json("get_pairing_crew", f"/api/pairings/{pairing_id}/crew")


def _search_crew(
    base: str | None = None,
    rank: str | None = None,
    status: str | None = None,
    aircraft_type: str | None = None,
) -> str:
    return _get_json(
        "search_crew",
        "/api/crew/search",
        {
            "base": base,
            "rank": rank,
            "status": status,
            "aircraftType": aircraft_type,
        },
    )


def _list_route_flights(date: str, departure_station: str, arrival_station: str) -> str:
    return _get_json(
        "list_route_flights",
        "/api/flights/routes",
        {
            "date": date,
            "departureStation": departure_station,
            "arrivalStation": arrival_station,
        },
    )


def _count_flights(date: str) -> str:
    return _get_json("count_flights", "/api/flights/count", {"date": date})


def _get_longest_block() -> str:
    return _get_json("get_longest_block", "/api/flights/longest-block")


def _list_aircraft_pairings(aircraft: str, date: str | None = None) -> str:
    return _get_json(
        "list_aircraft_pairings",
        f"/api/aircraft/{aircraft}/pairings",
        {"date": date},
    )


def _list_station_destinations(station: str) -> str:
    return _get_json(
        "list_station_destinations",
        f"/api/stations/{station}/nonstop-destinations",
    )


def _get_risk_signal(crew_id: str) -> str:
    return _get_json("get_risk_signal", f"/api/crew/{crew_id}/risk-signal")


def _get_uncrewed_flights(crew_id: str, pairing_id: str, date: str) -> str:
    return _get_json(
        "get_uncrewed_flights",
        "/api/disruptions/uncrewed-flights",
        {"crewId": crew_id, "pairingId": pairing_id, "date": date},
    )


def _check_crew_legality(crew_id: str, pairing_id: str, date: str) -> str:
    return _get_json(
        "check_crew_legality",
        f"/api/crew/{crew_id}/legality",
        {"pairingId": pairing_id, "date": date},
    )


def _get_affected_flights(station: str, from_utc: str, to_utc: str) -> str:
    return _get_json(
        "get_affected_flights",
        "/api/flights/affected",
        {"station": station, "from": from_utc, "to": to_utc},
    )


def _check_fdp(pairing_id: str, crew_id: str, date: str, delay_hours: float = 0.0) -> str:
    return _get_json(
        "check_fdp",
        f"/api/pairings/{pairing_id}/fdp-check",
        {"crewId": crew_id, "date": date, "delayHours": str(delay_hours)},
    )


def _check_qualification(crew_id: str, aircraft_type: str, date: str) -> str:
    return _get_json(
        "check_qualification",
        f"/api/crew/{crew_id}/qualification",
        {"aircraftType": aircraft_type, "date": date},
    )


def _check_pairing_legality(
    pairing_id: str, crew_id: str, date: str, delay_hours: float = 0.0
) -> str:
    return _get_json(
        "check_pairing_legality",
        f"/api/pairings/{pairing_id}/legality",
        {"crewId": crew_id, "date": date, "delayHours": str(delay_hours)},
    )


def _check_rest(release_utc: str, crew_id: str | None = None) -> str:
    return _get_json(
        "check_rest",
        "/api/rest-check",
        {"releaseUtc": release_utc, "crewId": crew_id},
    )


def get_retrieval_tools() -> list[StructuredTool]:
    """Return the only tools the operational LLM may use for retrieval."""
    return [
        StructuredTool.from_function(
            func=_list_reserves,
            name="list_reserves",
            description=(
                "Retrieve reserve crew, on-call windows, and availability dates from the "
                "operational API. The window applies to callout time, not report time; "
                "use reachability to relate callout and report."
            ),
            args_schema=ReserveSearchInput,
        ),
        StructuredTool.from_function(
            func=_get_crew,
            name="get_crew_profile",
            description=(
                "Retrieve a crew member's authoritative profile, rank, base, status, "
                "ratings, seniority, and reachability from the operational API."
            ),
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_crew_ratings,
            name="get_crew_ratings",
            description="Retrieve a crew member's authoritative aircraft ratings.",
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_on_call_window,
            name="get_reserve_on_call_window",
            description=(
                "Retrieve one reserve crew member's authoritative UTC on-call window "
                "from the operational API."
            ),
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_reserve,
            name="get_reserve",
            description=(
                "Retrieve an authoritative reserve profile including base, dates, "
                "on-call window, rank, ratings, and reachability. The on-call window "
                "constrains callout time, not report time."
            ),
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_duty_clock,
            name="get_duty_clock",
            description=(
                "Retrieve the authoritative 7-day duty hours, 28-day flight hours, "
                "last rest, and snapshot metadata for a crew member."
            ),
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_duty_history,
            name="get_duty_history",
            description=(
                "Retrieve the authoritative daily duty and flight-hour history for a "
                "crew member. Use it when a question asks for a calendar-day window."
            ),
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_duty_headroom,
            name="get_duty_headroom",
            description=(
                "Retrieve authoritative 7-day duty-hour headroom under RULE-DUTY-02 "
                "for a crew member."
            ),
            args_schema=DutyHeadroomInput,
        ),
        StructuredTool.from_function(
            func=_get_rule,
            name="get_rule",
            description="Retrieve the authoritative text and parameters for an operational rule.",
            args_schema=RuleInput,
        ),
        StructuredTool.from_function(
            func=_list_flights,
            name="list_flights",
            description=(
                "Retrieve authoritative flights filtered by UTC date and departure "
                "station, optionally including arrival station."
            ),
            args_schema=FlightSearchInput,
        ),
        StructuredTool.from_function(
            func=_list_departures,
            name="list_departures",
            description=(
                "Retrieve all authoritative flights departing a station on a UTC date."
            ),
            args_schema=FlightDepartureInput,
        ),
        StructuredTool.from_function(
            func=_get_flight,
            name="get_flight",
            description=(
                "Retrieve one authoritative flight by flight number or stored flight ID. "
                "Provide the operating date when using a flight number."
            ),
            args_schema=FlightLookupInput,
        ),
        StructuredTool.from_function(
            func=_list_expiring_certifications,
            name="list_expiring_certifications",
            description=(
                "Retrieve authoritative crew certifications whose valid_to date "
                "falls within an inclusive UTC date range."
            ),
            args_schema=CertificationRangeInput,
        ),
        StructuredTool.from_function(
            func=_get_pairing,
            name="get_pairing",
            description=(
                "Retrieve an authoritative pairing including aircraft, assigned crew "
                "roles, duty days, and flight IDs."
            ),
            args_schema=PairingInput,
        ),
        StructuredTool.from_function(
            func=_get_pairing_crew,
            name="get_pairing_crew",
            description="Retrieve the authoritative crew and roles assigned to a pairing.",
            args_schema=PairingInput,
        ),
        StructuredTool.from_function(
            func=_search_crew,
            name="search_crew",
            description=(
                "Search authoritative crew profiles by optional base, rank, status, "
                "and aircraft rating filters."
            ),
            args_schema=CrewSearchInput,
        ),
        StructuredTool.from_function(
            func=_list_route_flights,
            name="list_route_flights",
            description=(
                "Retrieve authoritative flights on a date between a departure and "
                "arrival station."
            ),
            args_schema=FlightRouteInput,
        ),
        StructuredTool.from_function(
            func=_count_flights,
            name="count_flights",
            description="Count authoritative flights operating on a UTC date.",
            args_schema=FlightDateInput,
        ),
        StructuredTool.from_function(
            func=_get_longest_block,
            name="get_longest_block",
            description="Retrieve the longest block time and all flight numbers with it.",
        ),
        StructuredTool.from_function(
            func=_list_aircraft_pairings,
            name="list_aircraft_pairings",
            description="Retrieve authoritative pairings for an aircraft, optionally on a date.",
            args_schema=AircraftPairingInput,
        ),
        StructuredTool.from_function(
            func=_list_station_destinations,
            name="list_station_destinations",
            description="Retrieve authoritative nonstop destinations from a station.",
            args_schema=StationInput,
        ),
        StructuredTool.from_function(
            func=_get_risk_signal,
            name="get_risk_signal",
            description="Retrieve the provided disruption-risk score and drivers for crew.",
            args_schema=CrewInput,
        ),
        StructuredTool.from_function(
            func=_get_uncrewed_flights,
            name="get_uncrewed_flights",
            description="Determine flights at risk when a crew member is absent from a pairing.",
            args_schema=UncrewedFlightsInput,
        ),
        StructuredTool.from_function(
            func=_check_crew_legality,
            name="check_crew_legality",
            description="Check a crew member's duty legality for a pairing from a date.",
            args_schema=CrewLegalityInput,
        ),
        StructuredTool.from_function(
            func=_get_affected_flights,
            name="get_affected_flights",
            description="Find flights departing or arriving at a station during a UTC closure window.",
            args_schema=AffectedFlightsInput,
        ),
        StructuredTool.from_function(
            func=_check_fdp,
            name="check_fdp",
            description="Check FDP after delay against RULE-FDP-01 for a pairing duty.",
            args_schema=FdpCheckInput,
        ),
        StructuredTool.from_function(
            func=_check_qualification,
            name="check_qualification",
            description="Check aircraft rating and certification validity for crew on a date.",
            args_schema=QualificationInput,
        ),
        StructuredTool.from_function(
            func=_check_pairing_legality,
            name="check_pairing_legality",
            description="Check a crew member's legality for a pairing and date.",
            args_schema=PairingLegalityInput,
        ),
        StructuredTool.from_function(
            func=_check_rest,
            name="check_rest",
            description=(
                "Calculate the earliest next report from a provided release timestamp "
                "using the authoritative RULE-REST-04 minimum rest. A pairing ID is "
                "not required when the release time is provided."
            ),
            args_schema=RestCheckInput,
        ),
    ]