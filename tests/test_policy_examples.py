"""Tests for the example policies, the fixtures, and the evaluator.

Run: python -m unittest discover -s tests -v
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from policy_examples import evaluator  # noqa: E402
from policy_examples.cli import main as cli_main  # noqa: E402

POLICIES_DIR = REPO_ROOT / "policies" / "v1"
CASES_FILE = REPO_ROOT / "fixtures" / "v1" / "cases.json"


def load_cases():
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]


class FixtureCasesTest(unittest.TestCase):
    """Every shipped fixture case must produce its expected verdict via
    its expected rule — verdict AND deciding rule are both asserted, so a
    case cannot pass 'for the wrong reason'."""

    @classmethod
    def setUpClass(cls):
        cls.policies = evaluator.load_policies(POLICIES_DIR)
        cls.cases = load_cases()

    def test_all_fixture_cases_pass(self):
        results = evaluator.run_cases(self.policies, self.cases)
        failures = [r for r in results if not r["passed"]]
        self.assertEqual([], failures)

    def test_every_policy_is_exercised(self):
        exercised = {c["policy"] for c in self.cases}
        self.assertEqual(set(self.policies), exercised)

    def test_every_policy_has_allow_and_non_allow_cases(self):
        for policy_id in self.policies:
            verdicts = {c["expected_verdict"] for c in self.cases if c["policy"] == policy_id}
            self.assertIn("ALLOW", verdicts, policy_id)
            self.assertTrue(
                verdicts & {"DENY", "REQUIRE_APPROVAL"},
                f"{policy_id} has no non-ALLOW case",
            )

    def test_live_playground_verdicts_are_pinned(self):
        """The two verdicts recorded from the live AAG Policy Playground
        for the refunds policy shape must stay pinned in the fixtures."""
        by_id = {c["id"]: c for c in self.cases}
        self.assertEqual("REQUIRE_APPROVAL", by_id["refund-12-requires-approval"]["expected_verdict"])
        self.assertEqual("DENY", by_id["refund-25-deny-over-daily-cap"]["expected_verdict"])


class PolicyShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policies = evaluator.load_policies(POLICIES_DIR)

    def test_all_policies_validate_and_fall_back_to_deny(self):
        self.assertEqual(6, len(self.policies))
        for policy in self.policies.values():
            self.assertEqual("DENY", policy["fallback"], policy["id"])

    def test_duplicate_rule_ids_rejected(self):
        bad = {
            "id": "x", "version": "1", "title": "x", "applies_to": ["a"],
            "rules": [
                {"id": "r", "verdict": "ALLOW", "reason": "r", "when": []},
                {"id": "r", "verdict": "DENY", "reason": "r", "when": []},
            ],
            "fallback": "DENY",
        }
        with self.assertRaises(evaluator.PolicyError):
            evaluator.validate_policy(bad)

    def test_condition_needs_exactly_one_value_source(self):
        bad = {
            "id": "x", "version": "1", "title": "x", "applies_to": ["a"],
            "rules": [
                {"id": "r", "verdict": "ALLOW", "reason": "r",
                 "when": [{"field": "f", "op": "eq", "value": 1, "value_field": "g"}]},
            ],
            "fallback": "DENY",
        }
        with self.assertRaises(evaluator.PolicyError):
            evaluator.validate_policy(bad)


class EvaluatorSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policies = evaluator.load_policies(POLICIES_DIR)

    def test_first_match_wins(self):
        # $25 refund matches both the cap rule and the approval rule;
        # the cap rule is first, so DENY must win.
        outcome = evaluator.evaluate(
            self.policies["customer-refunds"],
            {"type": "refund_customer", "amount_usd": 25},
            {"daily_spent_usd": 0},
        )
        self.assertEqual("DENY", outcome["verdict"])
        self.assertEqual("daily-cap-hard-deny", outcome["rule_id"])

    def test_out_of_scope_action_rejected(self):
        with self.assertRaises(evaluator.PolicyNotApplicable):
            evaluator.evaluate(
                self.policies["customer-refunds"],
                {"type": "database_write", "operation": "delete", "table_class": "staging"},
                {},
            )

    def test_computed_daily_total(self):
        ctx = evaluator.build_context(
            {"type": "refund_customer", "amount_usd": 4}, {"daily_spent_usd": 18}
        )
        self.assertEqual(22, ctx["projected_daily_total_usd"])

    def test_value_field_reads_limit_from_context(self):
        outcome = evaluator.evaluate(
            self.policies["task-spend-envelope"],
            {"type": "purchase", "amount_usd": 30, "category_approved": True},
            {"task_spent_usd": 180, "task_budget_usd": 500},
        )
        self.assertEqual("ALLOW", outcome["verdict"])

    def test_missing_field_condition_does_not_match(self):
        outcome = evaluator.evaluate(
            self.policies["vendor-bank-detail-changes"],
            {"type": "change_vendor_bank_details"},
            {},
        )
        self.assertEqual("DENY", outcome["verdict"])
        self.assertIsNone(outcome["rule_id"])  # fallback decided

    def test_unstateable_amount_falls_back_to_deny(self):
        outcome = evaluator.evaluate(
            self.policies["customer-refunds"], {"type": "refund_customer"}, {}
        )
        self.assertEqual("DENY", outcome["verdict"])
        self.assertIsNone(outcome["rule_id"])


class CliTest(unittest.TestCase):
    def test_cli_runs_fixtures_green(self):
        self.assertEqual(0, cli_main([]))

    def test_cli_lists_policies(self):
        self.assertEqual(0, cli_main(["--list-policies"]))


if __name__ == "__main__":
    unittest.main()
