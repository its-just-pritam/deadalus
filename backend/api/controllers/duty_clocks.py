"""Duty-clock retrieval controller."""

from datetime import date, datetime
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    DutyClockResponse,
    DutyHeadroomResponse,
    DutyHistoryResponse,
)
from backend.domain.entities import DutyClock
from backend.infrastructure.repositories import DutyClockRepository, RulesetRepository


def _clock_response(clock: DutyClock) -> DutyClockResponse:
    return DutyClockResponse(
        crew_id=clock.crew_id,
        as_of_utc=clock.as_of_utc,
        duty_hours_7d=clock.duty_hours_7d,
        flight_hours_28d=clock.flight_hours_28d,
        last_rest_ended=clock.last_rest_ended,
        daily_history=[
            DutyHistoryResponse(
                date=item.date,
                duty_hours=item.duty_hours,
                flight_hours=item.flight_hours,
            )
            for item in clock.daily_history
        ],
    )


class DutyClockController:
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["duty-clocks"])
        self.router.add_api_route(
            "/crew/{crew_id}/duty-clock",
            self.get_clock,
            methods=["GET"],
            response_model=DutyClockResponse,
        )
        self.router.add_api_route(
            "/crew/{crew_id}/duty-history",
            self.get_history,
            methods=["GET"],
            response_model=list[DutyHistoryResponse],
        )
        self.router.add_api_route(
            "/duty-clocks/{crew_id}/headroom",
            self.get_headroom,
            methods=["GET"],
            response_model=DutyHeadroomResponse,
        )

    @staticmethod
    def _get_clock(crew_id: str, connection: sqlite3.Connection) -> DutyClock:
        clock = DutyClockRepository(connection).get(crew_id)
        if clock is None:
            raise HTTPException(status_code=404, detail="Duty clock not found")
        return clock

    @classmethod
    def get_clock(
        cls,
        crew_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> DutyClockResponse:
        return _clock_response(cls._get_clock(crew_id, connection))

    @classmethod
    def get_history(
        cls,
        crew_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[DutyHistoryResponse]:
        return _clock_response(cls._get_clock(crew_id, connection)).daily_history

    @classmethod
    def get_headroom(
        cls,
        crew_id: str,
        as_of: str | None = Query(default=None, alias="asOf"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> DutyHeadroomResponse:
        clock = cls._get_clock(crew_id, connection)
        if as_of is not None:
            try:
                requested_date = (
                    datetime.fromisoformat(as_of.replace("Z", "+00:00")).date()
                    if "T" in as_of
                    else date.fromisoformat(as_of)
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="asOf must be an ISO date or UTC timestamp",
                ) from exc

            snapshot_date = date.fromisoformat(clock.as_of_utc.split("T", 1)[0])
            if requested_date != snapshot_date:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Only snapshot date {snapshot_date.isoformat()} is available "
                        f"for crew {crew_id}"
                    ),
                )
        rule = RulesetRepository(connection).get_rule("RULE-DUTY-02")
        if rule is None or rule.parameters.max_duty_hours is None:
            raise HTTPException(status_code=500, detail="RULE-DUTY-02 is not configured")
        limit = float(rule.parameters.max_duty_hours)
        return DutyHeadroomResponse(
            crew_id=crew_id,
            as_of_utc=clock.as_of_utc,
            duty_hours_7d=clock.duty_hours_7d,
            max_duty_hours_7d=limit,
            headroom_hours=round(limit - clock.duty_hours_7d, 2),
            rule_id="RULE-DUTY-02",
        )