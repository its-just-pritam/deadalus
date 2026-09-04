"""Rule retrieval controller."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_connection
from backend.api.schemas import RuleResponse
from backend.infrastructure.repositories import RulesetRepository


class RuleController:
    def __init__(self):
        self.router = APIRouter(prefix="/api/rules", tags=["rules"])
        self.router.add_api_route(
            "/{rule_id}",
            self.get,
            methods=["GET"],
            response_model=RuleResponse,
        )

    @staticmethod
    def get(
        rule_id: str,
        connection: sqlite3.Connection = Depends(get_connection),
    ) -> RuleResponse:
        rule = RulesetRepository(connection).get_rule(rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        return RuleResponse(
            rule_id=rule.rule_id,
            text=rule.text,
            parameters={
                key: value
                for key, value in vars(rule.parameters).items()
                if value is not None
            },
        )