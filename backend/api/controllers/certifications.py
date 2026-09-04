"""Certification retrieval controller."""

from datetime import date
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_connection
from backend.api.schemas import CertificationResponse
from backend.infrastructure.repositories import CertificationRepository


class CertificationController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/certifications", tags=["certifications"])
        self.router.add_api_route(
            "/expiring",
            self.list_expiring,
            methods=["GET"],
            response_model=list[CertificationResponse],
        )

    @staticmethod
    def list_expiring(
        from_date: str = Query(alias="from", min_length=1),
        to_date: str = Query(alias="to", min_length=1),
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> list[CertificationResponse]:
        try:
            start = date.fromisoformat(from_date)
            end = date.fromisoformat(to_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="from and to must be ISO dates in YYYY-MM-DD format",
            ) from exc
        if start > end:
            raise HTTPException(
                status_code=400,
                detail="from must be on or before to",
            )

        certifications = CertificationRepository(connection).list_expiring(
            from_date=start.isoformat(),
            to_date=end.isoformat(),
        )
        return [
            CertificationResponse(
                crew_id=certification.crew_id,
                cert_type=certification.cert_type,
                valid_from=certification.valid_from,
                valid_to=certification.valid_to,
            )
            for certification in certifications
        ]