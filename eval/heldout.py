# -*- coding: utf-8 -*-
"""Held-out guard + retrieval probes (eval/heldout_cases.json).

The 35 cases in eval/cases.json are the ones the guard rules were written
against. These 20 were written afterwards and the code was not changed to make
them pass, so the pass count here is the closest thing this repo has to an
out-of-sample number. It is still author-written and small (n=20).

  python eval/heldout.py          run, print, write eval/heldout.json
  python eval/heldout.py --check  run and compare against the committed file (CI)

Judging rules (per case "expect"):
  stop         the question must stop; if "codes" is non-empty the code must be one of them
  answer       not stopped, and the top-1 citation starts with one of "top1";
               if "top1_text" is given, the top-1 passage must contain it (case-insensitive)
  no_run_hits  either stopped, or answered without citing any run artifact
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eda_copilot.answer import ask  # noqa: E402

CASES = ROOT / "eval" / "heldout_cases.json"
OUT = ROOT / "eval" / "heldout.json"


def judge(case: dict, r: dict) -> bool:
    if case["expect"] == "stop":
        return r["hitl"] and (not case["codes"] or r["hitl_code"] in case["codes"])
    if case["expect"] == "no_run_hits":
        return r["hitl"] or all(h["kind"] != "run" for h in r["hits"])
    if r["hitl"] or not r["hits"]:
        return False
    top = r["hits"][0]
    ok = top["cite"].startswith(tuple(case["top1"]))
    if case.get("top1_text"):
        ok = ok and case["top1_text"].lower() in top["text"].lower()
    return ok


def compute() -> dict:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    rows = []
    for c in cases:
        r = ask(c["q"])
        rows.append({
            "id": c["id"], "q": c["q"], "expect": c["expect"],
            "pass": judge(c, r),
            "hitl_code": r["hitl_code"],
            "top_cite": r["hits"][0]["cite"] if r["hits"] else None,
        })
    n_pass = sum(r["pass"] for r in rows)
    return {"passed": f"{n_pass}/{len(rows)}",
            "failed_ids": [r["id"] for r in rows if not r["pass"]],
            "rows": rows}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = compute()
    if "--check" in argv:
        committed = json.loads(OUT.read_text(encoding="utf-8"))
        same = ([(r["id"], r["pass"], r["hitl_code"]) for r in result["rows"]]
                == [(r["id"], r["pass"], r["hitl_code"]) for r in committed["rows"]]
                and result["passed"] == committed["passed"])
        print("ok: eval/heldout.json matches a fresh run" if same
              else "DRIFT: eval/heldout.json differs from a fresh run")
        return 0 if same else 1
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                   newline="\n")
    print(f"held-out: {result['passed']} passed; failed: {result['failed_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
