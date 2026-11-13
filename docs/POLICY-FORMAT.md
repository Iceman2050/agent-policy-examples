# The policy format

Each policy is one JSON file. The format is deliberately small — it exists
so the examples are readable and runnable, not to compete with production
policy languages (Rego, Cedar, and friends do that job properly).

## Fields

| Field | Meaning |
|---|---|
| `id` | Stable policy identifier; fixture cases reference it. |
| `version` | The policy's own version. Policies are versioned so a verdict can always be traced to the exact rules that produced it. |
| `title`, `description` | What the policy governs and why, in plain language. |
| `applies_to` | Action types this policy governs. Evaluating any other action type is an error (`PolicyNotApplicable`), never a silent allow. |
| `rules` | Ordered rule list. **First match wins.** |
| `fallback` | Verdict when no rule matches. Every shipped policy falls back to `DENY`. |
| `fallback_reason` | Why the fallback exists. |

## Rules

```json
{"id": "over-5-requires-approval", "verdict": "REQUIRE_APPROVAL",
 "reason": "Refunds over $5 require human approval before they are issued.",
 "when": [{"field": "amount_usd", "op": "gt", "value": 5}]}
```

- `verdict` is one of `ALLOW`, `DENY`, `REQUIRE_APPROVAL`.
- `reason` is mandatory and is what the runner prints: a verdict you cannot
  explain is a verdict you cannot defend.
- `when` is a list of conditions; **all** must hold for the rule to match.
  An empty `when` matches everything (a catch-all — the shipped policies
  use the fallback for that instead).

## Conditions

```json
{"field": "projected_daily_total_usd", "op": "gt", "value": 20}
{"field": "projected_task_total_usd", "op": "gt", "value_field": "task_budget_usd"}
```

- `field` is looked up in the evaluation context: the action's fields
  merged with the case context, plus two computed fields —
  `projected_daily_total_usd` (`daily_spent_usd` + `amount_usd`) and
  `projected_task_total_usd` (`task_spent_usd` + `amount_usd`). Computed
  fields never override a field supplied explicitly.
- `op` is one of `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in`.
- Exactly one of `value` (a literal) or `value_field` (compare against
  another context field) must be present. `value_field` is how a limit
  stated by the task itself — like a spend envelope's budget — becomes the
  rule's threshold instead of a number hard-coded in the policy.
- A condition on a missing field does not match, except `ne` / `not_in`
  (absent counts as "not equal"). The shipped policies avoid relying on
  that: they test explicit `eq: false` flags and let unstated state fall
  through to the `DENY` fallback, and their fixtures always say which
  behaviour they are pinning.

## Ordering is semantics

Rule order is part of the policy, not an implementation detail. The
refunds policy lists its daily-cap denial **before** its approval rule so
a $25 refund is denied (the cap is hard) instead of queued for approval
(the cap would then be advisory). The database policy lists its audit-log
allow **before** its generic production-write gate so the audit trail
itself is never gated. When you adapt a policy, re-check every case after
any reorder — the fixture runner asserts the deciding rule as well as the
verdict, precisely so an ordering change cannot silently change meaning.

## Writing your own

1. Copy the closest policy in `policies/v1/` and change the ids.
2. State the hard limits first (denials that no approval can override),
   then approval gates, then allows.
3. Add fixture cases for every rule, plus the boundary on each side of
   every threshold, plus one case that falls through to the fallback.
4. Run `python -m policy_examples your-cases.json --policies your-dir`
   and `python -m unittest discover -s tests -v`.
