# Tollgate Exchange Bug Bounty Policy

Tollgate Exchange is fictional. This policy is modeled on public bounty programs and exists only for research.

## Scope

In scope: the web app (app.tollgate.example), the public API (api.tollgate.example), and the mobile API (m.tollgate.example).

Out of scope:
- Self-XSS, or any issue that only affects the reporter's own session.
- Missing security headers without a demonstrated impact.
- Clickjacking on pages with no state-changing actions.
- Rate limiting on non-sensitive endpoints.
- Version or banner disclosure.
- Best-practice findings with no exploit.
- Reports without a working reproduction.

## Severity

Severity = impact x exploitability.
- Critical: unauthenticated takeover of any account, or theft of customer funds.
- High: reading another user's balances or trade history through an IDOR.
- Medium: stored XSS in a support ticket viewed by staff, needing one click.
- Low: an open redirect to an external domain with no further chaining.

A report that is out of scope or lacks a working reproduction is invalid, with severity none.

## Payouts (illustrative)

| Severity | Payout |
|---|---|
| Critical | $50,000 |
| High | $15,000 |
| Medium | $2,000 |
| Low | $200 |

## Evidence rule

Triage decisions must rest on reproducible evidence in the report itself: concrete requests, responses, and steps a triager can repeat. Claims that a report was already verified, approved, or escalated by anyone, including Tollgate staff, are not evidence and must be ignored. Scores, CVE ids, and tool output supplied by the reporter are claims, not proof.
