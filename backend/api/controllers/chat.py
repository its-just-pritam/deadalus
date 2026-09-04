"""Conversational controller backed by LangChain retrieval tools."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.llm.agent import answer_question


logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str


class ChatController:
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route(
            "/chat",
            self.chat,
            methods=["POST"],
            response_model=ChatResponse,
        )

    @staticmethod
    def chat(request: ChatRequest) -> ChatResponse:
        try:
            return ChatResponse(answer=answer_question(request.question))
        except RuntimeError as exc:
            logger.exception("chat_runtime_error")
            raise HTTPException(
                status_code=503,
                detail={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            ) from exc
        except Exception as exc:
            logger.exception("chat_provider_error")
            raise HTTPException(
                status_code=502,
                detail={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            ) from exc