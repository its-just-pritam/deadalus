"""Tool-calling agent for operational retrieval questions."""

import os
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from backend.llm.tools import get_retrieval_tools


SYSTEM_PROMPT = """You are a crew operations assistant.

Use the retrieval tools for every question involving crew, reserves, bases,
ratings, status, reachability, duty hours, duty history, headroom, rules,
flights, pairings, or certifications. For flight questions, use the flight retrieval
tools for lookups, route/date filters, counts, and longest-block queries. For crew
search questions, use the crew search tool. For certification-expiry questions, use
the certification retrieval tool. For pairing questions, use the pairing
retrieval tools. Do not invent operational facts and do not
answer from memory. If the tools do not contain enough data, say what is
missing. Clearly distinguish retrieved facts from any explanation.
"""


def build_agent() -> Any:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    model_name = os.environ.get("OPENROUTER_MODEL")
    if not model_name:
        raise RuntimeError("OPENROUTER_MODEL is not configured")

    default_headers = {
        key: value
        for key, value in {
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL"),
            "X-Title": os.environ.get("OPENROUTER_SITE_NAME"),
        }.items()
        if value
    }

    model = ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers=default_headers,
        extra_body={"reasoning": {"enabled": True}},
    )
    return create_agent(model, tools=get_retrieval_tools(), system_prompt=SYSTEM_PROMPT)


def answer_question(question: str) -> str:
    result = build_agent().invoke({"messages": [("user", question)]})
    messages = result.get("messages", [])
    if not messages:
        return "No answer was returned."
    content = messages[-1].content
    if isinstance(content, str):
        return content
    return str(content)