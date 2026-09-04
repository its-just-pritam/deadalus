"""FastAPI application for crew operations data retrieval."""

from fastapi import FastAPI

from backend.api.controllers.chat import ChatController
from backend.api.controllers.certifications import CertificationController
from backend.api.controllers.crew import CrewController
from backend.api.controllers.duty_clocks import DutyClockController
from backend.api.controllers.flights import FlightController
from backend.api.controllers.pairings import PairingController
from backend.api.controllers.reserves import ReserveController
from backend.api.controllers.rules import RuleController


app = FastAPI(
    title="Crew Operations API",
    version="0.1.0",
    description="Read-only crew operations data retrieval API.",
)

app.include_router(CrewController().router)
app.include_router(CertificationController().router)
app.include_router(DutyClockController().router)
app.include_router(FlightController().router)
app.include_router(PairingController().router)
app.include_router(ReserveController().router)
app.include_router(RuleController().router)
app.include_router(ChatController().router)
