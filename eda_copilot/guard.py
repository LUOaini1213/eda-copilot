# -*- coding: utf-8 -*-
"""停问护栏。口径不清、超出语料范围、或需要本库根本没有的运行结果时，停下来问人，不猜。

设计原则和 malaysia-auto-ask 一致：宁可少答，不可给一个看起来对的错答。
在 EDA 场景里这条更重要——一个错误的时序归因可能让人去改错的约束。

parse(q)              正常模式：命中护栏就停。
parse(q, force=True)  消融模式：关掉护栏，按「没有护栏的系统」的朴素默认强行作答，
                      把每次猜测记进 guesses，供对照实验统计。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# 本库覆盖的流程阶段 -> 关键词
STAGES = {
    "floorplan": ["floorplan", "die area", "core area", "utilization", "布局规划", "面积规划"],
    "place": ["global place", "detail place", "placement", "布局", "gpl", "dpl"],
    "cts": ["cts", "clock tree", "skew", "时钟树", "时钟偏斜"],
    "route": ["global route", "detail route", "routing", "congestion", "drc", "绕线", "布线", "拥塞"],
    "synth": ["synthesis", "yosys", "abc", "综合"],
    "resize": ["resize", "repair_timing", "buffer", "修时序"],
}

HITL_CODES = {
    "OUT_OF_SCOPE": ("库外主题", "本库只有开源数字后端流程（OpenROAD/ORFS）的脚本与模块文档，没有 DRAM 阵列 / 工艺 / 器件内容"),
    "NO_RUN_DATA": ("无运行数据", "本库没有任何一次真实 P&R 运行的结果，答不了具体数值"),
    "AMBIGUOUS_METRIC": ("双口径歧义", "「时序好不好 / 面积多大」在本领域对应多套指标，先说清是哪一个"),
    "MISSING_CORNER": ("缺时序检查类型", "时序问题必须说清 setup 还是 hold，两者结论常常相反"),
    "MISSING_STAGE": ("缺阶段", "同一个量在不同阶段的含义与可信度不同，先说清问的是哪一步"),
    "UNDEFINED_TERM": ("无口径措辞", "「优化一下 / 怎么样 / 好不好」没有可执行口径"),
    "RELATIVE_RUN": ("相对指代", "「上次那个 run / 最新的」没有版本锚点"),
}

FORCED_DEFAULT = {
    "OUT_OF_SCOPE": "丢弃不认识的主题词，退回全库检索",
    "NO_RUN_DATA": "拿文档里的示例数值当作实际结果",
    "AMBIGUOUS_METRIC": "默认取 WNS",
    "MISSING_CORNER": "默认按 setup 答",
    "MISSING_STAGE": "默认按 floorplan 答",
    "UNDEFINED_TERM": "丢弃无口径修饰词，退回全库检索",
    "RELATIVE_RUN": "假定指最后一个阶段",
}


@dataclass
class Intent:
    topic: str | None = None
    stage: str | None = None
    metric: str | None = None
    check_type: str | None = None          # setup / hold
    hitl: bool = False
    hitl_code: str = ""
    hitl_reason: str = ""
    guesses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# 明确不在语料里的主题（DRAM 器件/工艺/良率数据、模拟、封装）
_OUT_OF_SCOPE = re.compile(
    r"dram\s*(阵列|cell|array|电容|刷新|refresh)|字线|位线|word\s*line|bit\s*line|"
    r"光刻|刻蚀|薄膜|离子注入|良率数据|wafer\s*map|晶圆图|封装|bonding|"
    r"运放|模拟电路|adc|pll\s*设计", re.I)

_NEEDS_RUN = re.compile(
    r"(我的|这个|本|该)?\s*(设计|design|run|跑的?)\s*.*(是多少|多少|结果|数值)|"
    r"(wns|tns|slack|skew|drc|面积|利用率)\s*(是)?\s*多少|"
    r"跑出来|实际(结果|数值)|report 里(写|是)什么", re.I)

_RELATIVE = re.compile(r"上次|上一次|最新的?那?个?\s*run|刚才那个|之前那个|last run|latest run", re.I)

_UNDEFINED = re.compile(r"优化一下|怎么样|好不好|行不行|帮我看看|有没有问题|正不正常", re.I)

# 文档/定义类问题：问的是「这个命令/参数是什么、怎么用、有哪些」，
# 不是问「我这次跑出来的数是多少」。这类问题不该被 setup/hold、阶段等
# 面向结果的护栏拦下——评测里 #6 #7 就是被误拦的。
_DOC_Q = re.compile(
    r"是什么|什么意思|怎么用|如何使用|干什么|作用是|定义|有哪些|哪些参数|哪些取值|"
    r"哪个命令|什么命令|怎么读写|怎么实现|用的什么|用什么算法|在哪个模块|"
    r"会报(告)?哪些|支持哪些|为什么要|为什么放在|什么条件下|什么时候执行", re.I)

_AMBIG_METRIC = re.compile(r"时序(好|怎么样|如何)|面积(多大|大不大)|性能(怎么样|好不好)|质量(怎么样|好不好)", re.I)

_TIMING = re.compile(r"slack|wns|tns|时序|timing|建立|保持", re.I)
_SETUP = re.compile(r"setup|建立时间|max\s*delay|path_delay\s*max", re.I)
_HOLD = re.compile(r"hold|保持时间|min\s*delay|path_delay\s*min", re.I)


def parse(question: str, force: bool = False) -> Intent:
    q = (question or "").strip()
    low = q.lower()
    it = Intent()

    def guard(code: str, reason: str) -> bool:
        """命中护栏。正常模式记 hitl 让调用方返回；force 模式只记账，继续往下猜。"""
        if force:
            it.guesses.append(f"{code}: {FORCED_DEFAULT[code]}")
            if not it.hitl_code:
                it.hitl_code = code
            return False
        it.hitl = True
        it.hitl_code = code
        it.hitl_reason = reason
        return True

    doc_q = bool(_DOC_Q.search(q))
    it.notes.append("doc_q" if doc_q else "result_q")

    if _OUT_OF_SCOPE.search(q):
        if guard("OUT_OF_SCOPE", HITL_CODES["OUT_OF_SCOPE"][1] + "。请换成流程/脚本/命令相关的问题。"):
            return it

    # 相对指代比「无口径措辞」更具体，必须先判，否则「上次那个 run 怎么样」会被记成后者
    if _RELATIVE.search(q):
        if guard("RELATIVE_RUN", "本库不保存运行历史。请直接说阶段与指标名。"):
            return it

    if _NEEDS_RUN.search(q):
        if guard("NO_RUN_DATA", "本库只有脚本与文档，**没有跑过任何一次 P&R**，给不出你这个设计的实际数值。"):
            return it

    if _AMBIG_METRIC.search(q):
        if guard("AMBIGUOUS_METRIC", "时序至少有 WNS / TNS / worst slack 三套；面积至少有 die area / core area / utilization 三套。请指定。"):
            return it

    if _UNDEFINED.search(q) and not doc_q:
        if guard("UNDEFINED_TERM", "请指定阶段（floorplan/place/cts/route）、指标（WNS/TNS/skew/DRC 数）和你要的是定义还是命令。"):
            return it

    # 阶段识别
    for st, kws in STAGES.items():
        if any(k in low for k in kws):
            it.stage = st
            break

    # 下面两条只针对「问结果」的问题。问文档的不需要 corner，也不需要先说阶段。
    if not doc_q:
        if _TIMING.search(q):
            if _SETUP.search(q) and not _HOLD.search(q):
                it.check_type = "setup"
            elif _HOLD.search(q) and not _SETUP.search(q):
                it.check_type = "hold"
            elif _SETUP.search(q) and _HOLD.search(q):
                it.check_type = "both"
            else:
                if guard("MISSING_CORNER", "setup 和 hold 的修复手段相反（加 buffer 修 hold 会恶化 setup）。请说清问哪一个。"):
                    return it
                it.check_type = "setup"

        if it.stage is None and re.search(r"报告|report|metric|指标|参数|怎么设|怎么调", q, re.I):
            if guard("MISSING_STAGE", "请说清是哪一步：floorplan / place / cts / route / synth。"):
                return it
            it.stage = "floorplan"

    it.topic = q
    return it
