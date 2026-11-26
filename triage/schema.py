"""Records shared across the pipeline, and strict parsers for model output."""

import json
from dataclasses import dataclass, field

SEVERITIES = ("none", "low", "medium", "high", "critical")
GROUPS = ("real", "fake_clean", "fake_attacked")

VERDICT_KEYS = {"valid", "severity", "policy_rule", "rationale"}
EXTRACTION_KEYS = {
    "claimed_vuln_type",
    "affected_endpoint",
    "repro_steps",
    "evidence_provided",
    "evidence_summary",
}


class ParseError(ValueError):
    """Model output did not match the expected schema."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    # Wall-clock seconds of the API call itself; 0 for cached calls made before this was kept.
    seconds: float = 0.0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.reasoning_tokens + other.reasoning_tokens,
            self.seconds + other.seconds,
        )


@dataclass(frozen=True)
class Verdict:
    valid: bool
    severity: str
    policy_rule: str
    rationale: str


@dataclass(frozen=True)
class Extraction:
    claimed_vuln_type: str
    affected_endpoint: str
    repro_steps: list[str]
    evidence_provided: bool
    evidence_summary: str


@dataclass(frozen=True)
class Report:
    id: str
    group: str
    text: str
    valid: bool
    severity: str | None = None
    attack: str | None = None
    placement: str | None = None


@dataclass
class Outcome:
    """What one defense decided about one report, and what it cost."""

    verdict: Verdict | None
    # Keyed by model name, because defenses mix models with different prices.
    usage: dict[str, Usage] = field(default_factory=dict)
    parse_failure: bool = False
    flagged: bool | None = None


def merge_usage(*parts: dict[str, Usage]) -> dict[str, Usage]:
    """Add per-model usage dicts together."""
    merged: dict[str, Usage] = {}
    for part in parts:
        for name, usage in part.items():
            merged[name] = merged.get(name, Usage()) + usage
    return merged


def _load_object(text: str, keys: set[str]) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("expected a JSON object")
    if set(data) != keys:
        raise ParseError(f"expected keys {sorted(keys)}, got {sorted(data)}")
    return data


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ParseError(message)


def _words(text: str) -> int:
    return len(text.split())


def parse_verdict(text: str) -> Verdict:
    """Parse a judge reply, rejecting anything outside the schema."""
    data = _load_object(text, VERDICT_KEYS)
    _require(isinstance(data["valid"], bool), "valid must be a boolean")
    _require(data["severity"] in SEVERITIES, f"bad severity: {data['severity']!r}")
    _require(isinstance(data["policy_rule"], str), "policy_rule must be a string")
    _require(isinstance(data["rationale"], str), "rationale must be a string")
    _require(_words(data["rationale"]) <= 60, "rationale over 60 words")
    return Verdict(data["valid"], data["severity"], data["policy_rule"], data["rationale"])


def parse_extraction(text: str) -> Extraction:
    """Parse an extractor reply, rejecting anything outside the schema."""
    data = _load_object(text, EXTRACTION_KEYS)
    for key in ("claimed_vuln_type", "affected_endpoint", "evidence_summary"):
        _require(isinstance(data[key], str), f"{key} must be a string")
    steps = data["repro_steps"]
    _require(isinstance(steps, list), "repro_steps must be a list")
    _require(len(steps) <= 8, "repro_steps has more than 8 items")
    for step in steps:
        _require(isinstance(step, str), "each repro step must be a string")
        _require(_words(step) <= 25, "a repro step is over 25 words")
    _require(isinstance(data["evidence_provided"], bool), "evidence_provided must be a boolean")
    _require(_words(data["evidence_summary"]) <= 40, "evidence_summary over 40 words")
    return Extraction(
        data["claimed_vuln_type"],
        data["affected_endpoint"],
        list(steps),
        data["evidence_provided"],
        data["evidence_summary"],
    )


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a markdown file into its flat key: value front matter and body."""
    if not text.startswith("---\n"):
        raise ValueError("file has no front matter")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError("front matter is not closed")
    meta = {}
    for line in head.splitlines():
        key, colon, value = line.partition(":")
        if not colon:
            raise ValueError(f"bad front matter line: {line!r}")
        meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def join_front_matter(meta: dict[str, str], body: str) -> str:
    """Inverse of split_front_matter."""
    head = "\n".join(f"{key}: {value}" for key, value in meta.items())
    return f"---\n{head}\n---\n\n{body}"
