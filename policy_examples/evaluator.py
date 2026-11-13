"""Reference evaluator for the agent-policy-examples policy format.

Deliberately small and explicit. This is a *reference evaluator for
examples*, not a production authorization engine: no authentication, no
tenant isolation, no persistence, no audit log, no fail-closed deployment
guarantees. See the README's Limitations section.

Evaluation semantics
--------------------
- A policy applies to the action types listed in ``applies_to``. Evaluating
  an action type a policy does not list raises ``PolicyNotApplicable``.
- Rules are evaluated in file order. The FIRST rule whose conditions all
  hold decides the verdict ("first match wins"). If no rule matches, the
  policy's ``fallback`` verdict applies.
- Conditions are ``{"field": ..., "op": ..., "value": ...}`` triples over a
  flat evaluation context built from the action's fields plus the case
  context, plus two computed fields. A condition may use ``value_field``
  instead of ``value`` to compare against another context field (this is
  how the task spend envelope reads its budget from the task itself
  instead of hard-coding a number):

  - ``projected_daily_total_usd`` = context ``daily_spent_usd`` (default 0)
    + action ``amount_usd`` (default 0)
  - ``projected_task_total_usd`` = context ``task_spent_usd`` (default 0)
    + action ``amount_usd`` (default 0)

  Computed fields never override a field the caller supplied explicitly.
- Supported ops: ``eq``, ``ne``, ``lt``, ``lte``, ``gt``, ``gte``, ``in``,
  ``not_in``. A condition on a missing field never matches (except ``ne`` /
  ``not_in``, which match when the field is absent — documented so policies
  can treat "not stated" as "not satisfied" only where they say so; the
  shipped policies use explicit ``eq: false`` checks on named context
  fields instead, and their fixtures always supply those fields).
"""

from __future__ import annotations

import json
from pathlib import Path

VERDICTS = ("ALLOW", "DENY", "REQUIRE_APPROVAL")
OPS = ("eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in")


class PolicyError(ValueError):
    """Raised when a policy file is malformed."""


class PolicyNotApplicable(PolicyError):
    """Raised when a policy does not govern the action's type."""


def load_policy(path):
    """Load and validate one policy JSON file. Returns the policy dict."""
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_policy(policy, source=str(path))
    return policy


def validate_policy(policy, source="policy"):
    required = ("id", "version", "title", "applies_to", "rules", "fallback")
    for key in required:
        if key not in policy:
            raise PolicyError(f"{source}: missing required field {key!r}")
    if policy["fallback"] not in VERDICTS:
        raise PolicyError(f"{source}: fallback {policy['fallback']!r} not a verdict")
    seen_rule_ids = set()
    for rule in policy["rules"]:
        for key in ("id", "verdict", "reason"):
            if key not in rule:
                raise PolicyError(f"{source}: rule missing {key!r}: {rule!r}")
        if rule["id"] in seen_rule_ids:
            raise PolicyError(f"{source}: duplicate rule id {rule['id']!r}")
        seen_rule_ids.add(rule["id"])
        if rule["verdict"] not in VERDICTS:
            raise PolicyError(f"{source}: rule {rule['id']!r} verdict not valid")
        for cond in rule.get("when", []):
            for key in ("field", "op"):
                if key not in cond:
                    raise PolicyError(f"{source}: condition missing {key!r}: {cond!r}")
            if ("value" in cond) == ("value_field" in cond):
                raise PolicyError(
                    f"{source}: condition needs exactly one of 'value' / "
                    f"'value_field': {cond!r}"
                )
            if cond["op"] not in OPS:
                raise PolicyError(f"{source}: unsupported op {cond['op']!r}")
    return policy


def load_policies(directory):
    """Load every ``*.json`` policy in a directory, keyed by policy id."""
    policies = {}
    for path in sorted(Path(directory).glob("*.json")):
        policy = load_policy(path)
        if policy["id"] in policies:
            raise PolicyError(f"duplicate policy id {policy['id']!r}")
        policies[policy["id"]] = policy
    return policies


def build_context(action, context):
    """Merge action fields + case context and add computed totals."""
    merged = dict(context or {})
    merged.update(action or {})
    amount = merged.get("amount_usd", 0) or 0
    if "projected_daily_total_usd" not in merged:
        merged["projected_daily_total_usd"] = (merged.get("daily_spent_usd", 0) or 0) + amount
    if "projected_task_total_usd" not in merged:
        merged["projected_task_total_usd"] = (merged.get("task_spent_usd", 0) or 0) + amount
    return merged


def _condition_holds(cond, ctx):
    field, op = cond["field"], cond["op"]
    if "value_field" in cond:
        if cond["value_field"] not in ctx:
            return False
        expected = ctx[cond["value_field"]]
    else:
        expected = cond["value"]
    present = field in ctx
    actual = ctx.get(field)
    if op == "eq":
        return present and actual == expected
    if op == "ne":
        return not present or actual != expected
    if op == "in":
        return present and actual in expected
    if op == "not_in":
        return not present or actual not in expected
    if not present or actual is None:
        return False
    try:
        if op == "lt":
            return actual < expected
        if op == "lte":
            return actual <= expected
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
    except TypeError:
        return False
    raise PolicyError(f"unsupported op {op!r}")


def evaluate(policy, action, context=None):
    """Evaluate one action against one policy.

    Returns ``{"verdict", "rule_id", "reason", "policy_id",
    "policy_version"}``. ``rule_id`` is ``None`` when the fallback decided.
    """
    action_type = (action or {}).get("type")
    if action_type not in policy["applies_to"]:
        raise PolicyNotApplicable(
            f"policy {policy['id']!r} does not apply to action type {action_type!r}"
        )
    ctx = build_context(action, context)
    for rule in policy["rules"]:
        if all(_condition_holds(cond, ctx) for cond in rule.get("when", [])):
            return {
                "verdict": rule["verdict"],
                "rule_id": rule["id"],
                "reason": rule["reason"],
                "policy_id": policy["id"],
                "policy_version": policy["version"],
            }
    return {
        "verdict": policy["fallback"],
        "rule_id": None,
        "reason": policy.get(
            "fallback_reason", "No rule matched; the policy fallback applies."
        ),
        "policy_id": policy["id"],
        "policy_version": policy["version"],
    }


def run_cases(policies, cases):
    """Run fixture cases against loaded policies.

    Each case: ``{"id", "policy", "action", "context", "expected_verdict",
    "expected_rule"}``. Returns a list of result dicts with ``passed``.
    """
    results = []
    for case in cases:
        policy = policies[case["policy"]]
        outcome = evaluate(policy, case["action"], case.get("context"))
        passed = (
            outcome["verdict"] == case["expected_verdict"]
            and outcome["rule_id"] == case.get("expected_rule")
        )
        results.append(
            {
                "case_id": case["id"],
                "policy": case["policy"],
                "expected_verdict": case["expected_verdict"],
                "actual_verdict": outcome["verdict"],
                "expected_rule": case.get("expected_rule"),
                "actual_rule": outcome["rule_id"],
                "reason": outcome["reason"],
                "passed": passed,
            }
        )
    return results
