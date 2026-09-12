# -*- coding: utf-8 -*-
"""编排：先过护栏，过不了就停下来问人；过得了才检索并组装带出处的回答。

默认**不接大模型**：回答由检索到的原文片段 + 出处组装而成，离线、零 token、可复现。
接大模型是可选项（--llm），仅在显式打开且有 API key 时启用；关掉时系统仍完整可用。
这样做的原因和 malaysia-auto-ask 一致：先把「答得对不对、该不该答」这层做扎实，
生成只是最后一层皮。
"""
from __future__ import annotations

from functools import lru_cache

from .guard import HITL_CODES, parse
from .ingest import load_documents
from .retrieve import Retriever


@lru_cache(maxsize=4)
def _retriever(mode: str = "hybrid") -> Retriever:
    return Retriever(load_documents(), mode=mode)


def ask(question: str, k: int = 4, mode: str = "hybrid", force: bool = False) -> dict:
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
    prefer = "run" if any(n.startswith("run=") for n in it.notes) else None
    hits = _retriever(mode).search(question, k=k, stage=it.stage, prefer_kind=prefer,
                                  allow_unmatched=force)
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
