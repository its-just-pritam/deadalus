"""FastAPI application for crew operations data retrieval."""

from fastapi import FastAPI

from backend.api.controllers.chat import ChatController
from backend.api.controllers.certifications import CertificationController
from backend.api.controllers.crew import CrewController
from backend.api.controllers.duty_clocks import DutyClockController
from backend.api.controllers.flights import FlightController
from backend.api.controllers.pairings import PairingController
from backend.api.controllers.risk_signals import RiskSignalController
from backend.api.controllers.operational_impact import OperationalImpactController
from backend.api.controllers.reserves import ReserveController
from backend.api.controllers.rules import RuleController
from backend.api.controllers.stations import StationController
from backend.api.controllers.operational import OperationalController


app = FastAPI(
    title="Crew Operations API",
    version="0.1.0",
    description="Read-only crew operations data retrieval API.",
)

app.include_router(CrewController().router)
app.include_router(CertificationController().router)
app.include_router(DutyClockController().router)
app.include_router(OperationalController().router)
app.include_router(OperationalImpactController().router)
app.include_router(FlightController().router)
app.include_router(PairingController().router)
app.include_router(PairingController().aircraft_router)
app.include_router(RiskSignalController().router)
app.include_router(ReserveController().router)
app.include_router(RuleController().router)
app.include_router(StationController().router)
app.include_router(ChatController().router)
