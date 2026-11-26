"""Pick 25 disclosed HackerOne reports, deterministically, and write data/real_ids.csv."""

import argparse
import csv
import io
import sys
import urllib.request
from collections import Counter
from pathlib import Path

# Pinned so the selection never drifts as the upstream list grows.
SOURCE_COMMIT = "4c279ab93db2791adf4d6775d7539ee05b02cdb0"
SOURCE_URL = (
    f"https://raw.githubusercontent.com/reddelexc/hackerone-reports/{SOURCE_COMMIT}/data.csv"
)
OUT = Path(__file__).resolve().parent.parent / "data" / "real_ids.csv"
TOTAL = 25
MAX_PER_TYPE = 3

# Reports that cannot be triaged from their public JSON, found by probing on 2026-11-25.
# "summary": disclosed with an empty or near-empty body. "gone": the JSON returns 404.
EXCLUDED = {
    "231460": "summary", "307239": "summary", "380410": "gone", "383127": "summary",
    "391217": "summary", "403616": "summary", "415081": "summary", "639684": "summary",
    "663628": "summary", "697099": "summary", "699082": "gone", "723060": "gone",
    "739601": "summary", "758654": "gone", "786044": "gone", "811111": "gone",
    "819738": "gone", "863983": "gone", "868436": "gone", "881901": "gone",
    "923132": "gone", "1379975": "summary", "2262382": "summary", "2293343": "summary",
    "3124517": "summary", "3862641": "summary",
}

WEB_VULN_TYPES = {
    "Cross-site Scripting (XSS) - Stored",
    "Cross-site Scripting (XSS) - Reflected",
    "Insecure Direct Object Reference (IDOR)",
    "Server-Side Request Forgery (SSRF)",
    "SQL Injection",
    "Cross-Site Request Forgery (CSRF)",
    "Improper Access Control - Generic",
    "Privilege Escalation",
    "Open Redirect",
    "Business Logic Errors",
    "Path Traversal",
    "Command Injection - Generic",
    "Improper Authentication - Generic",
    "Information Disclosure",
}


def read_source(path: str | None) -> list[dict]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            text = response.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def report_id(link: str) -> str:
    return link.rstrip("/").rsplit("/", 1)[-1]


def select(rows: list[dict]) -> list[dict]:
    """Highest upvotes first, at most 3 per vuln type, ties broken by report id."""
    candidates = [
        row for row in rows
        if row["vuln_type"] in WEB_VULN_TYPES and float(row["bounty"] or 0) > 0
    ]
    candidates.sort(key=lambda row: (-int(row["upvotes"]), int(report_id(row["link"]))))
    picked: list[dict] = []
    per_type: Counter[str] = Counter()
    seen: set[str] = set()
    for row in candidates:
        rid = report_id(row["link"])
        if rid in EXCLUDED or rid in seen or per_type[row["vuln_type"]] >= MAX_PER_TYPE:
            continue
        picked.append(row)
        per_type[row["vuln_type"]] += 1
        seen.add(rid)
        if len(picked) == TOTAL:
            break
    return picked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="local copy of data.csv instead of downloading it")
    args = parser.parse_args(argv)
    picked = select(read_source(args.csv))
    if len(picked) < TOTAL:
        raise SystemExit(f"only {len(picked)} reports matched; expected {TOTAL}")
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "url", "vuln_type", "program", "upvotes", "bounty", "valid"])
        for row in sorted(picked, key=lambda r: int(report_id(r["link"]))):
            rid = report_id(row["link"])
            writer.writerow([rid, f"https://hackerone.com/reports/{rid}", row["vuln_type"],
                             row["program"], row["upvotes"], row["bounty"], "true"])
    print(f"wrote {len(picked)} report ids to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
