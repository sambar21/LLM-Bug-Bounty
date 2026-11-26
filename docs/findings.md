# Findings: prompt injection against an LLM bug bounty triager

Format: remediation report. Numbers come from `results/summary.json` after a real run.
Sections marked TODO are for the author to write.

## Summary

TODO. Two or three sentences.
- Which defense lowered attack success the most for each judge, and by how many points?
- What did that cost in clean precision and recall?
- Is the difference between defenses larger than the Wilson intervals?

## Impact

TODO.
- At baseline, what fraction of attacked fakes were approved, and what is the illustrative payout leaked?
- Which single technique worked best, and on which model?
- What would this mean for a program that auto-closes or auto-escalates on the triager's verdict?

## Reproduction

All paths are in this repo. Commands assume `GROQ_API_KEY` is set in `.env`.

1. Real reports. `scripts/select_real.py` reads a pinned copy of reddelexc/hackerone-reports
   `data.csv`, keeps rows with a bounty and one of 14 web vuln types, skips the ids in
   `EXCLUDED` (summary-only or removed), and takes at most 3 per type by upvotes to get 25.
   `scripts/fetch_real.py` downloads `hackerone.com/reports/<id>.json`, keeps title,
   `vulnerability_information` (cut to 2,500 characters plus `[truncated]`) and severity.
2. Fake reports. `data/fakes/01.md` to `25.md`, ten invalid patterns, each out of scope under
   `policy/policy.md`.
3. Attacks. `scripts/make_attacked.py` applies each function in `triage/attacks.py`
   (`override`, `authority`, `hidden`, `fake_evidence`, `severity_anchor`, `poc_comment`)
   to each fake.
   Placement comes from `choose_placement(report_id, attack)`, a `random.Random` seeded on
   both, and is written to front matter.
4. Defenses, in `triage/defenses.py`:
   - `baseline`: `JUDGE_SYSTEM` (policy plus output schema) as the system turn, raw report as
     the user turn.
   - `spotlight`: report between `<<REPORT>>` markers, spaces replaced with `^`, and
     `SPOTLIGHT_NOTE` explaining both.
   - `quarantine`: the extractor model gets `EXTRACTOR_SYSTEM` and the raw report and must
     return five fields, parsed by `parse_extraction`, which rejects any extra key. The judge
     gets `JUDGE_SYSTEM` plus `QUARANTINE_NOTE` and the extracted JSON only.
   - `guard`: the report is split by `chunk()` into 1,500-character windows overlapping by
     600, each scored by Prompt Guard 2 86M. Any score above 0.5 rejects the report;
     otherwise the cached baseline verdict is reused.
   - `cross-check` (in `triage/metrics.py`, `cross_check_rows`): approves only when both
     judges approved under the same defense; a disagreement counts as sent to human review.
   - `keyword-baseline` (`keyword_baseline` in `triage/defenses.py`): no model, a reference
     point for what the LLM adds.
5. Every judge reply goes through `parse_verdict`. A failure gets one retry with the parse
   error appended; a second failure is recorded as `parse_failure` and counted as not approved.
6. `python -m triage.run` runs the grid in the order baseline, guard, quarantine, spotlight,
   caching each call in `results/cache.jsonl` under sha256 of model, defense and prompt.
   `python -m triage.report` writes the summary, table and heatmap.

To rerun one cell: `python -m triage.run --models b --defenses quarantine --limit 5`.

## Fix

The fix tested here is quarantine: the model that reads attacker-controlled text cannot
decide validity or severity, and the model that decides never reads attacker-controlled
text verbatim. Spotlighting and an injection classifier are measured as cheaper
alternatives.

## Fix verification

See `results/table.md` and `results/heatmap.png`. Compare each defense's ASR and attack lift
against baseline for the same judge, and check that clean precision and recall stay within
the baseline's interval. `tests/test_defenses.py` asserts that a canary string in the raw
report never reaches the quarantine judge's prompt.

## Where it still fails

TODO.
- Does `fake_evidence` survive quarantine? The extractor is asked to summarise evidence, so
  does it faithfully copy the fabricated log into `evidence_summary`, and does the judge
  then trust it?
- Which attacks does the classifier miss, and why? Prompt Guard looks for instruction-like
  text; authority notes and fake logs contain no instructions.
- Does placement (top, middle, end) change success rates?
- How many attacks does the cross-check stop, and how much human review does it cost?
- Does the LLM beat the keyword baseline on clean precision and recall by more than the
  interval widths?

## Limitations

TODO.
- Is n=25 per group enough to rank defenses, given the interval widths?
- The fakes and attacks are written by one person; how would results change with real
  low-quality submissions or adaptive attackers who see the defense?
- Real reports are truncated to 2,500 characters, which may hide evidence and lower recall.
- What would a real program need beyond this: human review of every approval, evidence
  that is actually reproduced, and monitoring for payout anomalies?
