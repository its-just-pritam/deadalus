"""CLI that runs tests.json against the chat API and grades answers with an LLM judge.

Usage:
    python testing/run_evaluation.py --api-url http://localhost:8000
    python testing/run_evaluation.py --tier 1 --tier 2
    python testing/run_evaluation.py --id Q01 --id Q20 --output testing/report.json

Requires OPENROUTER_API_KEY and OPENROUTER_MODEL in the environment, matching the
backend's LLM configuration (see backend/llm/agent.py), so the judge uses the same model.
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


DEFAULT_TESTS_PATH = Path(__file__).resolve().parent / "tests.json"

JUDGE_SYSTEM_PROMPT = """You are grading a crew-operations assistant's answer against a reference answer.

Compare the ACTUAL answer to the EXPECTED answer for the given question. The actual answer is in
natural language and may phrase facts differently, but it must contain the same operational facts,
numbers, and conclusions as the expected answer. Ignore wording, formatting, and ordering
differences. Mark as failed if the actual answer omits, contradicts, or gets wrong any material
fact present in the expected answer.
"""


class Verdict(BaseModel):
    passed: bool = Field(description="True if the actual answer is consistent with the expected answer")
    reasoning: str = Field(description="One or two sentence justification for the verdict")


def build_judge_model() -> ChatOpenAI:
    """Build the grading model using the same OpenRouter configuration as the backend agent."""
    api_key = "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"
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    model_name = "z-ai/glm-5.3-flash"
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
    return ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers=default_headers,
    )


def judge_answer(model: ChatOpenAI, prompt: str, expected_answer: Any, actual_answer: str) -> Verdict:
    structured_model = model.with_structured_output(Verdict)
    message = (
        f"QUESTION:\n{prompt}\n\n"
        f"EXPECTED ANSWER (reference facts):\n{json.dumps(expected_answer, indent=2)}\n\n"
        f"ACTUAL ANSWER (from the assistant under test):\n{actual_answer}\n"
    )
    return structured_model.invoke([("system", JUDGE_SYSTEM_PROMPT), ("user", message)])


def load_tests(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def ask_chat_api(
    base_url: str,
    question: str,
    session_id: str,
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    response = httpx.post(
        f"{base_url}/api/chat",
        json={"question": question, "session_id": session_id},
        timeout=30.0,
    )
    response.raise_for_status()
    message_id = response.json()["message_id"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status_response = httpx.get(
            f"{base_url}/api/chat/status", params={"message_id": message_id}, timeout=30.0
        )
        status_response.raise_for_status()
        status = status_response.json()
        if status["status"] == "done":
            return status
        if status["status"] == "error":
            raise RuntimeError(status.get("error") or "Chat API returned an error")
        time.sleep(poll_interval)
    raise TimeoutError(f"Timed out waiting for message_id={message_id} to complete")


def run(args: argparse.Namespace) -> int:
    tests = load_tests(args.tests)
    if args.tiers:
        tests = [test for test in tests if test.get("tier") in args.tiers]
    if args.ids:
        wanted = set(args.ids)
        tests = [test for test in tests if test.get("question_id") in wanted]
    if not tests:
        print("No matching tests to run.")
        return 1

    judge_model = build_judge_model()

    results: list[dict[str, Any]] = []
    passed_count = 0
    for index, test in enumerate(tests, start=1):
        question_id = test["question_id"]
        prompt = test["prompt"]
        expected_answer = test["expected_answer"]
        session_id = f"eval-{question_id}-{uuid.uuid4().hex[:8]}"

        print(f"[{index}/{len(tests)}] {question_id}: {prompt}")
        try:
            chat_result = ask_chat_api(args.api_url, prompt, session_id, args.poll_interval, args.timeout)
            actual_answer = chat_result["answer"]
        except Exception as exc:
            print(f"  ERROR calling chat API: {exc}")
            results.append(
                {
                    "question_id": question_id,
                    "tier": test.get("tier"),
                    "prompt": prompt,
                    "response": None,
                    "passed": False,
                }
            )
            continue

        try:
            verdict = judge_answer(judge_model, prompt, expected_answer, actual_answer)
        except Exception as exc:
            print(f"  ERROR judging answer: {exc}")
            results.append(
                {
                    "question_id": question_id,
                    "tier": test.get("tier"),
                    "prompt": prompt,
                    "response": actual_answer,
                    "passed": False,
                }
            )
            continue

        status_label = "PASS" if verdict.passed else "FAIL"
        print(f"  {status_label} - {verdict.reasoning}")
        passed_count += int(verdict.passed)
        results.append(
            {
                "question_id": question_id,
                "tier": test.get("tier"),
                "prompt": prompt,
                "response": actual_answer,
                "passed": verdict.passed,
            }
        )

    total = len(results)
    print(f"\n{passed_count}/{total} passed")

    if args.output:
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Wrote detailed report to {args.output}")

    return 0 if passed_count == total else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the crew operations chat API against tests.json")
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS_PATH, help="Path to tests.json")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("CREW_OPERATIONS_API_URL", "http://localhost:8000"),
        help="Base URL of the chat API",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between status polls")
    parser.add_argument("--timeout", type=float, default=120.0, help="Seconds to wait for each answer before failing")
    parser.add_argument("--tier", dest="tiers", type=int, action="append", help="Only run tests of this tier (repeatable)")
    parser.add_argument("--id", dest="ids", action="append", help="Only run this question_id (repeatable)")
    parser.add_argument("--output", type=Path, help="Write a JSON report to this path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
