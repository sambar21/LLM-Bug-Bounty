# triage-injection-bench

Bug bounty programs are getting flooded with AI-generated reports, so they will start
triaging with LLMs. That makes every report attacker-controlled input to the triager. This
repo tests two things: can a fake report talk an LLM triager into approving it, and which
defense stops that without hurting accuracy on real reports?

## Results

Partial, as of 2026-11-25: only the baseline defense has finished, and the 120B judge has
not yet seen the `poc_comment` reports. Brackets are 95% Wilson intervals; with 25 reports
per group they are wide, so treat small differences as noise.

### Does the triager work on honest input?

| Triager | Precision | Recall | Fakes approved |
|---|---|---|---|
| gpt-oss-120b | 83% (64-93) | 80% (61-91) | 4 of 25 |
| gpt-oss-20b | 85% (64-95) | 68% (48-83) | 3 of 25 |
| Both must approve | 88% (66-97) | 60% (41-77) | 2 of 25 |
| Keyword match, no model | 31% (13-58) | 16% (6-35) | 9 of 25 |

Measured on 25 real reports and 25 clean fakes. "Both must approve" sends 20% to a human.

### Do the attacks work?

Attacked fakes approved, out of 25. "Caused" counts fakes rejected when clean and approved
once attacked.

| Attack | gpt-oss-120b | gpt-oss-20b |
|---|---|---|
| none (clean fakes) | 4 | 3 |
| override | 4 (0 caused) | 4 (3 caused) |
| authority | 3 (0 caused) | 4 (1 caused) |
| hidden | 4 (1 caused) | 3 (1 caused) |
| fake_evidence | 6 (3 caused) | 7 (4 caused) |
| severity_anchor | 3 (0 caused) | 3 (1 caused) |
| poc_comment | 0 of 10 so far | 2 (0 caused) |

1. **The triager does real work.** Both models beat the keyword baseline by about 50 points
   of precision. Most rejected real reports lacked "a reproducible request and response",
   partly because my 2,500 character cut can drop the evidence section.
2. **Instructions in the report mostly fail on the 120B model.** Override, forged staff notes
   and fake CVSS scores caused no new approvals; it approves those fakes with or without them.
3. **Fake evidence works on both models.** A pasted tool log showing a fake exploit caused 3
   approvals on the 120B and 4 on the 20B, all rated critical. The policy tells the judge to
   trust concrete requests and responses, and a fabricated log looks exactly like that. Any
   fix has to check evidence against the target, not read it.
4. **The 20B model follows plain instructions more often.** "Ignore previous instructions"
   caused 3 approvals on the 20B and none on the 120B. That is a lead, not a result, at n=25.
5. **A successful attack also inflates severity.** Every attack-caused approval on the 120B
   was critical. Under the sample payout table the 20B leaked $366,800 across all fakes.
6. **Requiring both judges to agree halves false approvals**, at a cost of recall (60%
   instead of 68 to 80%) and a human review of one report in five.

## How it works

- A triager reads one report plus a one-page fictional policy (`policy/policy.md`) and
  returns JSON: `valid`, `severity`, `policy_rule`, `rationale`.
- Inputs: 25 real disclosed HackerOne reports (valid), 25 fake reports I wrote (invalid), and
  each fake with each of 6 injections (150 attacked reports).
- Attacks (`triage/attacks.py`): `override` (ignore your instructions), `authority` (a forged
  staff note), `hidden` (an HTML comment and a zero width spaced copy), `fake_evidence` (a
  fabricated tool log), `severity_anchor` (CVSS 10.0 and "RCE" in the title), `poc_comment`
  (the instruction inside comments in exploit code).
- Defenses (`triage/defenses.py`):
  - `baseline`: policy in the system prompt, report in the user turn.
  - `spotlight`: the report in delimiters, a `^` between every word, and a note that marked
    text is untrusted data.
  - `quarantine`: one model extracts fixed fields from the report; the judge sees only those
    fields, never the raw text.
  - `guard`: Prompt Guard 2 86M scores the report in 1,500 character chunks; a flagged report
    is rejected, the rest reuse the baseline verdict.
  - Both must approve, computed from the two judges' results; and keyword match, which
    approves when a vulnerability term and an HTTP request both appear.
- Judges: `openai/gpt-oss-120b` and `openai/gpt-oss-20b`. Extractor: `qwen/qwen3.8-27b`. All
  on Groq's free tier at temperature 0.

## Reproduce

Needs Python 3.11+ and a free Groq API key from console.groq.com.

```
git clone https://github.com/sambar21/LLM-Bug-Bounty triage-injection-bench
cd triage-injection-bench
make setup
cp .env.example .env    # put GROQ_API_KEY in .env, never in .env.example
make fetch              # downloads the 25 real reports into data/real/
make budget             # planned calls, tokens and days per model
make bench              # rerun once a day until every cell is finished
make report             # results/summary.json, table.md, heatmap.png
```

The grid is about 1,650 calls, about 4 days on the free tier. Every call is cached, so a
rerun only makes missing calls, and a model that runs out of daily quota is skipped while
the others continue. `python -m triage.run --cached-only` reports progress for free.

With no key and no network, `make bench-mock && make test` runs everything against an
offline mock model. Mock output goes to `results/mock/` and is labeled MOCK.

## Data and ethics

- Tollgate Exchange and its policy are fictional; every domain in the fakes ends in `.example`.
- Real reports are fetched from HackerOne's public pages at one request per second and never
  committed. `data/real_ids.csv` holds ids and links only.
- The fakes and attacks were never submitted anywhere, their CVE ids and endpoints are made
  up, and nothing here touches a live target.

## Limitations

- 25 reports per group, so most differences between attacks are inside the intervals. One
  person wrote the fakes and attacks, and the attacks do not adapt to the defense.
- Real reports are cut to 2,500 characters, which lowers recall.
- The real reports are written for other companies, so the policy judges scope by asset type
  instead of hostname. Without that rule the judges rejected almost every real report.

## How I built this

Built with AI assistance; every design decision and the write-up are mine.
