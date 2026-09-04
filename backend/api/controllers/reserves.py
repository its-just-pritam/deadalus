"""Reserve resource controller."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    OnCallWindowResponse,
    ReserveDetailResponse,
    ReserveResponse,
)
from backend.infrastructure.repositories import CrewRepository, ReserveRepository


class ReserveController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/reserves", tags=["reserves"])
        self.router.add_api_route(
            "",
            self.list_reserves,
            methods=["GET"],
            response_model=list[ReserveResponse],
        )
        self.router.add_api_route(
            "/{crew_id}/on-call-window",
            self.get_on_call_window,
            methods=["GET"],
            response_model=OnCallWindowResponse,
        )
        self.router.add_api_route(
            "/{crew_id}",
            self.get_reserve,
            methods=["GET"],
            response_model=ReserveDetailResponse,
        )

    @staticmethod
    def list_reserves(
        date: str | None = Query(default=None),
        base: str = Query(min_length=1),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[ReserveResponse]:
        reserves = ReserveRepository(connection).list(date=date, base=base)
        crew_repository = CrewRepository(connection)
        response = []
        for reserve in reserves:
            crew = crew_repository.get(reserve.crew_id)
            if crew is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Crew record missing for reserve {reserve.crew_id}",
                )
            response.append(
                ReserveResponse(
                    crew_id=reserve.crew_id,
                    rank=crew.rank,
                    base=reserve.base,
                    note=reserve.note,
                    dates=list(reserve.dates),
                    oncall_window_utc=(
                        OnCallWindowResponse(
                            start=reserve.oncall_window_utc.start,
                            end=reserve.oncall_window_utc.end,
                        )
                        if reserve.oncall_window_utc
                        else None
                    ),
                )
            )
        return response

    @staticmethod
    def get_on_call_window(
        crew_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ):
        reserve = ReserveRepository(connection).get(crew_id)
        if reserve is None or reserve.oncall_window_utc is None:
            raise HTTPException(status_code=404, detail="On-call window not found")
        return reserve.oncall_window_utc

    @staticmethod
    def get_reserve(
        crew_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> ReserveDetailResponse:
        reserve = ReserveRepository(connection).get(crew_id)
        if reserve is None:
            raise HTTPException(status_code=404, detail="Reserve not found")
        crew = CrewRepository(connection).get(crew_id)
        if crew is None:
            raise HTTPException(
                status_code=500,
                detail=f"Crew record missing for reserve {crew_id}",
            )
        return ReserveDetailResponse(
            crew_id=reserve.crew_id,
            name=crew.name,
            rank=crew.rank,
            base=reserve.base,
            note=reserve.note,
            dates=list(reserve.dates),
            oncall_window_utc=(
                OnCallWindowResponse(
                    start=reserve.oncall_window_utc.start,
                    end=reserve.oncall_window_utc.end,
                )
                if reserve.oncall_window_utc
                else None
            ),
            seniority=crew.seniority,
            reachability_minutes=crew.reachability_minutes,
            status=crew.status,
            ratings=list(crew.ratings),
        )
