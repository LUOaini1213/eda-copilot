# -*- coding: utf-8 -*-
"""检索评测 + 停问评测。三种检索模式各跑一遍，看混合到底有没有用。

指标：
  Hit@k   期望出处出现在 top-k 里的比例
  MRR     期望出处的最高排名的倒数均值
  停问准确 该停的停住、且原因码判对

不带参数：把结果写回 eval/results.json。
带 --check：只跑不写，把这次新跑和已提交的 eval/results.json 比一遍，对不上退出码 1。
CI 用的是 --check，因为「重写一遍产物」永远不会失败，那不叫校验。
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


# 序数事实必须逐位相同；MRR 只到 0.01，理由见 README §4.1 与 tests/test_eval_reproduces.py
# （换一套 BLAS，TF-IDF 余弦的末位不同，同分的两篇会换位，MRR 摊到 23 题动 0.0022）。
EXACT_KEYS = ("mode", "k", "n_retrieval", "n_stop", "hit_at_k", "hit_rate",
              "stop_caught", "stop_code_correct")
MRR_TOLERANCE = 0.01


def drifts(fresh: dict, committed: dict) -> list[str]:
    """把一次新跑和已提交的 results.json 逐项比对，返回对不上的地方。"""
    out = []
    for mode in sorted(set(fresh) | set(committed)):
        if mode not in committed:
            out.append(f"{mode}: 已提交的 results.json 里没有这一档"); continue
        if mode not in fresh:
            out.append(f"{mode}: 这次新跑里没有这一档"); continue
        f, c = fresh[mode], committed[mode]
        for key in EXACT_KEYS:
            if f[key] != c[key]:
                out.append(f"{mode}.{key}: 新跑 {f[key]!r} != 已提交 {c[key]!r}")
        if abs(f["mrr"] - c["mrr"]) > MRR_TOLERANCE:
            out.append(f"{mode}.mrr: 新跑 {f['mrr']} != 已提交 {c['mrr']}（容差 {MRR_TOLERANCE}）")
        for field in ("retrieval_misses", "stop_misses"):
            fi = [m["id"] for m in f[field]]
            ci = [m["id"] for m in c[field]]
            if fi != ci:
                out.append(f"{mode}.{field}: 新跑 {fi} != 已提交 {ci}")
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    out = {m: evaluate(m) for m in ("bm25", "tfidf", "hybrid")}
    if not check:
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
    if not check:
        return 0
    committed = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
    problems = drifts(out, committed)
    if problems:
        print("\nDRIFT: eval/results.json 与一次新跑对不上：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nok: eval/results.json matches a fresh run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
