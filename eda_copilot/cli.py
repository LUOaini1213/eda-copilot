# -*- coding: utf-8 -*-
"""命令行：python -m eda_copilot.cli "cts 的 sink clustering 是干什么的" """
from __future__ import annotations

import argparse, json, sys
from .answer import ask


def build_parser() -> argparse.ArgumentParser:
    """The command line, as a value, so the tests can assert what it exposes."""
    ap = argparse.ArgumentParser(description="EDA Copilot：OpenROAD 流程问答，口径不清就停下来问人")
    ap.add_argument("question", nargs="*")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--mode", choices=["bm25", "tfidf", "hybrid"], default="bm25")
    ap.add_argument("--force", action="store_true", help="消融模式：关掉停问护栏")
    ap.add_argument("--json", action="store_true")
    return ap


def main() -> int:
    ap = build_parser()
    a = ap.parse_args()
    q = " ".join(a.question).strip()
    if not q:
        ap.print_help(); return 2
    r = ask(q, k=a.k, mode=a.mode, force=a.force)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
    print(r["answer"])
    if r["hits"]:
        print("\n出处：")
        for h in r["hits"]:
            print(f"  - {h['cite']}  [{h['stage']}/{h['kind']}]  {h['score']}")
    if r["guesses"]:
        print("\n（消融模式下做过的猜测）")
        for g in r["guesses"]:
            print("  !", g)
    return 0


if __name__ == "__main__":
    sys.exit(main())
