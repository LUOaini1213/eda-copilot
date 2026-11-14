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


def _cited_text(result: dict) -> str:
    return result["hits"][0]["text"] if result["hits"] else ""


class ReviewProbes(unittest.TestCase):
    """Questions a reviewer asked on 2026-11-03, outside eval/cases.json.

    They were written before guard.py was changed and failed on bd6d40a; the
    guard was then changed until they pass. So they are regression tests now,
    not an unbiased held-out measurement -- that is eval/heldout_cases.json,
    which was written after the change and never used to tune it.
    They stay out of cases.json so the 23/12 headline set stays comparable.
    """

    def assertStops(self, question, code=None):
        result = ask(question)
        self.assertTrue(result["hitl"], f"{question!r} was answered from {result['hits'][:1]}")
        if code:
            self.assertEqual(result["hitl_code"], code)
        self.assertEqual(result["hits"], [])
        return result

    def assertAnswersFrom(self, question, prefixes, kind=None):
        result = ask(question)
        self.assertFalse(result["hitl"], f"{question!r} stopped with {result['hitl_code']}")
        cites = [h["cite"] for h in result["hits"]]
        self.assertTrue(any(c.startswith(prefixes) for c in cites),
                        f"{question!r} cited {cites}")
        if kind:
            self.assertEqual(result["hits"][0]["kind"], kind, cites)
        return result

    # another design or platform, with no metric word: the gcd run must not answer
    def test_other_designs_never_borrow_the_gcd_run(self):
        for q in ("ibex 的 cts 是怎么做的", "aes 的 cts 是怎么做的",
                  "sky130 的 cts 是怎么做的", "ibex 的 placement 怎么做的",
                  "asap7 上 route 完了吗"):
            with self.subTest(q=q):
                self.assertStops(q, "RUN_OUT_OF_SCOPE")

    def test_a_doc_question_naming_another_design_is_answered_from_docs_only(self):
        result = ask("ibex 的 cts 有哪些参数")
        self.assertFalse(result["hitl"])
        self.assertTrue(result["hits"])
        self.assertNotIn("run", {h["kind"] for h in result["hits"]})

    # English documentation questions must not hit the setup/hold guard
    def test_english_documentation_questions_are_not_stopped(self):
        self.assertAnswersFrom("what does repair_timing do",
                               ("openroad_docs/rsz_README.md", "orfs_scripts/"))
        self.assertAnswersFrom("how to use repair_timing",
                               ("openroad_docs/rsz_README.md", "orfs_scripts/"))
        self.assertAnswersFrom("which command runs detailed routing",
                               ("openroad_docs/drt_README.md", "orfs_scripts/detail_route.tcl"))
        self.assertAnswersFrom("what does set_global_routing_layer_adjustment do",
                               ("openroad_docs/grt_README.md", "orfs_scripts/"))

    def test_an_english_question_with_no_corner_still_stops(self):
        self.assertTrue(ask("what is the wns")["hitl"])

    def test_a_bare_place_names_the_stage(self):
        result = self.assertAnswersFrom("place 阶段的 density 参数怎么设",
                                        ("openroad_docs/gpl_README.md", "orfs_scripts/global_place.tcl"))
        self.assertEqual(result["stage"], "place")

    # run metrics of gcd: the top-1 passage must hold the value asked for
    def test_run_metrics_of_gcd_cite_the_passage_that_holds_them(self):
        for q, needle in (("gcd 的利用率是多少", "utilization"),
                          ("what is the utilization of the gcd run", "utilization"),
                          ("gcd 的实例数是多少", "finish__design__instance__count"),
                          ("gcd 的 hold wns 是多少", "finish__timing__hold__ws")):
            with self.subTest(q=q):
                result = ask(q)
                self.assertFalse(result["hitl"], result["hitl_code"])
                self.assertTrue(result["hits"][0]["cite"].startswith("run_nangate45_gcd/"))
                self.assertIn(needle, _cited_text(result))

    def test_an_unqualified_area_is_ambiguous(self):
        self.assertStops("gcd 的面积是多少", "AMBIGUOUS_METRIC")

    def test_a_qualified_die_area_is_not_ambiguous(self):
        # 护栏让人「请指定 die / core / utilization」；指定了 die 就该放行并引到 Die area 那行
        result = ask("gcd 的 die 面积是多少")
        self.assertFalse(result["hitl"], result["hitl_code"])
        self.assertIn("Die area:", _cited_text(result))

    def test_setup_numbers_of_gcd_still_come_from_the_finish_report(self):
        for q in ("gcd 的 setup tns 是多少", "what is the setup WNS of the gcd run"):
            with self.subTest(q=q):
                self.assertAnswersFrom(q, ("run_nangate45_gcd/6_finish.rpt",))

    def test_a_pure_chinese_question_reaches_the_english_docs(self):
        self.assertAnswersFrom("如何降低布线拥塞",
                               ("openroad_docs/grt_README.md", "orfs_scripts/global_route.tcl"))

    def test_the_run_refusal_names_what_is_missing(self):
        result = self.assertStops("本次 run 的 setup tns 是多少", "RUN_OUT_OF_SCOPE")
        self.assertIn("gcd", result["hitl_reason"])
        self.assertNotIn("请指明是这次运行", result["hitl_reason"])
        self.assertStops("我的 sky130 设计 setup wns 多少", "RUN_OUT_OF_SCOPE")


if __name__ == "__main__":
    unittest.main()
