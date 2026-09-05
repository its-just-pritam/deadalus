"""Tool-calling agent for operational retrieval questions."""

import os
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from backend.llm.tools import get_retrieval_tools


SYSTEM_PROMPT = """You are a crew operations assistant.

Follow this procedure for every question:

1. Identify the operational facts and calculations the question requires.
2. Select and call the retrieval tool that owns those facts before answering.
3. Use the tool response as the authoritative source for the answer.
4. Explain the result briefly and identify the rule or retrieved fact supporting it.

Tool selection:
- Crew, reserve, rating, status, reachability, duty, headroom, and certification questions use the matching crew/reserve tools.
- Flight questions use flight lookup, route, date, count, or longest-block tools.
- Match tool scope to question scope: use an aggregate or comparison tool for schedule-wide summaries, and use a record-detail tool when the user identifies a specific resource. 
- Use the smallest set of tools that fully answers the question; do not enumerate individual records when an aggregate result is available.
- Pairing questions use pairing and crew-assignment tools.
- Legality, qualification, rest, station-closure, and FDP questions use operational query tools.
- Cancellation impact, at-risk duty, reserve availability, and downstream-rest questions use their matching operational tools.
- Rule questions use the rule retrieval tool.

Reserve-window interpretation:
- An on-call window describes when the reserve may be called.
- Reachability describes whether a callout can support the required report time.
- Map event time to context, report time to window matching, and reachability to timing feasibility.
- When report time is missing, retrieve it from the pairing or flight schedule before evaluating reserve availability.
- Pass the required duty report time to `get_available_reserves.report_time`.

Use retrieved facts and backend calculations in the final answer. State any missing input explicitly.
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