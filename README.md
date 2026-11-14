# agent-policy-examples

Testable authorization policies for AI agents: six versioned policy files,
26 test actions with expected verdicts, and a small runner that checks the
policies actually produce the verdicts they claim.

## The problem

When a team gives an AI agent the ability to refund a customer, pay a
vendor, change bank details or write to a database, the authorization rules
usually live in prose — a wiki page, a prompt, a manager's head. Prose
cannot be tested. Nobody can answer "what would the agent do with a $25
refund?" without either trusting the prose or watching it happen.

This repo makes the rules executable examples instead: each policy is a
small machine-readable file with ordered rules, every rule carries the
human-readable reason for its verdict, and every policy ships with fixture
actions whose expected verdict — and expected deciding rule — are pinned
in advance. Change a threshold or reorder the rules and the test suite
tells you exactly which behaviours changed.

## Verdict honesty — read this first

- **These are examples plus a reference evaluator, not a production
  authorization engine.** There is no authentication, no tenant isolation,
  no persistence, no approval workflow, no audit log, and no deployment
  hardening here. Do not put this evaluator in front of real money or real
  data and call the result "authorized". Production enforcement is what
  [Agent Auth Gateway](https://authgateway.getingeniousai.com) and
  [MandateGuard](https://mandateguard.getingeniousai.com) are built for;
  this repo is the readable, runnable front end of the same ideas.
- The evaluator trusts its inputs. `verified_callback_completed: true` in
  a fixture means "the case assumes a callback was verified" — nothing in
  this repo performs or checks a callback, a payment, or a database write.
- An `ALLOW` verdict means "these example rules, applied to this stated
  action and context, produce allow". It is a statement about the policy
  text, not about your organisation's risk.
- Two verdicts are pinned from a live system: for the refunds policy
  shape, the Agent Auth Gateway Policy Playground returns
  **REQUIRE_APPROVAL for a $12 refund** and **DENY for a $25 refund**
  (over the $20/day cap). Those two cases are in the fixtures by name, so
  the example cannot drift away from the behaviour it documents.

## The six policies (v1)

| Policy | Governs | The shape of the rules |
|---|---|---|
| `customer-refunds` | `refund_customer` | ≤ $5 auto-allow · > $5 needs approval · projected daily total > $20 **denied** (hard cap, checked first) |
| `outbound-payments` | `issue_payment`, `pay_invoice` | Approved vendor ≤ $100 auto-pay · > $100 approval · unapproved vendor always approval · > $500 **denied** (mandate max) |
| `vendor-bank-detail-changes` | `change_vendor_bank_details` | No verified callback → **deny** · callback done, second approver pending → approval · both done → allow |
| `high-risk-database-writes` | `database_write` | Billing-table deletes **denied outright** · other production deletes/updates → approval · audit-log inserts allowed · non-production open · unclassified → deny |
| `task-spend-envelope` | `purchase`, `book_service`, `pay_invoice` | Projected task total over the task's own stated budget → **deny** · unapproved category → approval · single action > $50 → approval · small in-envelope → allow |
| `retry-and-repeat-actions` | `retry_action`, `repeat_action`, `replay_action` | Attempt > 3 **denied** (retry ceiling) · repeat of a non-idempotent action **denied** (reconcile first, never auto-replay) · repeat of a sensitive action → fresh approval · proven-idempotent attempt ≤ 3 → allow |

Every policy falls back to `DENY` when no rule matches. The full format —
fields, condition operators, and why rule order is part of the meaning —
is documented in [docs/POLICY-FORMAT.md](docs/POLICY-FORMAT.md).

## How a verdict is decided

1. The policy must list the action's type in `applies_to`; anything else
   is an error, never a silent allow.
2. Rules are tried **in file order; the first rule whose conditions all
   hold decides**. Ordering is semantics: the refunds cap rule precedes
   the approval rule so a $25 refund is denied instead of queued, and the
   database policy's audit-insert allow precedes its generic production
   gate so the audit trail is never gated by its own policy.
3. Conditions read a flat context (action fields + case context) plus two
   computed totals: `projected_daily_total_usd` and
   `projected_task_total_usd`. A condition may compare against a literal
   (`value`) or against another context field (`value_field`) — the spend
   envelope reads its budget from the task itself that way.

## Install and use

Python ≥ 3.9, standard library only, no network access.

```bash
git clone https://github.com/Iceman2050/agent-policy-examples
cd agent-policy-examples

python -m policy_examples                  # run all 26 fixture cases
python -m policy_examples --list-policies  # list the six policies
python -m unittest discover -s tests -v    # the full test suite

# your own cases against your own edited policies:
python -m policy_examples my-cases.json --policies my-policies/
```

Exit codes: `0` = every case produced its expected verdict via its
expected rule; `1` = at least one case did not; `2` = usage / IO / policy
error.

## Reproduce the verified result

The fixtures are versioned at `fixtures/v1/cases.json`: 26 cases covering
every rule in every policy, both sides of every threshold boundary, two
fallback cases, and the two pinned live-playground verdicts. Each case
asserts the deciding rule as well as the verdict, so a case cannot pass
"for the wrong reason".

## Actual test results

Run on 2026-11-13, Python 3.12.3, from a clean checkout of this repo:

```
$ python -m unittest discover -s tests
----------------------------------------------------------------------
Ran 15 tests in 0.005s

OK
```

```
$ python -m policy_examples
[PASS] refund-3-allow (customer-refunds): expected ALLOW via small-refund-allow, got ALLOW via small-refund-allow
[PASS] refund-5-boundary-allow (customer-refunds): expected ALLOW via small-refund-allow, got ALLOW via small-refund-allow
[PASS] refund-12-requires-approval (customer-refunds): expected REQUIRE_APPROVAL via over-5-requires-approval, got REQUIRE_APPROVAL via over-5-requires-approval
[PASS] refund-25-deny-over-daily-cap (customer-refunds): expected DENY via daily-cap-hard-deny, got DENY via daily-cap-hard-deny
[PASS] refund-4-deny-cumulative-cap (customer-refunds): expected DENY via daily-cap-hard-deny, got DENY via daily-cap-hard-deny
[PASS] refund-6-approval-at-cap-edge (customer-refunds): expected REQUIRE_APPROVAL via over-5-requires-approval, got REQUIRE_APPROVAL via over-5-requires-approval
[PASS] pay-40-approved-allow (outbound-payments): expected ALLOW via small-approved-payment-allow, got ALLOW via small-approved-payment-allow
[PASS] pay-250-approved-approval (outbound-payments): expected REQUIRE_APPROVAL via over-100-requires-approval, got REQUIRE_APPROVAL via over-100-requires-approval
[PASS] pay-30-unapproved-approval (outbound-payments): expected REQUIRE_APPROVAL via unapproved-vendor-requires-approval, got REQUIRE_APPROVAL via unapproved-vendor-requires-approval
[PASS] pay-750-approved-deny (outbound-payments): expected DENY via mandate-max-hard-deny, got DENY via mandate-max-hard-deny
[PASS] pay-600-unapproved-deny-cap-first (outbound-payments): expected DENY via mandate-max-hard-deny, got DENY via mandate-max-hard-deny
[PASS] bank-change-no-callback-deny (vendor-bank-detail-changes): expected DENY via no-callback-deny, got DENY via no-callback-deny
[PASS] bank-change-callback-pending-dual (vendor-bank-detail-changes): expected REQUIRE_APPROVAL via callback-done-dual-approval-pending, got REQUIRE_APPROVAL via callback-done-dual-approval-pending
[PASS] bank-change-fully-verified-allow (vendor-bank-detail-changes): expected ALLOW via callback-and-dual-approval-allow, got ALLOW via callback-and-dual-approval-allow
[PASS] bank-change-unstated-deny-fallback (vendor-bank-detail-changes): expected DENY via fallback, got DENY via fallback
[PASS] db-delete-billing-deny (high-risk-database-writes): expected DENY via billing-delete-hard-deny, got DENY via billing-delete-hard-deny
[PASS] db-delete-users-approval (high-risk-database-writes): expected REQUIRE_APPROVAL via production-delete-requires-approval, got REQUIRE_APPROVAL via production-delete-requires-approval
[PASS] db-update-orders-approval (high-risk-database-writes): expected REQUIRE_APPROVAL via production-write-requires-approval, got REQUIRE_APPROVAL via production-write-requires-approval
[PASS] db-insert-audit-allow (high-risk-database-writes): expected ALLOW via audit-log-insert-allow, got ALLOW via audit-log-insert-allow
[PASS] db-update-staging-allow (high-risk-database-writes): expected ALLOW via non-production-allow, got ALLOW via non-production-allow
[PASS] db-write-unclassified-deny-fallback (high-risk-database-writes): expected DENY via fallback, got DENY via fallback
[PASS] task-20-approved-allow (task-spend-envelope): expected ALLOW via in-envelope-allow, got ALLOW via in-envelope-allow
[PASS] task-80-approved-approval (task-spend-envelope): expected REQUIRE_APPROVAL via over-50-requires-approval, got REQUIRE_APPROVAL via over-50-requires-approval
[PASS] task-20-unapproved-category-approval (task-spend-envelope): expected REQUIRE_APPROVAL via unapproved-category-requires-approval, got REQUIRE_APPROVAL via unapproved-category-requires-approval
[PASS] task-30-over-envelope-deny (task-spend-envelope): expected DENY via envelope-exceeded-hard-deny, got DENY via envelope-exceeded-hard-deny
[PASS] task-budget-is-read-from-task (task-spend-envelope): expected ALLOW via in-envelope-allow, got ALLOW via in-envelope-allow
Summary: 26/26 cases passed.
```

(The runner's real output appends each rule's reason after the verdicts;
reasons are trimmed above for width. These are real outputs of the
commands shown, not illustrations.)

## Exact supported scope

- **Policies:** the six files in `policies/v1/`, in the JSON format
  documented in `docs/POLICY-FORMAT.md`. Operators: `eq`, `ne`, `lt`,
  `lte`, `gt`, `gte`, `in`, `not_in`; literal or context-field comparison
  values; two computed totals (daily, per-task).
- **Not in scope:** boolean condition combinators beyond AND-within-a-rule
  (nest rules instead), time windows beyond the caller-supplied daily/task
  totals, roles/principals, obligations (logging, notification), or policy
  combination across files. Production policy languages and gateways
  cover those; these examples deliberately do not.
- **Relationship to neighbouring work:** Agent Auth Gateway ships policy
  examples inside the product and AgentGate's guide walks through
  publishing agent policies; this repo extracts the testable core — the
  policy files plus their expected verdicts — into a standalone artifact
  you can run, fork and adapt without any account.

## Limitations

- The evaluator is a teaching and specification tool. It makes no
  security claims: inputs are trusted, nothing is authenticated, and a
  verdict is only as honest as the context the caller supplies (a caller
  that lies about `daily_spent_usd` gets a verdict for the lie).
- Thresholds ($5 / $20 / $100 / $500 / $50) are example values chosen to
  make the rule shapes legible — including the two pinned live-playground
  verdicts — not recommendations for any real organisation.
- `REQUIRE_APPROVAL` ends the evaluation. Who approves, how, and what
  happens on timeout are workflow questions this format intentionally
  leaves to the system that embeds the policy.
- Table classes, vendor lists and categories are caller-supplied labels.
  The examples cannot tell a production table from a staging one; your
  integration has to classify honestly.

## Relationship to Agent Auth Gateway and MandateGuard

[Agent Auth Gateway](https://authgateway.getingeniousai.com) evaluates
authorization decisions against connected execution paths — its Policy
Playground is where the refunds verdicts above were recorded.
[MandateGuard](https://mandateguard.getingeniousai.com) is where a
spending mandate — approved vendors, amounts, periods, approval
conditions — is defined and reviewed as one clear card. This repo is the
open, standalone companion: the same policy shapes, written down as files
you can diff, test in CI, and argue about in review before anything is
enforced anywhere.

## License

MIT. Built by Ingenious AI — https://getingeniousai.com

## Ingenious AI platforms

Built by Ingenious AI. The fleet — every platform does one job:

- [Agent Auth Gateway](https://authgateway.getingeniousai.com) · [MandateGuard](https://mandateguard.getingeniousai.com) · [Agentic Receipts](https://agentic-receipts.getingeniousai.com) · [Agent Flight Recorder](https://flightrecorder.getingeniousai.com) · [TrustGate](https://trustgate.getingeniousai.com) · [BoundaryVault](https://boundaryvault.getingeniousai.com) · [Rogue-Agent Defense](https://rogue-defense.getingeniousai.com) · [AgentGate](https://agentgate.getingeniousai.com) · [Agent Passport](https://agentpassport.getingeniousai.com) · [HomeShield](https://homeshield.getingeniousai.com) · [AgentBlock](https://agentblock.getingeniousai.com) · [ChatBreaker](https://chatbreaker.getingeniousai.com) · [EvalScope](https://evalscope.getingeniousai.com) · [CompanionGuard](https://companionguard.getingeniousai.com)
- [DomainGuard](https://domainguard.getingeniousai.com) · [BreachHunter](https://breachhunter.getingeniousai.com) · [TakedownCoop](https://takedowncoop.getingeniousai.com) · [WireWatch](https://wirewatch.getingeniousai.com) · [CallbackShield](https://callbackshield.getingeniousai.com) · [Vibe-Code Audit](https://vibe-audit.getingeniousai.com)
- [DisclosureGuard](https://disclosureguard.getingeniousai.com) · [ProvenanceGuard](https://provenanceguard.getingeniousai.com) · [ADMT](https://admt.getingeniousai.com) · [ReviewDesk](https://reviewdesk.getingeniousai.com) · [CRAClock](https://craclock.getingeniousai.com) · [AI Audit Exchange](https://auditexchange.getingeniousai.com) · [TermsWatch](https://termswatch.getingeniousai.com) · [ModelMinder](https://modelminder.getingeniousai.com) · [ReviewProof](https://reviewproof.getingeniousai.com) · [EInvoice](https://einvoice.getingeniousai.com) · [DueLadder](https://dueladder.getingeniousai.com) · [OutcomeMeter](https://outcomemeter.getingeniousai.com)
- [AgentReady](https://agentready.getingeniousai.com) · [Store Audit](https://storeaudit.getingeniousai.com) · [ContentCraft AI](https://contentcraft.getingeniousai.com) · [GEOFixer](https://geofixer.getingeniousai.com)
- Full directory: https://getingeniousai.com/platforms
