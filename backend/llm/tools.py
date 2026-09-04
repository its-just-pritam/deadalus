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


class CertificationRangeInput(BaseModel):
    from_date: str = Field(
        description="Inclusive start date in YYYY-MM-DD format, for example 2026-09-15"
    )
    to_date: str = Field(
        description="Inclusive end date in YYYY-MM-DD format, for example 2026-10-15"
    )


def _list_reserves(base: str, date: str | None = None) -> str:
    return _get_json("list_reserves", "/api/reserves", {"base": base, "date": date})


def _get_crew(crew_id: str) -> str:
    return _get_json("get_crew_profile", f"/api/crew/{crew_id}")


def _get_on_call_window(crew_id: str) -> str:
    return _get_json(
        "get_reserve_on_call_window",
        f"/api/reserves/{crew_id}/on-call-window",
    )


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


def _list_expiring_certifications(from_date: str, to_date: str) -> str:
    return _get_json(
        "list_expiring_certifications",
        "/api/certifications/expiring",
        {"from": from_date, "to": to_date},
    )


def get_retrieval_tools() -> list[StructuredTool]:
    """Return the only tools the operational LLM may use for retrieval."""
    return [
        StructuredTool.from_function(
            func=_list_reserves,
            name="list_reserves",
            description=(
                "Retrieve reserve crew and their on-call windows from the operational API. "
                "Use this before answering reserve availability questions."
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
            func=_get_on_call_window,
            name="get_reserve_on_call_window",
            description=(
                "Retrieve one reserve crew member's authoritative UTC on-call window "
                "from the operational API."
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
            func=_list_expiring_certifications,
            name="list_expiring_certifications",
            description=(
                "Retrieve authoritative crew certifications whose valid_to date "
                "falls within an inclusive UTC date range."
            ),
            args_schema=CertificationRangeInput,
        ),
    ]