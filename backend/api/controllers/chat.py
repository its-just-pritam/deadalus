"""Conversational controller backed by LangChain retrieval tools."""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.dependencies import get_connection
from backend.llm.agent import answer_question


logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str = Field(default="default", min_length=1, max_length=100)


class ChatResponse(BaseModel):
    message_id: int
    question: str
    answer: str
    created_at: str
    response_time_ms: int


class ChatHistoryMessage(BaseModel):
    message_id: int
    session_id: str
    role: str
    content: str
    source_question: str | None
    created_at: str
    response_time_ms: int | None


class ChatController:
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route(
            "/chat",
            self.chat,
            methods=["POST"],
            response_model=ChatResponse,
        )
        self.router.add_api_route(
            "/chat/history",
            self.history,
            methods=["GET"],
            response_model=list[ChatHistoryMessage],
        )

    @staticmethod
    def chat(
        request: ChatRequest,
        connection=Depends(get_connection),
    ) -> ChatResponse:
        started_at = time.perf_counter()
        question = request.question.strip()
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO chat_history "
            "(session_id, role, content, source_question, created_at, response_time_ms) "
            "VALUES (?, 'user', ?, NULL, ?, NULL)",
            (request.session_id, question, created_at),
        )
        try:
            answer = answer_question(question)
            response_time_ms = round((time.perf_counter() - started_at) * 1000)
            created_at = datetime.now(timezone.utc).isoformat()
            cursor = connection.execute(
                "INSERT INTO chat_history "
                "(session_id, role, content, source_question, created_at, response_time_ms) "
                "VALUES (?, 'assistant', ?, ?, ?, ?)",
                (request.session_id, answer, question, created_at, response_time_ms),
            )
            connection.commit()
            return ChatResponse(
                message_id=cursor.lastrowid,
                question=question,
                answer=answer,
                created_at=created_at,
                response_time_ms=response_time_ms,
            )
        except RuntimeError as exc:
            connection.rollback()
            logger.exception("chat_runtime_error")
            raise HTTPException(
                status_code=503,
                detail={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            ) from exc
        except Exception as exc:
            connection.rollback()
            logger.exception("chat_provider_error")
            raise HTTPException(
                status_code=502,
                detail={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            ) from exc

    @staticmethod
    def history(
        session_id: str = Query(default="default", min_length=1, max_length=100),
        connection=Depends(get_connection),
    ) -> list[ChatHistoryMessage]:
        rows = connection.execute(
            "SELECT id, session_id, role, content, source_question, created_at, response_time_ms "
            "FROM chat_history WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [
            ChatHistoryMessage(
                message_id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                source_question=row["source_question"],
                created_at=row["created_at"],
                response_time_ms=row["response_time_ms"],
            )
            for row in rows
        ]