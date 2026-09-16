"""Check the audit's research-critical boundary: hidden labels cannot choose patches."""
import copy
import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[1] / "scripts/cross_candidate_audit.py"
spec = importlib.util.spec_from_file_location("cross_candidate_audit", path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def cell(candidate, reward, passed, failure_class="assertion"):
    return {
        "suite_trial": "donor", "cand_trial": candidate, "cand_reward": reward,
        "self": False, "applied": "ok", "public_rc": 0,
        "results": [{"passed": passed, "failure_class": "pass" if passed else failure_class}],
    }


class CrossCandidateAuditTest(unittest.TestCase):
    def test_hidden_label_flip_changes_score_but_never_selection(self):
        matrix = {"001": {
            "base": cell("BASELINE", None, False),
            "p1": cell("p1", 1, True), "p2": cell("p2", 0, False),
        }}
        flipped = copy.deepcopy(matrix)
        for row in flipped["001"].values():
            if row["cand_trial"] != "BASELINE":
                row["cand_reward"] = 1 - row["cand_reward"]
        a, b = audit.audit(matrix), audit.audit(flipped)
        for method in audit.METHODS:
            self.assertEqual(a["per_task"]["001"]["methods"][method]["picked"],
                             b["per_task"]["001"]["methods"][method]["picked"])
        self.assertEqual(a["macro_expected_reward"]["cross_vote"], 1)
        self.assertEqual(b["macro_expected_reward"]["cross_vote"], 0)

    def test_runtime_ambiguity_causes_strict_abstention(self):
        rows = audit.observations([cell("BASELINE", None, False, "runtime_error"),
                                   cell("p1", 1, True), cell("p2", 0, False)])
        self.assertEqual(audit.choose(rows, "cross_baseline_split")["picked"], ["p1"])
        strict = audit.choose(rows, "cross_baseline_split_assertion_only")
        self.assertEqual(strict["decision"], "public_random_fallback")
        self.assertEqual(strict["picked"], ["p1", "p2"])

    def test_own_suite_is_not_a_foreign_vote(self):
        rows = audit.observations([cell("donor", 1, True), cell("p2", 0, False)])
        self.assertNotIn("donor", audit.choose(rows, "cross_vote")["scores"])
        self.assertIn("donor", audit.choose(rows, "vote_including_self")["scores"])


if __name__ == "__main__":
    unittest.main()
