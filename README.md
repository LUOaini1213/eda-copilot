# EDA Copilot

[![ci](https://github.com/LUOaini1213/eda-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/LUOaini1213/eda-copilot/actions/workflows/ci.yml)

**In one paragraph (EN)** — a question-answering system over the real scripts and
module docs of an open-source digital back-end flow (OpenROAD / ORFS), plus the
reports, logs and per-stage metrics of one RTL→GDSII run I executed myself
(nangate45/gcd, 986 instances, 284 s of wall-clock across 19 stage logs). Answers
are retrieved passages with citations down to file and line. The part that
matters: when a question lacks the premise that decides the answer — setup or
hold? WNS or TNS? *which* run? — the system **stops and asks** with one of 7
structured reason codes instead of guessing. 23 retrieval cases: Hit@5 22/23;
12 stop cases: 12/12 stopped with the right code; with the guard off, all 12 are
answered *with citations*, which is exactly why the guard exists. Offline, no
model, no key.

在开源数字后端流程（OpenROAD / ORFS）的**真实脚本与文档**上做的问答系统。
一句话进来，只回答语料支撑得住的问题；**口径不清、超出语料、或需要本库根本没有的运行结果时，停下来问人，不猜**。

语料里包含**本人跑通的一次真实 RTL→GDSII 运行**的报告、日志与逐阶段结构化指标。
离线运行，**零 token、零费用**，全程不接大模型。

Windows / PowerShell（后续命令均在激活后的虚拟环境内执行）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
python -m eda_copilot.cli "cts 的 sink clustering 是干什么的"
python eval/run_eval.py      # 检索评测 + 停问评测，写回 eval/results.json
python eval/ablation.py      # 关掉护栏的对照实验，写回 eval/ablation.json
python eval/run_eval.py --check   # 只比对：新跑对不上已提交的产物就退出码 1（CI）
python eval/ablation.py --check   # 同上（CI）
python -m unittest discover -s tests -v   # 护栏逐条断言 + 产物与 README 数字回算（CI）
```

macOS / Linux：创建环境后运行 `source .venv/bin/activate`，再运行
`python -m pip install -r requirements.txt` 和上面的问答、评测命令。
如果 PowerShell 的执行策略不允许激活，可以把上面每条 `python` 换成
`.\.venv\Scripts\python.exe`，无需修改系统执行策略。

一个带出处的回答，和一次停问：

```text
$ python -m eda_copilot.cli "本次 run 的 setup tns 是多少"
[停下来问人 · 运行不在库内] 本库只收录了 **nangate45/gcd base** 这一次真实运行（跑到 6_final.gds）。要问数值，请指明是这次运行；别的设计本库没有数据。

$ python -m eda_copilot.cli "时序好不好"
[停下来问人 · 双口径歧义] 时序至少有 WNS / TNS / worst slack 三套；面积至少有 die area / core area / utilization 三套。请指定。
```

![Final layout of the nangate45/gcd run rendered by OpenROAD: placement, routing and the clock tree of all 986 instances](run_artifacts/final_all.webp)

*语料所依据的那次运行：`openroad/orfs` 官方镜像，nangate45/gcd，986 个实例，19 个阶段日志累计 284 s。更多版面图（拥塞、IR drop、最差路径）在 `run_artifacts/`。*

---

## 1. 为什么做这个

EDA 流程问答有一个特别的失败模式：**问题看起来有答案，其实缺了决定答案的那个前提。**

- 「slack 为什么是负的」——**setup 还是 hold？两者的修复手段方向相反**，
  插 buffer 修 hold 会让 setup 更差。猜错一个，给出的建议正好反向。
- 「时序好不好」——WNS（最差一条）还是 TNS（违例总量）？
  WNS 差 TNS 小是单条路径问题，WNS 一般 TNS 大是全局问题，两种结论要做的事完全不同。
- 「我的设计 WNS 是多少」——**本库只有 nangate45/gcd base 这一次 P&R**，无法回答其他设计或运行的数值。

一个不停问的系统会把这些都答出来，而且**答得带出处**——这比裸奔的模型更危险，
因为出处让人相信它。本项目把「什么时候不该答」做成了系统的一等公民，并**量化了这么做的价值**。

## 2. 语料（全部真实，可复查）

> 语料是第三方开源材料 + 本人运行产物，**非本项目原创**，来源与许可见 [`NOTICE.md`](NOTICE.md)。自有代码为 MIT。

| 目录 | 内容 | 数量 |
|---|---|---|
| `corpus/orfs_scripts/` | OpenROAD-flow-scripts 的流程驱动脚本（TCL 源码） | 16 个文件 |
| `corpus/openroad_docs/` | OpenROAD 各模块 README（ifp/gpl/dpl/cts/grt/drt/rsz/ppl/mpl/stt/pdn/tap/gui/odb/par） | 15 个文件 |
| `corpus/run_nangate45_gcd/` | **本人跑通的一次真实运行**的报告 / 日志 / 逐阶段 metric JSON | 46 个文件 |

**那次运行是真的：**用官方镜像 `openroad/orfs` 在 WSL2 里跑 `nangate45/gcd`，
约 5 分钟走完 yosys 综合 → floorplan → tapcell/PDN → place → CTS → 全局/详细布线 → fill →
`6_final.gds`。复现见 `scripts/run_orfs_flow.sh`，版面图在 `run_artifacts/`。
关键结果：**TNS(setup) = −7.18，WNS(setup) = −0.16**，实例数 986，利用率 0.880。

**从自己产出的报告里读出的三条结论**（文件与行号可直接核对）：

1. **违例是全局的，不是单条路径的。**`6_report.json` 第 30 行 `finish__timing__setup__tns = −7.18`，`6_finish.rpt` 里 WNS(setup) = −0.16，比值约 45——违例摊在几十条路径上，只修最差那条没用。
2. **为修时序插的 buffer 已占标准单元面积 18.7%，时序仍未收敛。**`6_report.json` 第 16–17 行：`timing_repair_buffer` 184 个、176.89 µm²；第 55 行标准单元实例面积 947.758 µm²，176.89 / 947.758 = 18.7%。
3. **报告正文和结构化指标对同一个量给出不同精度。**`6_finish.rpt` 第 31 行印的是 `0.00 setup skew`，`6_report.json` 第 36 行 `finish__clock__skew__setup = 0.000896484`。看报告正文会以为 skew 为零，看指标才知道是 0.9 ps 量级。

切块后 **1215 块**，平均 785 字符（`eda_copilot.ingest` 统计；加入运行产物前是 438）。
`.md` 按标题切并保留标题链，`.tcl` 按语义段切并**保留起止行号**——所以出处能精确到
`orfs_scripts/cts.tcl :: 18-27`。

## 3. 停问机制：7 类结构化原因码

不用自由文本写「我不确定」，而是给结构化 `hitl_code`，让停问本身可统计、可评测。

| 原因码 | 中文 | 触发场景 |
|---|---|---|
| `OUT_OF_SCOPE` | 库外主题 | 问 DRAM 阵列 / 工艺 / 晶圆图——本库只有数字后端 |
| `RUN_OUT_OF_SCOPE` | 运行不在库内 | 本库**只有 nangate45/gcd base 这一次**运行；问别的设计的数值要停 |
| `AMBIGUOUS_METRIC` | 双口径歧义 | 「时序好不好」「面积多大」 |
| `MISSING_CORNER` | 缺时序检查类型 | 时序问题没说 setup / hold |
| `MISSING_STAGE` | 缺阶段 | 问参数/报告但没说哪一步 |
| `UNDEFINED_TERM` | 无口径措辞 | 「优化一下」「帮我看看」 |
| `RELATIVE_RUN` | 相对指代 | 「上次那个 run」 |

**一个关键设计：文档类问题不走面向结果的护栏。**
「`repair_timing` 有哪些 sequence 取值」问的是文档，不是我这次跑出来的数，
不该因为句子里有 "timing" 就被要求先说 setup/hold。这条是**评测逼出来的**（见 §5）。

## 4. 评测结果

### 4.1 检索（23 题，人工标注期望出处）

| 检索器 | Hit@5 | Hit Rate | MRR |
|---|---|---|---|
| **bm25（默认）** | **22/23** | **0.9565** | **0.7841** |
| hybrid | 22/23 | 0.9565 | 0.7746 |
| tfidf | 21/23 | 0.9130 | 0.7514 |

这组结果于 2026-09-12 重跑，题目和金标未变。修复了运行身份校验、
补全带 `run / 这次运行` 的结果意图路由，并过滤 BM25 的零相关候选。

**默认检索器由此退回 bm25。**两者的 Hit@5 已经打平（都是 22/23）；MRR 上 bm25 高
0.0095，但本仓对 MRR 声明的复现容差就是 0.01（§5：换一套 BLAS，同一份代码算出的
hybrid MRR 在 0.7130 与 0.7109 之间摆动），所以这 0.0095 也不足以反过来说
「bm25 更好」。两个方向都拿不出增益——而 [`docs/PRD.md`](docs/PRD.md) 的验收标准第 5
条写的是「额外组件必须在评测上拿出增益，否则**不进默认路径**」。融合就是那个额外
组件，于是它退出默认路径。三档检索器仍可用 `--mode` 切换，评测每次三档都跑。

**这个默认值改过两次，两次都是评测改的；两组历史数都留在下面，没有只留最后那个。**

语料只有脚本 + 文档时（20 题），bm25 Hit@5 19/20、MRR **0.7892**，
hybrid 19/20、MRR **0.7700**（提交 `5ddddcf` 的 `eval/results.json`，可回查）——
融合拿不出增益，默认设成 bm25，当时写的理由是「多一个组件就多一处要解释的行为」。

加入真实运行产物之后，语料从同质（全是文档）变成异质（文档 + 报告 + 日志 +
metric JSON），两路检索的互补性开始体现，hybrid 在 Hit@5 上反超
（22/23 vs 21/23，提交 `d2e3e4e`），默认改成 hybrid。
（注意 MRR 上 bm25 当时就仍略高 0.7188 vs 0.7130——**两个指标不一致时按 Hit@5 选**，
因为本系统给用户看的是 top-k 证据列表，不是只看第一条。这个取舍写在这里，不藏。）
修好运行身份校验与结果意图路由后（提交 `dc105bf`），bm25 的 Hit@5 追平到 22/23，
那次反超随之消失——于是按同一条第 5 条，默认再退回 bm25。

> 组件有没有用**取决于语料，不能一次定终身**。换了语料就得重测。

**早期 CI 也暴露了跨平台差异。** 修复前的数值在我的笔记本上稳定复现，
推上去之后 ubuntu-latest 的 runner 算出 hybrid MRR **0.7109**，不是 0.7130。
查下来是第 32 题：它的正解落在第 4 名（融合分 0.029080），第 5 名是 0.029040，
**两者只差 4e-5**。换一套 BLAS，TF-IDF 余弦的末位不同，这一对就换了位置，
MRR 相应动 1/4 − 1/5 摊到 23 题 = 0.0022。顺带发现排序本身也不稳：
`argsort` 默认 quicksort，同分文档的先后随实现而变——现在并列一律按文档下标定序。
**Hit@5、Hit Rate、停问计数在两台机器上完全一致**，会动的只有「正解在 top-5 里排第几」。
所以测试对序数事实严格相等、对 MRR 留 0.01 的容差，理由写在 `tests/test_eval_reproduces.py` 里。
**「可复现」这四个字，得说清楚复现的是哪一部分。**
> 我把翻转前后的两组数都留在这里，而不是只留下最后那个好看的。

**还有一处是意图路由。**加入运行产物后 `#31 #32`（问本次 run 的 TNS/WNS）
一开始检索不到——因为设计名 `gcd` / `nangate45` 出现在文件名和流程配置里，
**却不出现在报告正文里**，纯词法检索被这些词带偏。
修法是复用护栏已经解析出的意图：判定为「问本次 run 的数值」时给运行产物加权
（`prefer_kind`），而不是再写一套判断。

**还修了一处语料噪声。**每个阶段的日志开头都有一份一模一样的 OpenROAD 版本横幅 +
许可证 + 读库命令，这种样板块对任何查询都「有点像」，会挤掉真正有内容的块——
演示时问「本次 run 的 setup TNS」，top-1 命中的竟是某个阶段日志的横幅。
当时在切块阶段丢掉纯样板块（1231 → 1215 块）后，top-1 变成
`6_finish.rpt :: 2-10`（正是 `tns max -7.18` 那一段），MRR 从 0.699 提到 0.713。
**这是删语料噪声，不是删难题。**

默认 bm25 未命中的 1 题：`#16 odb 数据库怎么读写`，三种检索器都没把 `odb_README.md` 排进 top-5，
被 `flow.tcl` 里大量出现的 `odb` 字样淹掉。**如实记录，未做针对性修补。**

### 4.2 停问（12 题）

| | 结果 |
|---|---|
| 该停的停住 | **12/12** |
| 原因码判对 | **12/12** |

**其中一条是评测反过来纠正了我。**我原本写了个用例
「`gcd` 这次 run 的 tns 是多少」并期望它能答，结果被 `MISSING_CORNER` 拦下。
查了自己跑出来的报告才发现**护栏是对的**——`report_metrics.tcl` 里
setup 和 hold 各报一套 TNS，不指明问哪个本来就该停。
于是我把用例改成「setup tns」，另外**新增一条期望它停的用例**。

### 4.3 消融对照：关掉护栏会怎样

同一批题跑两次，A 护栏开 / B 护栏关（`--force`）：

| | A 护栏开 | B 护栏关 |
|---|---|---|
| 该停的停住 | 12/12 | **0/12** |
| 强行作答 | — | **12/12** |
| 无提示猜测 | 0 | **12/12** |
| 对 23 题正常问答的回归 | — | **0** |

**危害分级：**

| 危害 | 数量 | 含义 |
|---|---|---|
| `TOPIC_DRIFT` | 4 | 问的主题不在库里，答的是别的东西（`OUT_OF_SCOPE` 2 + `UNDEFINED_TERM` 2） |
| `METRIC_GUESSED` | 4 | 猜了一套指标（`AMBIGUOUS_METRIC` 2）或猜了 setup/hold（`MISSING_CORNER` 2——修复手段相反） |
| `WRONG_TARGET` | 2 | 指代/阶段错了（`RELATIVE_RUN` 1 + `MISSING_STAGE` 1） |
| `FABRICATED_FACT` | 2 | 拿本库唯一那次 run 的数值当成你问的那次（`RUN_OUT_OF_SCOPE` 2） |

数字直接来自 `eval/ablation.json`（`python eval/ablation.py --check` 会把一次新跑与它比对，CI 每次都跑）。此前这张表写的是 4 / 3 / 2 / 1：`ablation.py` 里 `RUN_OUT_OF_SCOPE` 的映射键写错，两条本该记为 `FABRICATED_FACT` 的题落成了 `UNKNOWN`，2026-09-03 修正。

**最值得看的一条：**关掉护栏后，「DRAM 的字线和位线怎么布」「晶圆图的缺陷模式怎么分类」
「帮我看看」「优化一下这个流程」**四题的 top-1 出处是同一段**——
`run_nangate45_gcd/6_report.log :: 61-71`，也就是本次运行的面积汇总
（那一段的正文是 `Design area 948 um^2 88% utilization`）。问 DRAM 阵列，答的是这颗
gcd 的面积，还带着行号。
而「我的设计 WNS 是多少」返回 `run_nangate45_gcd/6_finish.rpt :: 2-10`，
那一段的正文就是 `tns max -7.18` / `wns max -0.16`——**看起来完全正确，实际上完全错误**，
因为那是本库唯一那次 nangate45/gcd base 的数，不是提问者那次设计的数。
这十二条的出处逐条记在 `eval/ablation.json` 的 `top_cite` 字段里。

> **带出处的错答比裸奔的错答更危险。**出处让人停止怀疑。
> 这是我做这个项目最想说的一句话。

## 5. 评测抓出来的两个真 bug（没有藏）

第一次跑评测时检索只有 17/20，查下去发现是护栏误伤，不是检索差：

1. **`#6` `#7` 被误拦。**「`repair_timing` 有哪些 sequence 取值」「`report_metrics` 会报告哪些时序指标」
   都是文档类问题，却因为句子里含 "timing"/"时序" 被 `MISSING_CORNER` 拦下。
   → 修法：增加文档/定义类问题识别，这类问题跳过面向结果的护栏。
2. **`#25` 原因码判错。**「上次那个 run 的 skew 怎么样」报成 `UNDEFINED_TERM`（因为「怎么样」），
   应该是更具体的 `RELATIVE_RUN`。
   → 修法：护栏按「具体 → 笼统」重排优先级。

**这两条都是评测逼出来的，不是我读代码读出来的。**

## 6. 诚实边界

- 语料是**开源数字后端流程**（OpenROAD），**不是任何公司的内部流程**，也不是 DRAM 专用流程。
- 跑通的是 `nangate45/gcd`——ORFS 里最小的示例设计（**986 个实例**），开源 45nm 库，
  **全默认参数**，用的是官方 docker 镜像而非自建工具链。
  说「跑通了一次开源流程的完整 RTL→GDSII」是准确的；说「做过芯片后端」不是。
- 本库**只有这一次运行**。问别的设计的数值一律停问（`RUN_OUT_OF_SCOPE`）——
  这不是谦虚，是它真的没有那个数据。
- `gcd` 是本库唯一运行的简称；显式写出其他工艺、设计或运行变体时不能沿用这个简称。
  例如 `sky130/gcd 的 setup tns 是多少` 会停问；建议使用完整的 `nangate45/gcd/base`。
- BM25 / TF-IDF 都没有正相关候选时返回 `NO_EVIDENCE`；这只是词法证据门槛，
  不是语义正确性的保证。`--force` 消融模式显式关闭护栏与此证据门槛。
- 回答由**检索到的原文片段 + 出处**组装，**不接大模型生成**：`eda_copilot/` 里
  没有任何模型调用，也不读 API key，因此不存在可以打开的生成开关。
- 检索评测的 23 条期望出处是**我自己标的**，不是公开基准。
- 停问的 12 条用例也是我自己设计的，7 类原因码全部覆盖；停问「12/12 判对」的金标同样是本人标的。

## 7. 结构

```
eda_copilot/
  guard.py      停问护栏：7 类原因码 + force 消融模式
  ingest.py     语料切块（md 按标题、tcl 按语义段并保留行号）
  retrieve.py   bm25 / tfidf / hybrid 三种可切换检索器
  answer.py     编排：先过护栏，再检索，组装带出处的回答
  cli.py        命令行
eval/
  cases.json    35 条用例（23 检索 + 12 停问）
  run_eval.py   Hit@k / MRR / 停问准确率，三种检索器各跑一遍
  ablation.py   关掉护栏的对照实验 + 危害分级
tests/
  test_guard.py               12 条停问逐条断言原因码；23 条文档题不得被拦；force 模式必带出处与猜测记录
  test_eval_reproduces.py     eval/results.json 与 eval/ablation.json 必须等于一次新跑
scripts/
  run_orfs_flow.sh   在 WSL2 用官方镜像跑一次真实 RTL->GDSII 并拷出产物
corpus/         77 个真实文件（31 脚本+文档，46 本人运行产物）
run_artifacts/  那次运行的版面图（布局/布线/时钟树/拥塞/IR drop）
```
