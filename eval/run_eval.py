# -*- coding: utf-8 -*-
"""检索评测 + 停问评测。三种检索模式各跑一遍，看混合到底有没有用。

指标：
  Hit@k   期望出处出现在 top-k 里的比例
  MRR     期望出处的最高排名的倒数均值
  停问准确 该停的停住、且原因码判对
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eda_copilot.answer import ask  # noqa: E402


def evaluate(mode: str, k: int = 5) -> dict:
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    ret = [c for c in cases if not c.get("expect_hitl")]
    stop = [c for c in cases if c.get("expect_hitl")]

    hit, rr, misses = 0, 0.0, []
    for c in ret:
        r = ask(c["q"], k=k, mode=mode)
        srcs = [h["cite"].split(" :: ")[0] for h in r["hits"]]
        pos = next((i for i, s in enumerate(srcs) if s in c["expect_source"]), None)
        if pos is None:
            misses.append({"id": c["id"], "q": c["q"], "got": srcs[:3], "want": c["expect_source"]})
        else:
            hit += 1; rr += 1.0 / (pos + 1)

    stop_ok, code_ok, stop_miss = 0, 0, []
    for c in stop:
        r = ask(c["q"], k=k, mode=mode)
        if r["hitl"]:
            stop_ok += 1
            if r["hitl_code"] == c["expect_code"]: code_ok += 1
            else: stop_miss.append({"id": c["id"], "q": c["q"], "got": r["hitl_code"], "want": c["expect_code"]})
        else:
            stop_miss.append({"id": c["id"], "q": c["q"], "got": "ANSWERED", "want": c["expect_code"]})

    return {
        "mode": mode, "k": k,
        "n_retrieval": len(ret), "n_stop": len(stop),
        "hit_at_k": f"{hit}/{len(ret)}", "hit_rate": round(hit / len(ret), 4),
        "mrr": round(rr / len(ret), 4),
        "stop_caught": f"{stop_ok}/{len(stop)}", "stop_code_correct": f"{code_ok}/{len(stop)}",
        "retrieval_misses": misses, "stop_misses": stop_miss,
    }


def main() -> int:
    out = {m: evaluate(m) for m in ("bm25", "tfidf", "hybrid")}
    (ROOT / "eval" / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'mode':<8}{'Hit@5':>10}{'HitRate':>10}{'MRR':>9}{'停问':>10}{'原因码':>10}")
    for m, r in out.items():
        print(f"{m:<8}{r['hit_at_k']:>10}{r['hit_rate']:>10}{r['mrr']:>9}{r['stop_caught']:>10}{r['stop_code_correct']:>10}")
    for m, r in out.items():
        if r["retrieval_misses"]:
            print(f"\n[{m}] 检索没命中的：")
            for x in r["retrieval_misses"]:
                print(f"  #{x['id']} {x['q']}\n      want={x['want']}\n      got ={x['got']}")
        if r["stop_misses"]:
            print(f"\n[{m}] 停问判错的：")
            for x in r["stop_misses"]:
                print(f"  #{x['id']} {x['q']}  got={x['got']} want={x['want']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
