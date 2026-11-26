"""Run the grid: every report x defense x judge. Cached, paced, resumable."""

import argparse
import hashlib
import json
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from triage import defenses
from triage.models import MockModel, Model, OpenAICompatModel, RateLimited, model_id
from triage.schema import GROUPS, Outcome, Report, Usage, split_front_matter

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# Ordered so each finished day leaves complete, usable results; guard reuses baseline.
DEFENSE_ORDER = ("baseline", "guard", "quarantine", "spotlight")
SHORT_WAIT_SECONDS = 120
MAX_SHORT_RETRIES = 10
TOKENS_PER_MINUTE = 6000
REQUESTS_PER_MINUTE = 25


class DailyLimitReached(Exception):
    """A 429 asked us to wait long enough that the daily quota must be spent."""

    def __init__(self, model_name: str, detail: str = "long retry-after"):
        super().__init__(f"{model_name}: {detail}")
        self.model_name = model_name


def complete_with_retry(model: Model, system: str, user: str, sleep=time.sleep):
    """Sleep through short 429 waits; raise DailyLimitReached on long ones."""
    for _ in range(MAX_SHORT_RETRIES):
        try:
            return model.complete(system, user)
        except RateLimited as exc:
            if exc.retry_after > SHORT_WAIT_SECONDS:
                raise DailyLimitReached(model.name) from exc
            sleep(exc.retry_after)
    raise DailyLimitReached(model.name, f"still rate limited after {MAX_SHORT_RETRIES} waits")


class Pacer:
    """Keeps one model under its per-minute token and request limits."""

    def __init__(self, tokens_per_minute: int, requests_per_minute: int):
        self.tokens_per_minute = tokens_per_minute
        self.requests_per_minute = requests_per_minute
        self.sent: deque[tuple[float, int]] = deque()
        self.lock = threading.Lock()

    def wait(self, tokens: int) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                while self.sent and now - self.sent[0][0] > 60:
                    self.sent.popleft()
                used = sum(t for _, t in self.sent)
                fits = used + tokens <= self.tokens_per_minute
                if not self.sent or (fits and len(self.sent) < self.requests_per_minute):
                    self.sent.append((now, tokens))
                    return
            time.sleep(1)


class CachedCaller:
    """The Call used by defenses: one JSONL line per finished model call."""

    def __init__(self, path: Path, paced: bool):
        self.path = path
        self.paced = paced
        self.lock = threading.Lock()
        self.pacers: dict[str, Pacer] = {}
        self.cache: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.cache[row["key"]] = row

    def __call__(self, model: Model, defense: str, system: str, user: str):
        key = hashlib.sha256(json.dumps([model.name, defense, system, user]).encode()).hexdigest()
        if key in self.cache:
            row = self.cache[key]
            return row["text"], Usage(**row["usage"])
        if self.paced:
            pacer = self.pacers.setdefault(
                model.name, Pacer(TOKENS_PER_MINUTE, REQUESTS_PER_MINUTE)
            )
            pacer.wait(len(system + user) // 4 + 400)
        text, usage = complete_with_retry(model, system, user)
        row = {
            "key": key,
            "model": model.name,
            "defense": defense,
            "text": text,
            "usage": asdict(usage),
        }
        with self.lock:
            self.cache[key] = row
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        return text, usage


def load_reports(limit: int | None) -> dict[str, list[Report]]:
    """All reports by group, sorted by id, optionally the first `limit` of each."""
    groups: dict[str, list[Report]] = {group: [] for group in GROUPS}
    for path in sorted((DATA / "real").glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        text = f"# {item['title']}\n\n{item['body']}"
        groups["real"].append(Report(item["id"], "real", text, True, item["severity"]))
    for path in sorted((DATA / "fakes").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        groups["fake_clean"].append(Report(meta["id"], "fake_clean", body, False, "none"))
    for path in sorted((DATA / "attacked").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        groups["fake_attacked"].append(
            Report(
                meta["id"], "fake_attacked", body, False, "none", meta["attack"], meta["placement"]
            )
        )
    return {group: items[:limit] for group, items in groups.items()}


def evaluate(
    report: Report, defense: str, judge: Model, extractor: Model, guard: Model, call: CachedCaller
) -> Outcome:
    if defense == "baseline":
        return defenses.baseline(report.text, judge, call)
    if defense == "spotlight":
        return defenses.spotlight(report.text, judge, call)
    if defense == "quarantine":
        return defenses.quarantine(report.text, extractor, judge, call)
    return defenses.guard(report.text, guard, judge, call)


def outcome_row(report: Report, defense: str, judge: str, outcome: Outcome, mock: bool) -> dict:
    return {
        "report_id": report.id,
        "group": report.group,
        "label_valid": report.valid,
        "attack": report.attack,
        "placement": report.placement,
        "defense": defense,
        "judge": judge,
        "mock": mock,
        "verdict": asdict(outcome.verdict) if outcome.verdict else None,
        "parse_failure": outcome.parse_failure,
        "flagged": outcome.flagged,
        "usage": {name: asdict(usage) for name, usage in sorted(outcome.usage.items())},
    }


def build_models(mock: bool, judge_keys: list[str]):
    if mock:
        judges = [MockModel(f"MOCK-judge-{key}") for key in judge_keys]
        return (
            judges,
            MockModel("MOCK-extractor", "extractor"),
            MockModel("MOCK-guard", "guard", False),
        )
    judges = [OpenAICompatModel(model_id(f"JUDGE_{key.upper()}_MODEL")) for key in judge_keys]
    return (
        judges,
        OpenAICompatModel(model_id("EXTRACTOR_MODEL")),
        OpenAICompatModel(model_id("GUARD_MODEL"), json_mode=False),
    )


def models_for(defense: str, judge: Model, extractor: Model, guard: Model) -> set[str]:
    """Every model a cell may call, so a spent quota skips only the cells that need it."""
    extra = {"quarantine": {extractor.name}, "guard": {guard.name}}.get(defense, set())
    return {judge.name} | extra


def evaluate_cell(items, defense, judge, extractor, guard, call, workers) -> list[Outcome]:
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        return list(pool.map(lambda r: evaluate(r, defense, judge, extractor, guard, call), items))
    finally:
        # On a spent quota, drop queued reports instead of sending each one to a 429.
        pool.shutdown(cancel_futures=True)


def run_grid(reports, defense_names, judges, extractor, guard, call, mock, workers=2):
    """Run cells in order; returns (rows, cells done, cells total, any quota spent)."""
    cells = [(d, j, g) for d in DEFENSE_ORDER if d in defense_names for j in judges for g in GROUPS]
    rows: list[dict] = []
    exhausted: set[str] = set()
    done = 0
    for index, (defense, judge, group) in enumerate(cells, start=1):
        if models_for(defense, judge, extractor, guard) & exhausted:
            continue
        items = reports[group]
        try:
            outcomes = evaluate_cell(items, defense, judge, extractor, guard, call, workers)
        except DailyLimitReached as exc:
            exhausted.add(exc.model_name)
            print(f"daily limit for {exc.model_name}; skipping its remaining cells ({exc})")
            continue
        done += 1
        rows += [
            outcome_row(r, defense, judge.name, o, mock)
            for r, o in zip(items, outcomes, strict=True)
        ]
        approved = sum(1 for o in outcomes if o.verdict and o.verdict.valid)
        print(
            f"[{index}/{len(cells)}] {defense:<10} {judge.name:<28} {group:<13} "
            f"n={len(items):<3} approved={approved:<3} "
            f"parse_failures={sum(o.parse_failure for o in outcomes)}"
        )
    return rows, done, len(cells), bool(exhausted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="a,b", help="judges to run: a (large), b (small)")
    parser.add_argument("--defenses", default=",".join(DEFENSE_ORDER))
    parser.add_argument("--limit", type=int, default=None, help="max reports per group")
    parser.add_argument("--model", choices=["groq", "mock"], default="groq")
    args = parser.parse_args(argv)
    mock = args.model == "mock"
    defense_names = args.defenses.split(",")
    unknown = set(defense_names) - set(DEFENSE_ORDER)
    if unknown:
        parser.error(f"unknown defenses: {sorted(unknown)}")
    out_dir = ROOT / "results" / ("mock" if mock else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = load_reports(args.limit)
    if not reports["real"]:
        print("note: no real reports in data/real; run `make fetch` for precision and recall")
    judges, extractor, guard = build_models(mock, args.models.split(","))
    call = CachedCaller(out_dir / "cache.jsonl", paced=not mock)
    rows, done, total, stopped = run_grid(
        reports, defense_names, judges, extractor, guard, call, mock
    )
    with (out_dir / "outcomes.jsonl").open("w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row) + "\n" for row in rows)
    if stopped:
        print(f"finished {done} of {total} cells; {total - done} remain")
        print("daily limit reached; rerun tomorrow to resume")
    else:
        print(f"finished all {total} cells; outcomes in {out_dir / 'outcomes.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
