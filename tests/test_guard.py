# -*- coding: utf-8 -*-
"""The stop-and-ask guard, asserted case by case against eval/cases.json."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eda_copilot.answer import ask  # noqa: E402
from eda_copilot.guard import HITL_CODES  # noqa: E402

CASES = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
STOP = [c for c in CASES if c.get("expect_hitl")]
ANSWER = [c for c in CASES if not c.get("expect_hitl")]


class GuardCases(unittest.TestCase):
    def test_suite_shape(self):
        self.assertEqual((len(CASES), len(ANSWER), len(STOP)), (35, 23, 12))

    def test_every_stop_case_stops_with_the_expected_structured_code(self):
        for c in STOP:
            with self.subTest(case=c["id"]):
                r = ask(c["q"])
                self.assertTrue(r["hitl"])
                self.assertEqual(r["hitl_code"], c["expect_code"])
                self.assertIn(r["hitl_code"], HITL_CODES)

    def test_all_seven_codes_are_exercised(self):
        self.assertEqual({c["expect_code"] for c in STOP}, set(HITL_CODES))

    def test_no_retrieval_case_is_stopped(self):
        for c in ANSWER:
            with self.subTest(case=c["id"]):
                r = ask(c["q"])
                self.assertFalse(r["hitl"], f"documentation question stopped: {r.get('hitl_code')}")
                self.assertTrue(r["hits"])

    def test_forced_mode_answers_every_stop_case_with_a_citation_and_records_the_guess(self):
        for c in STOP:
            with self.subTest(case=c["id"]):
                r = ask(c["q"], force=True)
                self.assertFalse(r["hitl"])
                self.assertTrue(r["hits"], "forced mode must still return cited hits")
                self.assertTrue(r["guesses"], "every forced answer rests on at least one recorded guess")

    def test_documentation_questions_skip_the_result_oriented_guard(self):
        # The two cases the first evaluation caught (#6, #7): "timing" in a
        # documentation question must not trigger MISSING_CORNER.
        for cid in (6, 7):
            case = next(c for c in CASES if c["id"] == cid)
            with self.subTest(case=cid):
                self.assertFalse(ask(case["q"])["hitl"])


if __name__ == "__main__":
    unittest.main()
