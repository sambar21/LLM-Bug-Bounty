"""Fetch the selected HackerOne reports into data/real/ (gitignored, never redistributed)."""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDS = ROOT / "data" / "real_ids.csv"
OUT_DIR = ROOT / "data" / "real"
MAX_CHARS = 2500
TRUNCATED = "\n\n[truncated]"
RETRIES = 3
USER_AGENT = "triage-injection-bench/0.1 (research; one request per second)"


def truncate(body: str, limit: int = MAX_CHARS) -> str:
    """Cut to the limit with a visible marker, so the model knows text is missing."""
    return body if len(body) <= limit else body[:limit] + TRUNCATED


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SystemExit(
                    f"{url} returned 404; add the id to EXCLUDED in scripts/select_real.py"
                ) from exc
            if exc.code in (401, 403) or attempt == RETRIES:
                raise SystemExit(
                    f"{url} returned HTTP {exc.code}. If every report fails, this network "
                    "probably blocks hackerone.com; run the fetch from another machine."
                ) from exc
        except urllib.error.URLError as exc:
            if attempt == RETRIES:
                raise SystemExit(f"could not reach {url}: {exc.reason}") from exc
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def to_record(row: dict, data: dict) -> dict:
    body = data.get("vulnerability_information") or ""
    if not body.strip():
        raise SystemExit(
            f"report {row['id']} has no vulnerability_information; add it to EXCLUDED in "
            "scripts/select_real.py and rerun `make select`"
        )
    severity = (data.get("severity") or {}).get("rating")
    return {
        "id": row["id"],
        "url": row["url"],
        "vuln_type": row["vuln_type"],
        "title": data["title"],
        "severity": severity if severity in ("low", "medium", "high", "critical") else None,
        "body": truncate(body),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="refetch reports already on disk")
    args = parser.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with IDS.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        path = OUT_DIR / f"{row['id']}.json"
        if path.exists() and not args.force:
            continue
        record = to_record(row, fetch_json(f"{row['url']}.json"))
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"fetched {row['id']}: {record['title'][:70]}")
        time.sleep(1)
    print(f"{len(list(OUT_DIR.glob('*.json')))} reports in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
