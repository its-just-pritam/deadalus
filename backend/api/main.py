"""FastAPI application for crew operations data retrieval."""

from fastapi import FastAPI

from backend.api.controllers.chat import ChatController
from backend.api.controllers.crew import CrewController
from backend.api.controllers.reserves import ReserveController


app = FastAPI(
    title="Crew Operations API",
    version="0.1.0",
    description="Read-only crew operations data retrieval API.",
)

app.include_router(CrewController().router)
app.include_router(ReserveController().router)
app.include_router(ChatController().router)
