"""Regressions outside the original, self-authored evaluation set."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eda_copilot.answer import ask


class EvidenceBoundaries(unittest.TestCase):
    def test_conflicting_run_identities_never_borrow_the_known_run(self):
        identities = ["sky130/gcd", "sky130 gcd", "otherpdk gcd",
                      "nangate45/adder", "nangate45/gcd/tuned",
                      "gcd platform=sky130", "gcd variant=tuned", "gcd2"]
        for identity in identities:
            for suffix in (" 的 setup tns 是多少", " 这次 run 的 setup wns"):
                with self.subTest(identity=identity, suffix=suffix):
                    result = ask(identity + suffix)
                    self.assertTrue(result["hitl"])
                    self.assertEqual(result["hitl_code"], "RUN_OUT_OF_SCOPE")
                    self.assertEqual(result["hits"], [])

    def test_known_run_and_explicit_base_still_have_evidence(self):
        for identity in ("gcd", "nangate45 gcd", "nangate45/gcd", "nangate45/gcd/base"):
            with self.subTest(identity=identity):
                result = ask(identity + " 这次 run 的 setup tns 是多少")
                self.assertFalse(result["hitl"])
                self.assertTrue(result["hits"][0]["cite"].startswith("run_nangate45_gcd/"))

    def test_no_matching_evidence_stops_in_every_retrieval_mode(self):
        for mode in ("bm25", "tfidf", "hybrid"):
            for question in ("今天午饭吃什么", "zzzzqqqvvv", "", "!!!"):
                with self.subTest(mode=mode, question=question):
                    result = ask(question, mode=mode)
                    self.assertTrue(result["hitl"])
                    self.assertEqual(result["hitl_code"], "NO_EVIDENCE")
                    self.assertEqual(result["hits"], [])

    def test_force_is_explicit_and_does_not_leak_into_normal_calls(self):
        question = "今天午饭吃什么"
        self.assertTrue(ask(question)["hitl"])
        self.assertTrue(ask(question, force=True)["hits"])
        self.assertTrue(ask(question)["hitl"])


if __name__ == "__main__":
    unittest.main()
