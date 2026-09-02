# -*- coding: utf-8 -*-
"""把 corpus/ 下的真实 OpenROAD 语料切成带元数据的块。

语料三类：
  corpus/orfs_scripts/*.tcl        ORFS 流程驱动脚本（真实源码）
  corpus/openroad_docs/*.md        OpenROAD 各模块 README（真实文档）
  corpus/run_nangate45_gcd/*       **本人跑通的一次真实 RTL->GDSII 运行**的报告/日志/逐阶段 metric
                                   （nangate45/gcd base，openroad/orfs 官方镜像，跑到 6_final.gds）

切块策略按类型分开：
  .md   按 markdown 标题切，标题链保留进 metadata，便于给出处。
  .tcl  按空行分段再按行数上限兜底；TCL 的语义单元是「一段连续命令 + 它上面的注释」。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from langchain_core.documents import Document

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"

STAGE_BY_FILE = {
    "floorplan.tcl": "floorplan", "io_placement.tcl": "floorplan", "macro_place_util.tcl": "floorplan",
    "global_place.tcl": "place", "detail_place.tcl": "place", "resize.tcl": "resize",
    "cts.tcl": "cts", "global_route.tcl": "route", "detail_route.tcl": "route",
    "synth.tcl": "synth", "report_metrics.tcl": "report", "final_outputs.tcl": "report",
    "flow.tcl": "flow", "util.tcl": "flow", "load.tcl": "flow", "README.md": "flow",
    "ifp_README.md": "floorplan", "mpl_README.md": "floorplan", "ppl_README.md": "floorplan",
    "gpl_README.md": "place", "dpl_README.md": "place", "rsz_README.md": "resize",
    "cts_README.md": "cts", "grt_README.md": "route", "drt_README.md": "route",
    "stt_README.md": "route", "pdn_README.md": "floorplan", "tap_README.md": "floorplan",
    "par_README.md": "flow", "odb_README.md": "flow", "gui_README.md": "flow",
}


# 本库目前只有这一次真实运行。护栏要靠它区分「问的是这次 run」还是「问的是别的设计」。
RUN_ID = "nangate45/gcd base"

_RUN_STAGE_PREFIX = [
    ("1_", "synth"), ("2_", "floorplan"), ("3_", "place"),
    ("4_", "cts"), ("5_", "route"), ("6_", "report"),
]


# 每个阶段的日志开头都有一份一模一样的 OpenROAD 版本横幅 + 许可证 + 读库命令。
# 这种样板块在所有阶段重复出现，对任何查询都「有点像」，会挤掉真正有内容的块。
# 这不是为了刷指标去删难题，是在删语料噪声。
_BOILERPLATE = (
    "This program is licensed under the BSD-3 license",
    "Features included (+) or not (-)",
    "[INFO ODB-0227]",
)


def _is_boilerplate(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if any(b in t for b in _BOILERPLATE):
        # 只有当这一块几乎全是样板（没有实质指标行）时才丢
        return not any(c in t for c in ("tns", "wns", "slack", "skew", "violation", "= "))
    return False


def _stage_from_run_name(name: str) -> str:
    for pre, st in _RUN_STAGE_PREFIX:
        if name.startswith(pre):
            return st
    return "other"


def _split_md(text: str, max_chars: int = 1400):
    """按标题切，标题链带进块首，超长再按段落二次切。"""
    lines = text.split("\n")
    blocks, cur, chain = [], [], []
    def flush():
        if cur and any(l.strip() for l in cur):
            blocks.append(("　>　".join(chain), "\n".join(cur).strip()))
    for ln in lines:
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            flush(); cur = []
            lvl = len(m.group(1)); title = m.group(2).strip()
            chain = chain[: lvl - 1] + [title]
        cur.append(ln)
    flush()
    out = []
    for head, body in blocks:
        if len(body) <= max_chars:
            out.append((head, body)); continue
        parts, buf = [], []
        for para in body.split("\n\n"):
            if sum(len(x) for x in buf) + len(para) > max_chars and buf:
                parts.append("\n\n".join(buf)); buf = []
            buf.append(para)
        if buf: parts.append("\n\n".join(buf))
        out.extend((head, p) for p in parts)
    return out


def _split_tcl(text: str, max_lines: int = 40):
    """空行分段；过长段按行数硬切。保留起止行号，出处能精确到行。"""
    lines = text.split("\n")
    chunks, start = [], 0
    cur = []
    for i, ln in enumerate(lines):
        if ln.strip() == "" and len(cur) >= 6:
            chunks.append((start + 1, i, "\n".join(cur))); cur = []; start = i + 1
            continue
        if ln.strip() == "" and not cur:
            start = i + 1; continue
        cur.append(ln)
        if len(cur) >= max_lines:
            chunks.append((start + 1, i + 1, "\n".join(cur))); cur = []; start = i + 1
    if any(l.strip() for l in cur):
        chunks.append((start + 1, len(lines), "\n".join(cur)))
    return [(a, b, c) for a, b, c in chunks if c.strip()]


def load_documents() -> list[Document]:
    docs: list[Document] = []
    for sub, kind in (("orfs_scripts", "tcl"), ("openroad_docs", "doc"), ("run_nangate45_gcd", "run")):
        d = CORPUS / sub
        if not d.is_dir():
            continue
        for fp in sorted(d.iterdir()):
            if not fp.is_file():
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
            stage = STAGE_BY_FILE.get(fp.name) or _stage_from_run_name(fp.name)
            rel = f"{sub}/{fp.name}"
            if kind == "run":
                for a, b, body in _split_tcl(text, max_lines=30):
                    if _is_boilerplate(body):
                        continue
                    docs.append(Document(page_content=body, metadata={
                        "source": rel, "kind": kind, "stage": stage,
                        "run": RUN_ID, "lines": f"{a}-{b}"}))
                continue
            if fp.suffix == ".md":
                for head, body in _split_md(text):
                    docs.append(Document(page_content=body, metadata={
                        "source": rel, "kind": kind, "stage": stage, "section": head}))
            else:
                for a, b, body in _split_tcl(text):
                    docs.append(Document(page_content=body, metadata={
                        "source": rel, "kind": kind, "stage": stage, "lines": f"{a}-{b}"}))
    return docs


if __name__ == "__main__":
    ds = load_documents()
    print(f"{len(ds)} chunks")
    from collections import Counter
    print("按类型:", Counter(d.metadata["kind"] for d in ds))
    print("按阶段:", Counter(d.metadata["stage"] for d in ds).most_common())
    print("平均长度:", round(sum(len(d.page_content) for d in ds) / len(ds)))
