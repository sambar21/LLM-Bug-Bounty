# Findings: prompt injection against an LLM bug bounty triager

This is written as a remediation report for the team that would run the triager. Numbers
come from `results/summary.json`. Sections marked TODO are for the author to write once the
full grid has finished.

## Summary

TODO. Two or three sentences a program owner can act on.
- Which defense lowered attack success the most for each judge, and by how many points?
- What did that cost in precision and recall on honest reports?
- Is the gap between defenses larger than the Wilson intervals?

## Impact

TODO.
- At baseline, what share of attacked fakes were approved, and what is the payout leaked
  under the sample table?
- Which technique worked best, and on which model? (Baseline so far: fake evidence, on both.)
- What happens to a program that closes or escalates reports automatically on the verdict?

## Reproduction

All paths are in this repo. Commands assume `GROQ_API_KEY` is set in `.env`.

1. Real reports. `scripts/select_real.py` reads a pinned copy of `data.csv` from
   reddelexc/hackerone-reports. It keeps rows with a bounty and one of 14 web vulnerability
   types, skips the ids in `EXCLUDED` (disclosed without a report body, or removed), and takes
   the 3 most upvoted per type until it has 25. `scripts/fetch_real.py` downloads
   `hackerone.com/reports/<id>.json` and keeps the title, the report body cut to 2,500
   characters with a `[truncated]` marker, and the severity.
2. Fake reports. `data/fakes/01.md` to `25.md` cover ten invalid patterns. Each one is out of
   scope or unreproducible under `policy/policy.md`.
3. Attacks. `scripts/make_attacked.py` applies each function in `triage/attacks.py` to each
   fake: `override`, `authority`, `hidden`, `fake_evidence`, `severity_anchor`, `poc_comment`.
   `choose_placement(report_id, attack)` picks top, middle or end from a seeded
   `random.Random`, and the choice is written to the file's front matter.
4. Defenses, in `triage/defenses.py`:
   - `baseline`: `JUDGE_SYSTEM` (policy plus output schema) is the system turn and the raw
     report is the user turn.
   - `spotlight`: the report sits between `<<REPORT>>` markers with every space replaced by
     `^`, and `SPOTLIGHT_NOTE` explains both.
   - `quarantine`: the extractor gets `EXTRACTOR_SYSTEM` and the raw report and must return
     five fields. `parse_extraction` rejects any other key, so the extractor cannot set
     `valid` or `severity`. The judge gets `JUDGE_SYSTEM`, `QUARANTINE_NOTE` and the fields.
   - `guard`: `chunk()` splits the report into 1,500 character windows that overlap by 600,
     and Prompt Guard 2 86M scores each one. Code and hex strings can exceed the classifier's
     512 token limit, so `guard_score()` splits an oversized chunk in half and scores both
     halves. Any score above 0.5 rejects the report; otherwise the baseline verdict is reused.
   - Both must approve: `cross_check_rows` in `triage/metrics.py` approves only when both
     judges approved under the same defense, and counts a disagreement as a human review.
   - Keyword match: `keyword_baseline` approves when a vulnerability term and an HTTP request
     both appear. It shows what the model adds over a simple rule.
5. `parse_verdict` checks every judge reply. A failure gets one retry with the error
   appended; a second failure is recorded as `parse_failure` and counted as not approved.
6. `python -m triage.run` runs baseline, guard, quarantine, then spotlight, caching each call
   in `results/cache.jsonl` under a sha256 of model, defense and prompt.
   `python -m triage.report` writes the summary, table and heatmap.

To rerun one slice: `python -m triage.run --models b --defenses quarantine --limit 5`.

## Fix

The fix under test is quarantine. The model that reads the attacker's text cannot decide
validity or severity, and the model that decides never reads the attacker's text. Spotlight
and the injection classifier are measured as cheaper alternatives, and requiring both judges
to agree is measured as a check that needs no extra calls.

## Fix verification

Compare each defense's attack success rate and attack lift with baseline for the same judge
in `results/table.md` and `results/heatmap.png`, and check that precision and recall on
honest reports stay inside the baseline interval. `tests/test_defenses.py` asserts that a
canary string in the raw report never reaches the quarantine judge.

## Where it still fails

TODO.
- Does fake evidence survive quarantine? The extractor is asked to summarize evidence. Does
  it copy the fabricated log into `evidence_summary`, and does the judge then trust it?
- Which attacks does the classifier miss, and why? Prompt Guard looks for instructions; a
  forged staff note or a fake log contains none.
- Does placement (top, middle, end) change success rates?
- How many attacks does requiring both judges stop, and how much human review does it add?

## Limitations

TODO.
- Is n=25 per group enough to rank defenses, given the interval widths?
- One person wrote the fakes and the attacks. How would results change with real junk
  submissions, or with attackers who adapt to the defense?
- Real reports are cut to 2,500 characters, which can hide evidence and lower recall.
- What would a real program need beyond this: a human on every approval, evidence that is
  actually reproduced, and alerts on unusual payouts?
