# -*- coding: utf-8 -*-
"""Every number README.md states is recomputed here from the corpus and the
committed evaluation artifacts.

The rest of the suite pins ``eval/results.json`` and ``eval/ablation.json`` to a
fresh run. Nothing pinned README.md -- which is the only layer most readers ever
open. The retrieval table, the chunk count, the corpus file counts, the
wall-clock of the run and the three conclusions read off ``6_report.json`` were
all transcribed by hand, so a wrong transcription stayed green.

This module asserts nothing new about the system. It refuses to let the prose
and the artifacts drift apart: the README is parsed, every value is recomputed
from its source, and the two must agree.

Two deliberate choices:
  * README values are compared against the *committed* eval/*.json, never
    against a fresh evaluation. Both sides are then static, so MRR can be
    compared exactly instead of inheriting the 0.01 BLAS tolerance that
    tests/test_eval_reproduces.py has to live with.
  * ``hit_rate`` is compared as a float: the artifact holds ``0.913`` where the
    README table writes ``0.9130``. Comparing the strings would report a
    correct README as broken.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eda_copilot.cli import build_parser  # noqa: E402
from eda_copilot.guard import HITL_CODES  # noqa: E402
from eda_copilot.ingest import load_documents  # noqa: E402

CORPUS = ROOT / "corpus"
RUN = CORPUS / "run_nangate45_gcd"

README = (ROOT / "README.md").read_text(encoding="utf-8")
RESULTS = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
ABLATION = json.loads((ROOT / "eval" / "ablation.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
REPORT = json.loads((RUN / "6_report.json").read_text(encoding="utf-8"))

# README writes negative numbers with a typographic minus (U+2212).
MINUS = "−"

# Flags that appear in README but belong to eval/*.py, not to the CLI.
NON_CLI_FLAGS = {"--check"}

ELAPSED = re.compile(r"Elapsed time: (\d+):(\d+(?:\.\d+)?)")


def corpus_file_count(subdir: str) -> int:
    """Real files only: no dotfiles and no directories, so a dirty working tree
    (a stray __pycache__, an editor swap file) cannot turn this red."""
    return sum(1 for p in (CORPUS / subdir).iterdir()
               if p.is_file() and not p.name.startswith("."))


def stage_log_elapsed() -> tuple[int, float]:
    """(how many stage logs report an elapsed time, how many seconds in total)."""
    total, n = 0.0, 0
    for log in sorted(RUN.glob("*.log")):
        for m in ELAPSED.finditer(log.read_text(encoding="utf-8", errors="replace")):
            total += int(m.group(1)) * 60 + float(m.group(2))
            n += 1
    return n, total


def cited_passage(cite: str) -> str:
    """The text a citation like ``6_finish.rpt :: 2-10`` actually points at."""
    path, lines = cite.split(" :: ")
    first, last = (int(x) for x in lines.split("-"))
    body = (CORPUS / path).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(body[first - 1:last])


class ReadmeNumbers(unittest.TestCase):
    # ---- helpers ---------------------------------------------------------
    def one(self, pattern, cast=str, text=README):
        """The single capture group of `pattern`, or a failure naming what is gone."""
        found = re.findall(pattern, text)
        self.assertEqual(len(found), 1, f"README no longer has exactly one {pattern!r}")
        return cast(found[0].replace(MINUS, "-")) if cast is not str else found[0]

    def section(self, start: str, end: str) -> str:
        a = README.index(start)
        b = README.index(end, a)
        return README[a:b]

    # ---- 4.1 retrieval ---------------------------------------------------
    def test_the_retrieval_table_matches_the_committed_results(self):
        row = re.compile(r"^\|\s*\*{0,2}(bm25|hybrid|tfidf)(?:（默认）)?\*{0,2}\s*\|"
                         r"\s*\*{0,2}(\d+/\d+)\*{0,2}\s*\|"
                         r"\s*\*{0,2}([\d.]+)\*{0,2}\s*\|"
                         r"\s*\*{0,2}([\d.]+)\*{0,2}\s*\|", re.M)
        table = {m[0]: m[1:] for m in row.findall(README)}
        self.assertEqual(set(table), {"bm25", "hybrid", "tfidf"})
        for mode, (hit, hit_rate, mrr) in table.items():
            with self.subTest(mode=mode):
                self.assertEqual(hit, RESULTS[mode]["hit_at_k"])
                self.assertEqual(float(hit_rate), RESULTS[mode]["hit_rate"])
                self.assertEqual(float(mrr), RESULTS[mode]["mrr"])

    def test_the_retriever_the_table_marks_as_default_is_the_default_in_the_code(self):
        marked = self.one(r"\|\s*\*{0,2}(bm25|hybrid|tfidf)（默认）")
        self.assertEqual(marked, build_parser().get_default("mode"))

    def test_the_mrr_gap_the_readme_calls_too_small_to_choose_on_really_is(self):
        gap = self.one(r"MRR 上 bm25 高\s*\n?([\d.]+)", float)
        tolerance = self.one(r"复现容差就是 ([\d.]+)", float)
        self.assertAlmostEqual(gap, RESULTS["bm25"]["mrr"] - RESULTS["hybrid"]["mrr"], places=4)
        self.assertLess(gap, tolerance)

    # ---- 4.2 / 4.3 guard and ablation ------------------------------------
    def test_the_case_counts_match_eval_cases_json(self):
        stop = [c for c in CASES if c.get("expect_hitl")]
        answer = [c for c in CASES if not c.get("expect_hitl")]
        total, n_answer, n_stop = re.search(
            r"cases\.json\s+(\d+) 条用例（(\d+) 检索 \+ (\d+) 停问）", README).groups()
        self.assertEqual((int(total), int(n_answer), int(n_stop)),
                         (len(CASES), len(answer), len(stop)))
        self.assertEqual(self.one(r"### 4\.1 检索（(\d+) 题", int), len(answer))
        self.assertEqual(self.one(r"### 4\.2 停问（(\d+) 题）", int), len(stop))

    def test_the_seven_reason_codes_in_the_table_are_the_seven_the_guard_has(self):
        table = self.section("## 3. 停问机制", "## 4. 评测结果")
        self.assertEqual(set(re.findall(r"^\|\s*`([A-Z_]+)`\s*\|", table, re.M)),
                         set(HITL_CODES))
        self.assertEqual(self.one(r"## 3\. 停问机制：(\d+) 类结构化原因码", int),
                         len(HITL_CODES))

    def test_the_ablation_tables_match_the_committed_ablation(self):
        a, b = ABLATION["A_护栏开"], ABLATION["B_护栏关"]
        stopped_a, stopped_b = re.search(
            r"\|\s*该停的停住\s*\|\s*(\S+)\s*\|\s*\*\*(\S+)\*\*\s*\|", README).groups()
        self.assertEqual(stopped_a, a["该停的停住"])
        self.assertEqual(stopped_b, b["该停的停住"])
        self.assertEqual(self.one(r"\|\s*强行作答\s*\|\s*—\s*\|\s*\*\*(\S+)\*\*\s*\|"),
                         b["强行作答"])
        silent_a, forced_b = re.search(
            r"\|\s*无提示猜测\s*\|\s*(\d+)\s*\|\s*\*\*(\S+)\*\*\s*\|", README).groups()
        self.assertEqual(int(silent_a), a["静默错答"])
        self.assertEqual(forced_b, b["无提示猜测"])
        n_answer, regressions = re.search(
            r"\|\s*对 (\d+) 题正常问答的回归\s*\|\s*—\s*\|\s*\*\*(\d+)\*\*\s*\|", README).groups()
        self.assertEqual(int(n_answer), ABLATION["n_answer_cases"])
        self.assertEqual(int(regressions), b["对23题正常问答的回归"])

    def test_the_harm_grades_match_the_committed_ablation(self):
        table = self.section("**危害分级：**", "**最值得看的一条：**")
        grades = {k: int(v) for k, v in re.findall(r"^\|\s*`([A-Z_]+)`\s*\|\s*(\d+)\s*\|",
                                                   table, re.M)}
        self.assertEqual(grades, ABLATION["危害分级"])
        self.assertEqual(sum(grades.values()), ABLATION["n_stop_cases"])

    def test_the_forced_mode_citations_quoted_in_the_readme_come_from_the_artifact(self):
        rows = {r["q"]: r for r in ABLATION["rows"]}
        shared = self.one(r"四题的 top-1 出处是同一段\*\*——\s*`([^`]+)`")
        for q in ("DRAM 的字线和位线怎么布", "晶圆图的缺陷模式怎么分类",
                  "帮我看看", "优化一下这个流程"):
            with self.subTest(q=q):
                self.assertIn(f"「{q}」", README)
                self.assertEqual(rows[q]["top_cite"], shared)
        area = self.one(r"那一段的正文是 `([^`]+)`")
        self.assertIn(area, cited_passage(shared))

        wns_cite = self.one(r"而「我的设计 WNS 是多少」返回 `([^`]+)`")
        self.assertEqual(rows["我的设计 WNS 是多少"]["top_cite"], wns_cite)
        passage = cited_passage(wns_cite)
        for quoted in re.search(r"那一段的正文就是 `([^`]+)` / `([^`]+)`", README).groups():
            self.assertIn(quoted, passage)

    # ---- 2. corpus -------------------------------------------------------
    def test_the_chunk_count_and_average_chunk_length(self):
        chunks, average = re.search(r"切块后 \*\*(\d+) 块\*\*，平均 (\d+) 字符", README).groups()
        docs = load_documents()
        self.assertEqual(int(chunks), len(docs))
        self.assertEqual(int(average),
                         round(sum(len(d.page_content) for d in docs) / len(docs)))

    def test_the_corpus_file_counts(self):
        listed = {d: int(n) for d, n in re.findall(
            r"\|\s*`corpus/([a-z0-9_]+)/`\s*\|[^|]*\|\s*(\d+) 个文件\s*\|", README)}
        self.assertEqual(set(listed), {"orfs_scripts", "openroad_docs", "run_nangate45_gcd"})
        for subdir, n in listed.items():
            with self.subTest(subdir=subdir):
                self.assertEqual(n, corpus_file_count(subdir))
        total, third_party, own = re.search(
            r"corpus/\s+(\d+) 个真实文件（(\d+) 脚本\+文档，(\d+) 本人运行产物）", README).groups()
        self.assertEqual(int(total), sum(listed.values()))
        self.assertEqual(int(third_party), listed["orfs_scripts"] + listed["openroad_docs"])
        self.assertEqual(int(own), listed["run_nangate45_gcd"])

    def test_the_headline_numbers_of_the_run(self):
        instances = REPORT["finish__design__instance__count"]
        n_logs, seconds = stage_log_elapsed()
        # The English opening paragraph, the figure caption and the image alt text
        # all restate the same three numbers; every one of them has to hold.
        en = re.search(r"nangate45/gcd, (\d+) instances, (\d+) s of wall-clock "
                       r"across (\d+) stage logs", README).groups()
        self.assertEqual([int(x) for x in en], [instances, round(seconds), n_logs])
        zh = re.search(r"(\d+) 个实例，(\d+) 个阶段日志累计 (\d+) s", README).groups()
        self.assertEqual([int(x) for x in zh], [instances, n_logs, round(seconds)])
        self.assertEqual(self.one(r"clock tree of all (\d+) instances", int), instances)
        self.assertEqual(self.one(r"实例数 (\d+)，利用率", int), instances)
        self.assertEqual(self.one(r"（\*\*(\d+) 个实例\*\*）", int), instances)

    def test_the_three_conclusions_read_off_the_committed_report(self):
        tns = REPORT["finish__timing__setup__tns"]
        wns = REPORT["finish__timing__setup__ws"]
        buffers = REPORT["finish__design__instance__count__class:timing_repair_buffer"]
        buffer_area = REPORT["finish__design__instance__area__class:timing_repair_buffer"]
        stdcell_area = REPORT["finish__design__instance__area__stdcell"]

        self.assertEqual(self.one(r"\*\*TNS\(setup\) = (.\d+\.\d+)", float), round(tns, 2))
        self.assertEqual(self.one(r"WNS\(setup\) = (.\d+\.\d+)\*\*", float), round(wns, 2))
        self.assertEqual(self.one(r"finish__timing__setup__tns = (.\d+\.\d+)", float),
                         round(tns, 2))
        self.assertEqual(self.one(r"比值约 (\d+)", int), round(tns / wns))
        self.assertEqual(self.one(r"`timing_repair_buffer` (\d+) 个", int), buffers)
        self.assertEqual(self.one(r"个、([\d.]+) µm²", float), buffer_area)
        self.assertEqual(self.one(r"标准单元实例面积 ([\d.]+) µm²", float), stdcell_area)
        share = self.one(r"已占标准单元面积 ([\d.]+)%", float)
        self.assertEqual(share, round(buffer_area / stdcell_area * 100, 1))
        self.assertEqual(self.one(r"finish__clock__skew__setup = ([\d.]+)", float),
                         REPORT["finish__clock__skew__setup"])
        self.assertEqual(self.one(r"利用率 ([\d.]+)。", float),
                         round(REPORT["finish__design__instance__utilization"], 3))

    def test_the_line_numbers_the_readme_cites_hold_what_it_says_they_hold(self):
        report = (RUN / "6_report.json").read_text(encoding="utf-8").splitlines()
        finish = (RUN / "6_finish.rpt").read_text(encoding="utf-8").splitlines()
        cited = {
            30: "finish__timing__setup__tns",
            16: "finish__design__instance__count__class:timing_repair_buffer",
            17: "finish__design__instance__area__class:timing_repair_buffer",
            55: "947.758",
            36: "finish__clock__skew__setup",
        }
        for line, needle in cited.items():
            with self.subTest(line=line):
                self.assertIn(needle, report[line - 1])
        self.assertIn("0.00 setup skew", finish[30])  # README: 6_finish.rpt 第 31 行

    # ---- the README must not document things the code does not have ------
    def test_every_cli_flag_the_readme_documents_actually_exists(self):
        mentioned = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", README)) - NON_CLI_FLAGS
        help_text = build_parser().format_help()
        for flag in sorted(mentioned):
            with self.subTest(flag=flag):
                self.assertIn(flag, help_text)

    def test_the_structure_tree_lists_every_test_file(self):
        tree = README[README.index("## 7. 结构"):]
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            with self.subTest(test=path.name):
                self.assertIn(path.name, tree)


if __name__ == "__main__":
    unittest.main()
