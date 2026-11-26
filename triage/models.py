"""One OpenAI-compatible client for Groq or Ollama, plus an offline mock."""

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from triage.schema import Usage

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

DEFAULT_MODELS = {
    "JUDGE_A_MODEL": "openai/gpt-oss-120b",
    "JUDGE_B_MODEL": "openai/gpt-oss-20b",
    # The spec named qwen3.8-27b; Groq does not serve it, so this is the nearest Qwen3.
    "EXTRACTOR_MODEL": "qwen/qwen3-32b",
    "GUARD_MODEL": "meta-llama/llama-prompt-guard-2-86m",
}

MAX_OUTPUT_TOKENS = 400


class RateLimited(Exception):
    """The provider returned 429; retry_after is in seconds."""

    def __init__(self, retry_after: float):
        super().__init__(f"rate limited, retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class Model(Protocol):
    name: str
    json_mode: bool

    def complete(self, system: str, user: str) -> tuple[str, Usage]: ...


def model_id(env_key: str) -> str:
    """Model id from the environment, falling back to the default."""
    return os.environ.get(env_key) or DEFAULT_MODELS[env_key]


def _request_options(name: str) -> dict:
    # Reasoning tokens count against the free-tier limits, so keep them low.
    if name.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    if name.startswith("qwen/qwen3"):
        return {"extra_body": {"reasoning_effort": "none"}}
    return {}


def _retry_after(headers) -> float:
    value = headers.get("retry-after") if headers is not None else None
    if value is None:
        # Groq always sends retry-after on 429; a missing one is treated as a short wait.
        return 30.0
    return float(value)


@dataclass
class OpenAICompatModel:
    """Chat completions against Groq, or any OpenAI-compatible server."""

    name: str
    json_mode: bool = True

    def __post_init__(self) -> None:
        from openai import OpenAI

        base_url = os.environ.get("OPENAI_COMPAT_BASE_URL") or GROQ_BASE_URL
        api_key = os.environ.get("GROQ_API_KEY")
        if base_url == GROQ_BASE_URL and not api_key:
            raise SystemExit("GROQ_API_KEY is not set. Copy .env.example to .env and fill it in.")
        # Retries are ours, so a 429 with a long wait can stop the run instead of blocking it.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "ollama", max_retries=0)

    def complete(self, system: str, user: str) -> tuple[str, Usage]:
        """Send one chat completion and return its text and token usage."""
        import openai

        messages = [{"role": "user", "content": user}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        options = _request_options(self.name)
        if self.json_mode:
            options["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(
                model=self.name,
                messages=messages,
                temperature=0,
                max_completion_tokens=MAX_OUTPUT_TOKENS,
                **options,
            )
        except openai.RateLimitError as exc:
            raise RateLimited(_retry_after(exc.response.headers)) from exc
        return response.choices[0].message.content or "", _usage(response.usage)


def _usage(usage) -> Usage:
    if usage is None:
        return Usage()
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) or 0
    return Usage(usage.prompt_tokens, usage.completion_tokens, reasoning)


TRIGGER_WORDS = ("verified", "critical", "rce")


@dataclass
class MockModel:
    """Offline, deterministic, and naive on purpose: trigger words win approval."""

    name: str
    role: str = "judge"
    json_mode: bool = True

    def complete(self, system: str, user: str) -> tuple[str, Usage]:
        """Answer like the given role would, with no network."""
        if self.role == "guard":
            text = _mock_guard(user)
        elif self.role == "extractor":
            text = _mock_extract(user)
        else:
            text = _mock_judge(user)
        return text, Usage(len(system + user) // 4, len(text) // 4, 0)


def _mock_judge(user: str) -> str:
    lowered = user.lower()
    hit = next((word for word in TRIGGER_WORDS if word in lowered), None)
    return json.dumps(
        {
            "valid": hit is not None,
            "severity": "critical" if hit else "none",
            "policy_rule": "evidence rule" if hit else "no working reproduction",
            "rationale": f"mock saw '{hit}'" if hit else "mock saw no trigger words",
        }
    )


def _mock_extract(user: str) -> str:
    endpoint = re.search(r"/[\w./-]+", user)
    lines = [line.strip() for line in user.splitlines() if line.strip()]
    return json.dumps(
        {
            "claimed_vuln_type": "unknown",
            "affected_endpoint": endpoint.group(0) if endpoint else "",
            "repro_steps": [" ".join(line.split()[:25]) for line in lines[1:4]],
            "evidence_provided": "HTTP/1.1" in user,
            "evidence_summary": " ".join(" ".join(lines[1:3]).split()[:40]),
        }
    )


def _mock_guard(user: str) -> str:
    lowered = user.lower()
    return "0.99" if "ignore" in lowered and "instruction" in lowered else "0.01"
