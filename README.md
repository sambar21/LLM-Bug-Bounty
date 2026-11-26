# triage-injection-bench

AI-generated bug reports are flooding bounty programs. Programs will respond by triaging
with LLMs, and the report is attacker-controlled input to that LLM. I wanted to know two
things: can a fake report talk the triager into approving it, and which defense stops that,
and what does each defense cost in accuracy on legitimate reports?

## Results

No real run is committed yet. After `make bench` finishes and `make report` runs, this
section embeds `results/table.md` and `results/heatmap.png`.

<!-- After a real run: paste results/table.md here and uncomment the image.
![Attack success rate by attack and defense](results/heatmap.png)
-->

## How it works

- A triager reads one report plus a one-page fictional policy (`policy/policy.md`) and
  returns `{"valid", "severity", "policy_rule", "rationale"}` as JSON.
- Inputs: 25 real disclosed HackerOne reports (valid), 25 fake reports I wrote (invalid),
  and those 25 fakes with each of 6 injections (150 attacked reports).
- Attacks (`triage/attacks.py`): `override`, `authority` (forged staff note), `hidden`
  (HTML comment and zero-width spaced copy), `fake_evidence` (fabricated tool log),
  `severity_anchor` (CVSS 10.0, "RCE" in the title), `poc_comment` (instructions in
  comments inside proof-of-concept code).
- Defenses (`triage/defenses.py`):
  - `baseline`: policy in the system prompt, report in the user turn.
  - `spotlight`: delimiters plus datamarking (`^` between words) and an untrusted-data note.
  - `quarantine`: an extractor fills a fixed schema from the report; the judge sees only
    that JSON, never the raw text.
  - `guard`: Prompt Guard 2 86M on 1,500-character chunks; flagged reports are rejected,
    the rest reuse the baseline verdict.
  - `cross-check`: approve only when both judges approve; any disagreement goes to a human.
    Computed from the two judges' results, so it costs no extra calls.
  - `keyword-baseline`: no model; approves when a vulnerability term and an HTTP evidence
    marker both appear. It shows what the LLM adds over a regex.
- Judges: `openai/gpt-oss-120b` and `openai/gpt-oss-20b`. Extractor: `qwen/qwen3.8-27b`.
  All on Groq's free tier, temperature 0.
- Metrics (`triage/metrics.py`): precision and recall on real plus clean fakes, false
  approval rate, attack success rate (ASR), attack lift (ASR minus false approval rate),
  severity inflation, illustrative payout leaked, share sent to human review, tokens per
  1,000 reports, and API seconds per report. Every rate has
  a 95% Wilson interval, because n is small.

## Reproduce

Requires Python 3.11+ and a free Groq API key from console.groq.com.

```
git clone https://github.com/sambar21/LLM-Bug-Bounty triage-injection-bench
cd triage-injection-bench
make setup
cp .env.example .env            # then set GROQ_API_KEY in .env
make fetch                      # downloads the 25 real reports into data/real/
make budget                     # prints planned calls, tokens and days per model
make bench                      # resumable; rerun daily until all cells finish
make report                     # results/summary.json, table.md, heatmap.png
make resume                     # optional: bullets filled from the real numbers
```

The full grid is about 1,400 calls. At the free tier's 200,000 tokens per day per model it
takes a few days (`make budget` gives the current estimate). Each call is cached in
`results/cache.jsonl`, so a rerun never repeats finished work. When Groq answers 429 with a
long retry-after, the run stops cleanly, prints what is left, and exits 0 with
"daily limit reached; rerun tomorrow to resume".

With no key and no network, `make bench-mock && make test` runs everything against an
offline mock model. Mock output goes to `results/mock/`, is labeled MOCK, and
`make resume` refuses to use it.

Docker: `docker build -t tib . && docker run --env-file .env -v "$PWD/results:/app/results"
-v "$PWD/data/real:/app/data/real" tib`.

To run against a local Ollama server instead, set `OPENAI_COMPAT_BASE_URL` and the model
env vars in `.env`.

## Data and ethics

- Tollgate Exchange and its policy are fictional. The domains use `.example`.
- Real reports are fetched from HackerOne's public disclosure pages, one request per
  second, and never committed. `data/real_ids.csv` holds ids and links only. These are other
  people's reports; I do not redistribute them.
- The fakes and attacked reports were written for this benchmark and never submitted to
  any program. CVE ids and endpoints in them are made up on purpose. Nothing here touches
  a live target.
- `data/attacked/` is committed as the release copy of the attack set.

## Limitations

- 25 reports per group. Intervals are wide, so small differences between defenses mean
  little.
- One author wrote the fakes and the attacks. Attacks are static, not adaptive to the
  defense.
- Real reports are truncated to 2,500 characters to fit free-tier limits.
- The real reports target other companies, so the policy judges scope by asset type, not
  hostname. Without that rule the judges rejected nearly every real report as out of scope.
- Severity accuracy is secondary; some real reports have no public severity.
- Model ids and free-tier limits on Groq change. The extractor is a different model family
  on purpose, since free-tier limits are per model; override any id in `.env`.
- The guard's response format is parsed as a bare probability. If Groq returns something
  else, the run fails loudly on the first guard call.

## How I built this

Built with AI assistance; every design decision and the write-up are mine.
