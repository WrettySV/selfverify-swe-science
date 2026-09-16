import json
from pathlib import Path
import tempfile
import unittest

from selfverify.metrics import collect_session_usage


class UsageTests(unittest.TestCase):
    def test_sums_last_totals_of_each_session_across_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for day, values in (("15", [4, 10]), ("16", [3, 7])):
                target = root / "sessions/2026/09" / day
                target.mkdir(parents=True)
                rows = [{"type": "session_meta", "payload": {"id": day}}]
                rows.extend({"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": value, "output_tokens": 2, "total_tokens": value+2},
                    "last_token_usage": {"input_tokens": 4}}}} for value in values)
                (target / "session.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
            result = collect_session_usage(root)
            self.assertEqual(result["n_sessions"], 2)
            self.assertEqual(result["totals"]["input_tokens"], 17)
            self.assertEqual(result["totals"]["total_tokens"], 21)
            self.assertTrue(result["complete"])
