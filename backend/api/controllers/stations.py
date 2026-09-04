"""Station network retrieval controller."""

import sqlite3

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_connection
from backend.api.schemas import StationDestinationsResponse
from backend.infrastructure.repositories import FlightRepository


class StationController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/stations", tags=["stations"])
        self.router.add_api_route(
            "/{station}/nonstop-destinations",
            self.nonstop_destinations,
            methods=["GET"],
            response_model=StationDestinationsResponse,
        )

    @staticmethod
    def nonstop_destinations(
        station: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> StationDestinationsResponse:
        destinations = FlightRepository(connection).nonstop_destinations(
            departure_station=station
        )
        return StationDestinationsResponse(station=station, destinations=destinations)