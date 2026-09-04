"""Risk-signal retrieval controller."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_connection
from backend.api.schemas import RiskSignalResponse
from backend.infrastructure.repositories import RiskSignalRepository


class RiskSignalController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/crew", tags=["risk-signals"])
        self.router.add_api_route(
            "/{crew_id}/risk-signal",
            self.get,
            methods=["GET"],
            response_model=RiskSignalResponse,
        )

    @staticmethod
    def get(
        crew_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> RiskSignalResponse:
        signal = RiskSignalRepository(connection).get(crew_id)
        if signal is None:
            raise HTTPException(status_code=404, detail="Risk signal not found")
        return RiskSignalResponse(
            crew_id=signal.crew_id,
            as_of_utc=signal.as_of_utc,
            disruption_risk_score=signal.disruption_risk_score,
            drivers=list(signal.drivers),
        )