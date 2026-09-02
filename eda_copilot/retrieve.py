# -*- coding: utf-8 -*-
"""检索层。三种可切换的检索器，用来做消融，而不是默认最花哨的那个。

  bm25    词法检索（rank_bm25，经 langchain-community 的 BM25Retriever）
  tfidf   字符 n-gram TF-IDF 余弦（sklearn），对中英混合与标识符更稳
  hybrid  上面两路的倒数排名融合（RRF）

默认是 bm25，不是 hybrid。理由见 eval/results.json：在本语料的 20 条检索题上
hybrid 的 Hit@5 与 bm25 打平（都是 19/20），MRR 反而更低（0.770 vs 0.789）。
既然融合拿不出增益，就不默认开——多一个组件就多一处要解释的行为。

EDA 语料里全是 set_global_routing_layer_adjustment 这种蛇形标识符，
默认按空格切词会把它当成一个不可再分的怪词。这里的分词器把标识符
同时保留「整体」和「拆开的词素」两种形态。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """标识符同时保留整体与词素；中文按二元切分。"""
    out: list[str] = []
    for tok in _WORD.findall(text.lower()):
        if "\u4e00" <= tok[0] <= "\u9fff":
            out.append(tok)
            out.extend(tok[i:i + 2] for i in range(len(tok) - 1))
            continue
        out.append(tok)
        if "_" in tok:
            out.extend(p for p in tok.split("_") if p)
    return out


@dataclass
class Hit:
    doc: Document
    score: float
    why: str

    @property
    def cite(self) -> str:
        m = self.doc.metadata
        loc = m.get("lines") or m.get("section") or ""
        return f"{m['source']}" + (f" :: {loc}" if loc else "")


class Retriever:
    def __init__(self, docs: list[Document], mode: str = "bm25"):
        assert mode in ("bm25", "tfidf", "hybrid")
        self.docs = docs
        self.mode = mode
        self._bm25 = BM25Retriever.from_documents(docs, preprocess_func=tokenize, k=50)
        self._vec = TfidfVectorizer(tokenizer=tokenize, lowercase=True, token_pattern=None,
                                    sublinear_tf=True, min_df=1)
        self._mat = self._vec.fit_transform(d.page_content for d in docs)
        # BM25Retriever 返回的是 Document 副本而非原对象，不能用 id() 回查，
        # 因此用 (来源, 定位, 正文) 组成稳定键。
        self._index = {self._key(d): i for i, d in enumerate(docs)}

    @staticmethod
    def _key(d: Document) -> tuple:
        m = d.metadata
        return (m.get("source"), m.get("lines") or m.get("section"), d.page_content)

    def _bm25_rank(self, q: str) -> list[int]:
        out = []
        for d in self._bm25.invoke(q):
            i = self._index.get(self._key(d))
            if i is not None:
                out.append(i)
        return out

    def _tfidf_rank(self, q: str, n: int = 50) -> list[int]:
        sims = cosine_similarity(self._vec.transform([q]), self._mat)[0]
        order = sims.argsort()[::-1][:n]
        return [int(i) for i in order if sims[i] > 0]

    def search(self, q: str, k: int = 5, stage: str | None = None) -> list[Hit]:
        if self.mode == "bm25":
            ranks = {"bm25": self._bm25_rank(q)}
        elif self.mode == "tfidf":
            ranks = {"tfidf": self._tfidf_rank(q)}
        else:
            ranks = {"bm25": self._bm25_rank(q), "tfidf": self._tfidf_rank(q)}

        # 倒数排名融合
        fused: dict[int, float] = {}
        for name, order in ranks.items():
            for pos, idx in enumerate(order):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (60 + pos)

        # 阶段命中给一个温和加成，不做硬过滤——硬过滤会在阶段判错时直接答不出来
        if stage:
            for idx in list(fused):
                if self.docs[idx].metadata.get("stage") == stage:
                    fused[idx] *= 1.25

        top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [Hit(self.docs[i], s, "+".join(ranks)) for i, s in top]
