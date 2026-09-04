"""Flight retrieval controller."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import FlightCountResponse, FlightResponse, LongestBlockResponse
from backend.infrastructure.repositories import FlightRepository


def _flight_response(flight) -> FlightResponse:
    return FlightResponse(
        flight_id=flight.flight_id,
        flight_no=flight.flight_no,
        date=flight.date,
        dep_station=flight.dep_station,
        arr_station=flight.arr_station,
        dep_utc=flight.dep_utc,
        arr_utc=flight.arr_utc,
        block_hours=flight.block_hours,
        aircraft=flight.aircraft,
        aircraft_type=flight.aircraft_type,
        seats=flight.seats,
    )


class FlightController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/flights", tags=["flights"])
        self.router.add_api_route(
            "",
            self.list_flights,
            methods=["GET"],
            response_model=list[FlightResponse],
        )
        self.router.add_api_route(
            "/departures",
            self.list_departures,
            methods=["GET"],
            response_model=list[FlightResponse],
        )
        self.router.add_api_route(
            "/routes",
            self.list_routes,
            methods=["GET"],
            response_model=list[FlightResponse],
        )
        self.router.add_api_route(
            "/count",
            self.count_flights,
            methods=["GET"],
            response_model=FlightCountResponse,
        )
        self.router.add_api_route(
            "/longest-block",
            self.longest_block,
            methods=["GET"],
            response_model=LongestBlockResponse,
        )
        self.router.add_api_route(
            "/{flight_id}",
            self.get_flight,
            methods=["GET"],
            response_model=FlightResponse,
        )

    @staticmethod
    def get_flight(
        flight_id: str,
        date: str | None = Query(default=None),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> FlightResponse:
        repository = FlightRepository(connection)
        flight = repository.get(flight_id)
        if flight is None:
            flight = repository.get_by_number(flight_id, date=date)
        elif date is not None and flight.date != date:
            flight = None
        if flight is None:
            raise HTTPException(status_code=404, detail="Flight not found")
        return _flight_response(flight)

    @staticmethod
    def list_flights(
        date: str | None = Query(default=None),
        departure_station: str | None = Query(default=None, alias="departureStation"),
        arrival_station: str | None = Query(default=None, alias="arrivalStation"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[FlightResponse]:
        flights = FlightRepository(connection).list(
            date=date,
            departure_station=departure_station,
            arrival_station=arrival_station,
        )
        return [_flight_response(flight) for flight in flights]

    @staticmethod
    def list_departures(
        date: str = Query(min_length=1),
        station: str = Query(min_length=1),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[FlightResponse]:
        flights = FlightRepository(connection).list(
            date=date,
            departure_station=station,
        )
        return [_flight_response(flight) for flight in flights]

    @staticmethod
    def list_routes(
        date: str = Query(min_length=1),
        departure_station: str = Query(min_length=1, alias="departureStation"),
        arrival_station: str = Query(min_length=1, alias="arrivalStation"),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[FlightResponse]:
        flights = FlightRepository(connection).list(
            date=date,
            departure_station=departure_station,
            arrival_station=arrival_station,
        )
        return [_flight_response(flight) for flight in flights]

    @staticmethod
    def count_flights(
        date: str = Query(min_length=1),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> FlightCountResponse:
        return FlightCountResponse(
            date=date,
            flight_count=FlightRepository(connection).count(date=date),
        )

    @staticmethod
    def longest_block(
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> LongestBlockResponse:
        block_hours, flights = FlightRepository(connection).longest_block()
        return LongestBlockResponse(block_hours=block_hours, flights=flights)