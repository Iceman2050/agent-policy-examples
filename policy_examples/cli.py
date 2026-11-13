"""Command-line runner: evaluate fixture cases against the policies.

Usage:
    python -m policy_examples                 # run fixtures/v1/cases.json
    python -m policy_examples --list-policies
    python -m policy_examples path/to/cases.json --policies path/to/dir

Exit codes: 0 = every case produced its expected verdict via its expected
rule; 1 = at least one case did not; 2 = usage / IO / policy error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import evaluator

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = REPO_ROOT / "fixtures" / "v1" / "cases.json"
DEFAULT_POLICIES = REPO_ROOT / "policies" / "v1"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="agent-policy-examples",
        description="Run test actions against the example authorization policies.",
    )
    parser.add_argument(
        "cases",
        nargs="?",
        default=str(DEFAULT_CASES),
        help="fixture cases JSON (default: fixtures/v1/cases.json)",
    )
    parser.add_argument(
        "--policies",
        default=str(DEFAULT_POLICIES),
        help="directory of policy JSON files (default: policies/v1)",
    )
    parser.add_argument(
        "--list-policies",
        action="store_true",
        help="list the loaded policies and exit",
    )
    args = parser.parse_args(argv)

    try:
        policies = evaluator.load_policies(args.policies)
    except (OSError, ValueError) as exc:
        print(f"error loading policies: {exc}", file=sys.stderr)
        return 2

    if args.list_policies:
        for policy in policies.values():
            actions = ", ".join(policy["applies_to"])
            print(f"{policy['id']} v{policy['version']} — {policy['title']} [{actions}]")
        return 0

    try:
        cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"error loading cases: {exc}", file=sys.stderr)
        return 2

    try:
        results = evaluator.run_cases(policies, cases)
    except (ValueError, KeyError) as exc:
        print(f"error running cases: {exc}", file=sys.stderr)
        return 2

    for result in results:
        mark = "PASS" if result["passed"] else "FAIL"
        rule = result["actual_rule"] or "fallback"
        print(
            f"[{mark}] {result['case_id']} ({result['policy']}): "
            f"expected {result['expected_verdict']} via {result['expected_rule'] or 'fallback'}, "
            f"got {result['actual_verdict']} via {rule} — {result['reason']}"
        )
    passed = sum(1 for r in results if r["passed"])
    print(f"Summary: {passed}/{len(results)} cases passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
