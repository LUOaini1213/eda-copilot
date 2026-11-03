# -*- coding: utf-8 -*-
"""编排：先过护栏，过不了就停下来问人；过得了才检索并组装带出处的回答。

**不接大模型**：回答由检索到的原文片段 + 出处组装而成，离线、零 token、可复现。
本包里没有任何模型调用，也不读 API key——没有可打开的生成开关。
这样做的原因和 malaysia-auto-ask 一致：先把「答得对不对、该不该答」这层做扎实，
生成只是最后一层皮。
"""
from __future__ import annotations

from functools import lru_cache

from .guard import HITL_CODES, parse
from .ingest import load_documents
from .retrieve import Retriever


# 中文问法 -> 语料里的英文术语。语料全是英文，纯中文问题只能靠夹带的英文标识符
# 命中；这张小表只收领域里一对一的词，查询时追加在原句后面，原句不改。
# 不收「时序 / 面积」这类本身有歧义、要由护栏先问清的词。
ZH_TERMS = (
    ("拥塞", "congestion"),
    ("布线", "routing"),
    ("绕线", "routing"),
    ("时钟树", "clock tree"),
    ("利用率", "utilization"),
    ("实例数", "instance count"),
)

# 问本次 run 的 hold 数值：6_finish.rpt 里的 tns / wns / worst slack 全是 max（setup），
# hold 的数只在 6_report.json 的 finish__timing__hold__* 里。不补这层，
# 「gcd 的 hold wns」会因为 wns 这个词命中 setup 那一段，带出处地答错。
_HOLD_RUN_TERMS = "finish__timing__hold__ws finish__timing__hold__tns"


def expand_query(question: str, run_intent: bool = False, check_type: str | None = None) -> str:
    extra = [en for zh, en in ZH_TERMS if zh in question]
    if run_intent and check_type == "hold":
        extra.append(_HOLD_RUN_TERMS)
    return question if not extra else question + " " + " ".join(extra)


@lru_cache(maxsize=4)
def _retriever(mode: str = "bm25") -> Retriever:
    return Retriever(load_documents(), mode=mode)


def ask(question: str, k: int = 4, mode: str = "bm25", force: bool = False) -> dict:
    it = parse(question, force=force)
    out: dict = {
        "question": question,
        "hitl": it.hitl,
        "hitl_code": it.hitl_code,
        "hitl_reason": it.hitl_reason,
        "guesses": it.guesses,
        "stage": it.stage,
        "check_type": it.check_type,
        "forced": force,
        "hits": [],
        "answer": "",
    }
    if it.hitl:
        zh, why = HITL_CODES.get(it.hitl_code, ("", ""))
        out["answer"] = f"[停下来问人 · {zh}] {it.hitl_reason}"
        return out

    # guard 已经判过这是「问本次 run 的数值」还是「问文档」，直接复用，不重复判一遍
    run_intent = any(n.startswith("run=") for n in it.notes)
    prefer = "run" if run_intent else None
    exclude = "run" if "exclude=run" in it.notes else None
    query = expand_query(question, run_intent=run_intent, check_type=it.check_type)
    hits = _retriever(mode).search(query, k=k, stage=it.stage, prefer_kind=prefer,
                                  allow_unmatched=force, exclude_kind=exclude)
    out["hits"] = [{"cite": h.cite, "stage": h.doc.metadata.get("stage"),
                    "kind": h.doc.metadata.get("kind"), "score": round(h.score, 5),
                    "text": h.doc.page_content} for h in hits]
    if not hits:
        out["answer"] = "[停下来问人 · 无命中] 语料里没有能支撑回答的片段，请换个说法或确认这是不是本库覆盖的主题。"
        out["hitl"] = True
        out["hitl_code"] = "NO_EVIDENCE"
        return out

    top = hits[0]
    out["answer"] = (f"依据 {top.cite}（{top.doc.metadata.get('kind')}，阶段 "
                     f"{top.doc.metadata.get('stage')}）：\n{top.doc.page_content.strip()[:700]}")
    return out
