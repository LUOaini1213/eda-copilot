# 语料来源与许可

本仓 `corpus/` 下的内容**不是本项目原创**，是为做检索评测而收录的第三方开源材料，
以及本人在本机跑出的运行产物。原样保留，未做改写。

| 目录 | 来源 | 许可 |
|---|---|---|
| `corpus/orfs_scripts/` | [The-OpenROAD-Project/OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) `flow/scripts/` | BSD 3-Clause |
| `corpus/openroad_docs/` | [The-OpenROAD-Project/OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) 各模块 `README.md` | BSD 3-Clause |
| `corpus/run_nangate45_gcd/`<br>`run_artifacts/` | 本人用官方镜像 `openroad/orfs` 跑 `nangate45/gcd` 产生的报告 / 日志 / 指标 / 版面图 | 见上（工具与工艺库均为 OpenROAD 项目提供） |

OpenROAD 与 Nangate45 开放工艺库的著作权归其各自作者所有。
收录目的仅为让检索评测可复现，不主张任何权利。

本仓**自有代码**（`eda_copilot/`、`eval/`、`scripts/`）以 MIT 许可发布，见 `LICENSE`。
