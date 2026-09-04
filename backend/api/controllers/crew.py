"""Crew resource controller."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_connection
from backend.api.schemas import CrewResponse
from backend.infrastructure.repositories import CrewRepository


class CrewController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/crew", tags=["crew"])
        self.router.add_api_route(
            "/{crew_id}/ratings",
            self.get_ratings,
            methods=["GET"],
            response_model=list[str],
        )
        self.router.add_api_route(
            "/{crew_id}",
            self.get,
            methods=["GET"],
            response_model=CrewResponse,
        )

    @staticmethod
    def get_ratings(
        crew_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[str]:
        crew = CrewRepository(connection).get(crew_id)
        if crew is None:
            raise HTTPException(status_code=404, detail="Crew not found")
        return list(crew.ratings)

    @staticmethod
    def get(crew_id: str, connection: sqlite3.Connection = Depends(get_connection)):
        crew = CrewRepository(connection).get(crew_id)
        if crew is None:
            raise HTTPException(status_code=404, detail="Crew not found")
        return CrewResponse(
            crew_id=crew.crew_id,
            name=crew.name,
            rank=crew.rank,
            base=crew.base,
            seniority=crew.seniority,
            reachability_minutes=crew.reachability_minutes,
            status=crew.status,
            ratings=list(crew.ratings),
        )
