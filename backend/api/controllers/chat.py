"""Conversational controller backed by LangChain retrieval tools."""

import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.dependencies import DATABASE_PATH, get_connection
from backend.infrastructure.database.connection import connect
from backend.llm.agent import answer_question
from backend.llm.tools import clear_tool_call_logging, set_tool_call_logging


logger = logging.getLogger(__name__)

# In-memory status of answers still being generated in a background thread,
# keyed by the user question's chat_history message_id.
_pending_lock = threading.Lock()
_pending_answers: dict[int, dict] = {}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str = Field(default="default", min_length=1, max_length=100)


class ChatAcceptedResponse(BaseModel):
    message_id: int
    question: str
    created_at: str
    status: str


class ChatStatusResponse(BaseModel):
    message_id: int
    status: str
    answer: str | None
    created_at: str | None
    response_time_ms: int | None
    error: str | None


class ChatHistoryMessage(BaseModel):
    message_id: int
    session_id: str
    role: str
    content: str
    source_question: str | None
    created_at: str
    response_time_ms: int | None


class ToolCallRecord(BaseModel):
    id: int
    message_id: int
    tool_name: str
    method: str
    request_url: str
    curl_command: str
    status_code: int | None
    duration_ms: float | None
    success: bool
    error_message: str | None
    created_at: str


class ChatController:
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route(
            "/chat",
            self.chat,
            methods=["POST"],
            response_model=ChatAcceptedResponse,
        )
        self.router.add_api_route(
            "/chat/status",
            self.status,
            methods=["GET"],
            response_model=ChatStatusResponse,
        )
        self.router.add_api_route(
            "/chat/history",
            self.history,
            methods=["GET"],
            response_model=list[ChatHistoryMessage],
        )
        self.router.add_api_route(
            "/chat/tool-calls",
            self.tool_calls,
            methods=["GET"],
            response_model=list[ToolCallRecord],
        )

    @staticmethod
    def chat(
        request: ChatRequest,
        connection=Depends(get_connection),
    ) -> ChatAcceptedResponse:
        question = request.question.strip()
        created_at = datetime.now(timezone.utc).isoformat()
        user_cursor = connection.execute(
            "INSERT INTO chat_history "
            "(session_id, role, content, source_question, created_at, response_time_ms) "
            "VALUES (?, 'user', ?, NULL, ?, NULL)",
            (request.session_id, question, created_at),
        )
        connection.commit()
        message_id = user_cursor.lastrowid
        with _pending_lock:
            _pending_answers[message_id] = {
                "status": "pending",
                "answer": None,
                "created_at": None,
                "response_time_ms": None,
                "error": None,
            }
        threading.Thread(
            target=ChatController._answer_in_background,
            args=(message_id, request.session_id, question),
            daemon=True,
        ).start()
        return ChatAcceptedResponse(
            message_id=message_id,
            question=question,
            created_at=created_at,
            status="pending",
        )

    @staticmethod
    def _answer_in_background(message_id: int, session_id: str, question: str) -> None:
        started_at = time.perf_counter()
        connection = connect(DATABASE_PATH)
        try:
            set_tool_call_logging(connection, message_id)
            try:
                answer = answer_question(question)
            finally:
                clear_tool_call_logging()
            response_time_ms = round((time.perf_counter() - started_at) * 1000)
            created_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "INSERT INTO chat_history "
                "(session_id, role, content, source_question, created_at, response_time_ms) "
                "VALUES (?, 'assistant', ?, ?, ?, ?)",
                (session_id, answer, question, created_at, response_time_ms),
            )
            connection.commit()
            with _pending_lock:
                _pending_answers[message_id] = {
                    "status": "done",
                    "answer": answer,
                    "created_at": created_at,
                    "response_time_ms": response_time_ms,
                    "error": None,
                }
        except Exception as exc:
            connection.rollback()
            logger.exception("chat_background_error")
            with _pending_lock:
                _pending_answers[message_id] = {
                    "status": "error",
                    "answer": None,
                    "created_at": None,
                    "response_time_ms": None,
                    "error": str(exc),
                }
        finally:
            connection.close()

    @staticmethod
    def status(message_id: int = Query(ge=1)) -> ChatStatusResponse:
        with _pending_lock:
            entry = _pending_answers.get(message_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Unknown message_id")
        return ChatStatusResponse(message_id=message_id, **entry)

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

    @staticmethod
    def tool_calls(
        message_id: int = Query(ge=1),
        connection=Depends(get_connection),
    ) -> list[ToolCallRecord]:
        rows = connection.execute(
            "SELECT id, message_id, tool_name, method, request_url, curl_command, "
            "status_code, duration_ms, success, error_message, created_at "
            "FROM tool_calls WHERE message_id = ? ORDER BY id",
            (message_id,),
        ).fetchall()
        return [
            ToolCallRecord(
                id=row["id"],
                message_id=row["message_id"],
                tool_name=row["tool_name"],
                method=row["method"],
                request_url=row["request_url"],
                curl_command=row["curl_command"],
                status_code=row["status_code"],
                duration_ms=row["duration_ms"],
                success=bool(row["success"]),
                error_message=row["error_message"],
                created_at=row["created_at"],
            )
            for row in rows
        ]