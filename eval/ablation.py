# -*- coding: utf-8 -*-
"""停问机制消融对照。

同一批题跑两次：
  A 基线  ask(q)              护栏开，该停就停
  B 消融  ask(q, force=True)  护栏关，按「没有护栏的系统」的朴素默认强行作答

对 12 条本该停问的题，B 会给出一个看起来正常、带出处的回答——正因为带出处，
它比裸奔的模型更容易被相信。本脚本统计：强行作答几条、其中几条做过无提示猜测、
以及检索到的出处是否已经偏到别的主题上（用阶段标签判定）。

同时检查消融不能损伤本来就该答对的 23 条。
输出 eval/ablation.json。
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eda_copilot.answer import ask            # noqa: E402
from eda_copilot.guard import HITL_CODES      # noqa: E402

HARM = {
    "OUT_OF_SCOPE":     "TOPIC_DRIFT",    # 问的主题根本不在库里，答什么都是答别的
    "RUN_OUT_OF_SCOPE": "FABRICATED_FACT",# 拿本库唯一那次 run 的数值当成你问的那次
    "RELATIVE_RUN":     "WRONG_TARGET",   # 指代对象错了
    "AMBIGUOUS_METRIC": "METRIC_GUESSED", # 猜了一套指标
    "MISSING_CORNER":   "METRIC_GUESSED", # 猜了 setup/hold——两者修复手段相反
    "MISSING_STAGE":    "WRONG_TARGET",
    "UNDEFINED_TERM":   "TOPIC_DRIFT",
}


def compute() -> dict:
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    stop = [c for c in cases if c.get("expect_hitl")]
    keep = [c for c in cases if not c.get("expect_hitl")]

    a_runs = [ask(c["q"]) for c in stop]
    base_stop = sum(1 for r in a_runs if r["hitl"])
    base_silent = sum(1 for r in a_runs if (not r["hitl"]) and r["hits"])

    rows, forced_answered, silent_guess, b_stopped = [], 0, 0, 0
    for c in stop:
        r = ask(c["q"], force=True)
        if r["hitl"]:
            b_stopped += 1
        answered = bool(r["hits"])
        guesses = r.get("guesses") or []
        code = r.get("hitl_code") or ""
        if answered:
            forced_answered += 1
        if answered and guesses:
            silent_guess += 1
        stages = sorted({h["stage"] for h in r["hits"]}) if r["hits"] else []
        rows.append({
            "id": c["id"], "q": c["q"], "code": code,
            "code_zh": HITL_CODES.get(code, ("", ""))[0],
            "harm": HARM.get(code, "UNKNOWN"),
            "guesses": guesses,
            "answered": answered,
            "n_hits": len(r["hits"]),
            "cited_stages": stages,
            "top_cite": r["hits"][0]["cite"] if r["hits"] else None,
            "note": "带出处地答了一个本不该答的问题" if answered else "即使关掉护栏也没检索到东西",
        })

    regressions = []
    for c in keep:
        a, b = ask(c["q"]), ask(c["q"], force=True)
        sa = [h["cite"] for h in a["hits"]]
        sb = [h["cite"] for h in b["hits"]]
        if sa != sb:
            regressions.append({"id": c["id"], "q": c["q"]})

    dist = {}
    for r in rows:
        k = r["code"] or "UNKNOWN"
        d = dist.setdefault(k, {"code_zh": HITL_CODES.get(k, ("", ""))[0],
                                "说明": HITL_CODES.get(k, ("", ""))[1], "n": 0, "ids": []})
        d["n"] += 1; d["ids"].append(r["id"])

    result = {
        "n_stop_cases": len(stop), "n_answer_cases": len(keep),
        "A_护栏开": {"该停的停住": f"{base_stop}/{len(stop)}", "静默错答": base_silent},
        "B_护栏关": {
            "该停的停住": f"{b_stopped}/{len(stop)}",
            "强行作答": f"{forced_answered}/{len(stop)}",
            "无提示猜测": f"{silent_guess}/{len(stop)}",
            f"对{len(keep)}题正常问答的回归": len(regressions),
        },
        "停问原因分布": dist,
        "危害分级": {h: sum(1 for r in rows if r["harm"] == h) for h in sorted({r["harm"] for r in rows})},
        "rows": rows,
        "regressions": regressions,
    }
    return result


def summary(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in ("rows", "regressions")}


def main(argv=None) -> int:
    """Write eval/ablation.json, or with --check compare a fresh run against it."""
    argv = sys.argv[1:] if argv is None else argv
    result = compute()
    out = ROOT / "eval" / "ablation.json"
    if "--check" in argv:
        committed = json.loads(out.read_text(encoding="utf-8"))
        same = (summary(result) == summary(committed)
                and [r["harm"] for r in result["rows"]] == [r["harm"] for r in committed["rows"]])
        print("ok: eval/ablation.json matches a fresh run" if same
              else "DRIFT: eval/ablation.json differs from a fresh run")
        return 0 if same else 1
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
