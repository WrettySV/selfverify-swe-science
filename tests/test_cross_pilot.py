"""Regression checks for public fallback and verifier validity in the new matrix."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_cross_pilot import select_task
from run_cross_pilot import source_only


def cell(candidate, status=None, kind="blind", own=False):
    return {"suite_id": "PUBLIC_ONLY" if kind == "public" else "T1", "kind": kind,
        "candidate_id": candidate, "self": own, "applied": "ok",
        "evaluation": {"public": {"status": "pass"}, "results":
            [] if status is None else [{"path": "test_x.py", "status": status}]}}


class CrossPilotTests(unittest.TestCase):
    def test_unusable_suite_uses_public_fallback_instead_of_dropping_task(self):
        rows = [cell("p1", kind="public"), cell("p2", kind="public")]
        result = select_task(rows, [], "blind")
        self.assertEqual(result["cross"]["picked"], ["p1", "p2"])
        self.assertEqual(result["cross"]["decision"], "public_random_fallback")

    def test_runtime_baseline_changes_only_predeclared_sensitivity_policy(self):
        rows = [cell("p1", kind="public"), cell("p2", kind="public"),
                cell("BASELINE", "runtime_error"), cell("p1", "pass"), cell("p2", "assertion")]
        self.assertEqual(select_task(rows, [], "blind", True)["cross"]["picked"], ["p1", "p2"])
        self.assertEqual(select_task(rows, [], "blind", False)["cross"]["picked"], ["p1"])

    def test_donor_self_vote_is_excluded_even_with_different_suite_id(self):
        rows = [cell("p1", kind="public"), cell("p2", kind="public"),
                cell("BASELINE", "assertion", "candidate"), cell("p1", "pass", "candidate", True),
                cell("p2", "assertion", "candidate")]
        result = select_task(rows, [], "candidate")
        self.assertNotIn("p1", result["cross"]["scores"])
        self.assertIn("p2", result["cross"]["scores"])

    def test_only_source_diff_is_presented_as_candidate(self):
        source = "diff --git a/source/a.py b/source/a.py\n+fix\n"
        suite = "diff --git a/selfverify/invariants/test_x.py b/selfverify/invariants/test_x.py\n+assert x\n"
        self.assertEqual(source_only(source + suite), source)


if __name__ == "__main__":
    unittest.main()
