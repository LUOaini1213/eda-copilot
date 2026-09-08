# -*- coding: utf-8 -*-
"""The committed evaluation artifacts are what a fresh run produces."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "eval" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Ordinal facts: these must reproduce exactly on any machine.
EXACT_KEYS = ("mode", "k", "n_retrieval", "n_stop", "hit_at_k", "hit_rate",
              "stop_caught", "stop_code_correct")
# MRR is not in that list. It depends on the *order* within the top-5, and two
# documents can sit 4e-5 apart in the fused score (case #32: ranks 4 and 5 are
# 0.029080 vs 0.029040). A different BLAS build computes the TF-IDF cosines to
# slightly different last bits, that pair swaps, and MRR moves by 1/4 - 1/5 over
# 23 queries = 0.0022. CI on ubuntu-latest measured 0.7109 where this laptop
# measures 0.7130. Ranking ties are broken by document index (see retrieve.py),
# so what is left is genuine float noise, not an unstable sort. Whether the
# right passage is retrieved at all does not move; where it lands inside the
# top-5 can. So: hit rate exact, MRR to two decimals.
MRR_TOLERANCE = 0.01


class EvaluationReproduces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_eval = _load("run_eval")
        cls.committed = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))

    def test_each_retriever_matches_the_committed_results(self):
        for mode in ("bm25", "tfidf", "hybrid"):
            with self.subTest(mode=mode):
                fresh = self.run_eval.evaluate(mode)
                for key in EXACT_KEYS:
                    self.assertEqual(fresh[key], self.committed[mode][key], key)
                self.assertAlmostEqual(fresh["mrr"], self.committed[mode]["mrr"],
                                       delta=MRR_TOLERANCE, msg="mrr")
                self.assertEqual([m["id"] for m in fresh["retrieval_misses"]],
                                 [m["id"] for m in self.committed[mode]["retrieval_misses"]])

    def test_hybrid_is_the_default_because_it_wins_on_hit_at_5(self):
        h, b = self.committed["hybrid"], self.committed["bm25"]
        self.assertEqual(h["hit_at_k"], "22/23")
        self.assertGreater(h["hit_rate"], b["hit_rate"])
        self.assertEqual((h["stop_caught"], h["stop_code_correct"]), ("12/12", "12/12"))

    def test_ablation_artifact_matches_a_fresh_run(self):
        ablation = _load("ablation")
        fresh = ablation.compute()
        committed = json.loads((ROOT / "eval" / "ablation.json").read_text(encoding="utf-8"))
        self.assertEqual(ablation.summary(fresh), ablation.summary(committed))
        self.assertEqual([r["harm"] for r in fresh["rows"]], [r["harm"] for r in committed["rows"]])
        self.assertNotIn("UNKNOWN", fresh["危害分级"])
        self.assertEqual(sum(fresh["危害分级"].values()), 12)


if __name__ == "__main__":
    unittest.main()
