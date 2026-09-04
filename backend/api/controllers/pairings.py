"""Pairing retrieval controller."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_connection
from backend.api.schemas import (
    PairingCrewResponse,
    PairingDayResponse,
    PairingResponse,
)
from backend.infrastructure.repositories import PairingRepository


def _pairing_response(pairing) -> PairingResponse:
    return PairingResponse(
        pairing_id=pairing.pairing_id,
        aircraft=pairing.aircraft,
        crew=[
            PairingCrewResponse(crew_id=member.crew_id, role=member.role)
            for member in pairing.crew
        ],
        days=[
            PairingDayResponse(
                date=day.date,
                report_utc=day.report_utc,
                release_utc=day.release_utc,
                flight_ids=list(day.flight_ids),
            )
            for day in pairing.days
        ],
    )


class PairingController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/pairings", tags=["pairings"])
        self.router.add_api_route(
            "/{pairing_id}/crew",
            self.get_crew,
            methods=["GET"],
            response_model=list[PairingCrewResponse],
        )
        self.router.add_api_route(
            "/{pairing_id}",
            self.get_pairing,
            methods=["GET"],
            response_model=PairingResponse,
        )

    @staticmethod
    def _get_pairing(pairing_id: str, connection: sqlite3.Connection):
        pairing = PairingRepository(connection).get(pairing_id)
        if pairing is None:
            raise HTTPException(status_code=404, detail="Pairing not found")
        return pairing

    @classmethod
    def get_pairing(
        cls,
        pairing_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> PairingResponse:
        return _pairing_response(cls._get_pairing(pairing_id, connection))

    @classmethod
    def get_crew(
        cls,
        pairing_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[PairingCrewResponse]:
        return _pairing_response(cls._get_pairing(pairing_id, connection)).crew