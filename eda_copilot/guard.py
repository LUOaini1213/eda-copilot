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
# 子串匹配会把 replace / global_place 也当成 place，所以单写的 place 要按词边界判。
# 只在上面的子串都没命中时才用（floorplan 在 place 之前判，不会被它抢走）。
_BARE_STAGE = {"place": re.compile(r"(?<![a-z_])place(?![a-z_])", re.I)}

HITL_CODES = {
    "OUT_OF_SCOPE": ("库外主题", "本库只有开源数字后端流程（OpenROAD/ORFS）的脚本与模块文档，没有 DRAM 阵列 / 工艺 / 器件内容"),
    "RUN_OUT_OF_SCOPE": ("运行不在库内", "本库只有 nangate45/gcd base 这一次真实运行，别的设计 / 别的 run 答不了"),
    "AMBIGUOUS_METRIC": ("双口径歧义", "「时序好不好 / 面积多大」在本领域对应多套指标，先说清是哪一个"),
    "MISSING_CORNER": ("缺时序检查类型", "时序问题必须说清 setup 还是 hold，两者结论常常相反"),
    "MISSING_STAGE": ("缺阶段", "同一个量在不同阶段的含义与可信度不同，先说清问的是哪一步"),
    "UNDEFINED_TERM": ("无口径措辞", "「优化一下 / 怎么样 / 好不好」没有可执行口径"),
    "RELATIVE_RUN": ("相对指代", "「上次那个 run / 最新的」没有版本锚点"),
}

FORCED_DEFAULT = {
    "OUT_OF_SCOPE": "丢弃不认识的主题词，退回全库检索",
    "RUN_OUT_OF_SCOPE": "拿本库唯一那次 run 的数值当成你问的那次",
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
    r"(wns|tns|slack|skew|drc|面积|利用率|实例数)\s*(是)?\s*多少|"
    r"跑出来|实际(结果|数值)|report 里(写|是)什么", re.I)

# 本库唯一收录的运行。gcd 是这个语料库的简称；显式给出的工艺、设计、
# 变体必须同时匹配，不能因为任一名称碰巧出现就借用这次运行的数值。
KNOWN_RUN = re.compile(r"(?<![\w.-])gcd(?![\w.-])", re.I)
_IDENT = r"[a-z][a-z0-9_.-]*"
_RUN_PATH = re.compile(rf"(?<![\w.-])({_IDENT})\s*/\s*({_IDENT})(?:\s*/\s*({_IDENT}))?", re.I)
_METRIC_PAIRS = {("setup", "hold"), ("hold", "setup"), ("wns", "tns"), ("tns", "wns")}
_PLATFORM = re.compile(r"\b(?:sky\d+[\w.-]*|asap\d+[\w.-]*|nangate\d+[\w.-]*|gf\d+[\w.-]*|ihp[\w.-]*|tsmc\d+[\w.-]*)\b", re.I)
_RUN_REFERENCE = re.compile(r"\brun\b|这次运行|本次运行|这次跑", re.I)


def _known_run(question: str) -> bool:
    if not KNOWN_RUN.search(question):
        return False
    for platform, design, variant in _RUN_PATH.findall(question.lower()):
        if (platform, design) in _METRIC_PAIRS and not variant:
            continue
        if (platform, design) != ("nangate45", "gcd") or variant not in ("", "base"):
            return False
    if any(p.lower() != "nangate45" for p in _PLATFORM.findall(question)):
        return False
    # Also recognize whitespace-qualified identities, including unseen PDK names.
    for qualifier in re.findall(rf"\b({_IDENT})\s+gcd\b", question, re.I):
        if qualifier.lower() not in {"nangate45", "run", "design", "the", "for", "of"}:
            return False
    for label, value in re.findall(
            rf"\b(platform|pdk|design|variant|run_id)\s*[:=]\s*({_IDENT})", question, re.I):
        expected = {"platform": "nangate45", "pdk": "nangate45", "design": "gcd",
                    "variant": "base", "run_id": "base"}[label.lower()]
        if value.lower() != expected:
            return False
    return True


# 明显是别的设计
OTHER_DESIGN = re.compile(r"我的设计|我这个设计|aes|ibex|jpeg|swerv|ariane|riscv|black\s*parrot|asap7", re.I)


def _names_other_run(question: str) -> bool:
    """问题里点名了别的设计或别的工艺（nangate45 之外的 PDK）。"""
    if OTHER_DESIGN.search(question):
        return True
    return any(p.lower() != "nangate45" for p in _PLATFORM_NAME.findall(question))


# 和 _PLATFORM 同一组 PDK 名，但边界只看 ASCII：中文紧贴着写（「在sky130上」）时
# \b 不成立，_PLATFORM 会漏掉。
_PLATFORM_NAME = re.compile(
    r"(?<![A-Za-z0-9_])(sky\d+|asap\d+|nangate\d+|gf\d+|ihp[A-Za-z0-9]*|tsmc\d+)", re.I)

_RELATIVE = re.compile(r"上次|上一次|最新的?那?个?\s*run|刚才那个|之前那个|last run|latest run", re.I)

_UNDEFINED = re.compile(r"优化一下|怎么样|好不好|行不行|帮我看看|有没有问题|正不正常", re.I)

# 文档/定义类问题：问的是「这个命令/参数是什么、怎么用、有哪些」，
# 不是问「我这次跑出来的数是多少」。这类问题不该被 setup/hold、阶段等
# 面向结果的护栏拦下——评测里 #6 #7 就是被误拦的。
_DOC_Q = re.compile(
    r"是什么|什么意思|怎么用|如何使用|干什么|作用是|定义|有哪些|哪些参数|哪些取值|"
    r"哪个命令|什么命令|怎么读写|怎么实现|用的什么|用什么算法|在哪个模块|"
    r"会报(告)?哪些|支持哪些|为什么要|为什么放在|什么条件下|什么时候执行|"
    # 英文问法。只收「问命令 / 选项 / 用法」的句式；"what is the wns" 这种问数值的
    # 不算文档题，仍要过 setup/hold 护栏。
    r"\bwhat\s+does\b|\bhow\s+(?:to|do|does|can|should)\b|"
    r"\bwhich\s+(?:command|option|parameter|flag|variable|argument|algorithm|module)s?\b|"
    r"\bwhat\s+(?:commands|options|parameters|flags|arguments|algorithm)\b|"
    r"\bwhat\s+is\s+(?:the\s+)?(?:purpose|meaning|definition|role)\b|"
    r"\bwhat\s+is\s+[a-z]+_[a-z0-9_]+|\bexplain\b|\blist\s+(?:the|all|of)\b", re.I)

_AMBIG_METRIC = re.compile(r"时序(好|怎么样|如何)|面积(多大|大不大)|性能(怎么样|好不好)|质量(怎么样|好不好)", re.I)
# 「面积是多少」同样有 die / core / 实例 三套；带了限定词才不算歧义
_AREA_VALUE = re.compile(r"面积\s*(是)?\s*多少|\barea\b.*\b(is|of)\b|what\s+is\s+the\s+area", re.I)
_AREA_QUALIFIED = re.compile(r"die|core|instance|stdcell|std\s*cell|macro|实例|标准单元|单元|芯片|核心|管芯", re.I)

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

    run_refusal = ("本库只收录了 **nangate45/gcd base** 这一次真实运行（跑到 6_final.gds）。"
                   "要问这次运行的数值，请在问题里写明 gcd（或 nangate45/gcd）；别的设计本库没有数据。")

    # 点名了别的设计 / 工艺、又不是问文档：本库没有那次运行，gcd 的产物不能拿来顶替。
    # 这一条必须在 _NEEDS_RUN 之前判——「ibex 的 cts 是怎么做的」不含数值词，
    # 以前会漏过 _NEEDS_RUN，直接拿 gcd 的 4_1_cts.json 带出处作答。
    other_run = _names_other_run(q)
    if not doc_q and other_run:
        if guard("RUN_OUT_OF_SCOPE", run_refusal):
            return it
    if doc_q and other_run:
        # 文档与设计无关，可以答；但运行产物属于 gcd，不能当成别的设计的证据
        it.notes.append("exclude=run")

    # 问具体数值：本库有且只有 nangate45/gcd base 这一次运行。
    # 问的是这次 -> 可以答；问的是别的设计 / 没指明是哪次 -> 停。
    if _NEEDS_RUN.search(q) or (not doc_q and _RUN_REFERENCE.search(q)):
        # force 模式下上面已经记过一次同样的猜测，这里不重复记账
        already = not doc_q and other_run
        if (other_run or not _known_run(q)) and not already:
            if guard("RUN_OUT_OF_SCOPE", run_refusal):
                return it
        it.notes.append("run=nangate45/gcd base")

    if _AMBIG_METRIC.search(q) or (not doc_q and _AREA_VALUE.search(q)
                                    and not _AREA_QUALIFIED.search(q)):
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
    else:
        for st, pat in _BARE_STAGE.items():
            if pat.search(q):
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
