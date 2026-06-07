# khan-interactive-data-analysis

交互式业务数据清洗与分析 Skill — 支持仅清洗、仅分析、先清洗再分析，以及会话恢复与回滚。

## What This Does

**khan-interactive-data-analysis** 帮助业务分析师处理原始数据（Excel、CSV、BI 明细表），从清洗到业务洞察全流程可追溯、每一步需用户确认。

清洗流程：自动检测表头行与数据区域，将汇总/备注等行标记为候选，用户确认后排除并写入审计 Tab，再交接给分析阶段。

分析流程：数据画像 → 异常识别 → 图表决策 → 十二步业务分析 → 生成结构化报告，支持 Markdown 和 HTML 导出。

### 核心特性

- **全程可回滚** — 检查点（Checkpoint A–E）与失效规则；用户可对任何结论提出质疑，触发从对应检查点重新执行
- **双确认门控** — 清洗结果确认、分析目标确认，两道关卡全部通过才能进入分析阶段
- **会话持久化** — 清洗状态在 `.cleaning-session/`，分析状态在 `.analysis-session/`，跨对话恢复
- **溯源透明** — 清洗输出含血缘列，跑 ID 写入交接文件，规则快照存档
- **图表评分制** — 图表候选按 8 项条件评分（+3 至 -3），根据阈值（≥6 必做、3–5 可选、<3 不做）自动筛选，不为凑数生成图表
- **异常分类处理** — 10 类异常（缺失值、重复行、零值、离群点、时间跨距等），三级严重度（blocking/warning/info），用户逐条确认处置方式
- **多入口路由** — 支持仅清洗、仅分析、端到端、恢复会话、修订决策、生成报告

## Installation

### Via Claude Code Custom Marketplace Source

安装到 Claude Code 运行的两个独立消息，分开发送：

```text
/plugin marketplace add https://github.com/forestfantacy/khan-interactive-data-analysis
```

安装完成后运行：

```text
/plugin install khan-interactive-data-analysis@khan-interactive-data-analysis
```

使用 HTTPS 链接。短格式 `forestfantacy/khan-interactive-data-analysis` 可能触发 SSH 访问，若 GitHub 未在 `known_hosts` 中注册会失败。

调用方式：在 Claude Code 中输入 `/khan-interactive-data-analysis:khan-interactive-data-analysis`。

Claude Code 会对插件安装的 Skill 加上命名空间前缀。

### Claude Code 手动安装

复制 Skill 文件到 Claude Code 技能目录：

```bash
mkdir -p ~/.claude/skills/khan-interactive-data-analysis/{scripts,references,templates,agents}
cp SKILL.md ~/.claude/skills/khan-interactive-data-analysis/
cp -R scripts/ references/ templates/ agents/ ~/.claude/skills/khan-interactive-data-analysis/
```

或直接克隆：

```bash
git clone https://github.com/forestfantacy/khan-interactive-data-analysis.git ~/.claude/skills/khan-interactive-data-analysis
```

调用方式：在 Claude Code 中输入 `/khan-interactive-data-analysis`（手动安装的 Standalone Skill 不加命名空间）。

### 其他 Coding Agent

Codex、Kimi Code、OpenCode、Gemini CLI 等本地助手也可以使用本 Skill。将此 GitHub 仓库链接发给 Agent，并要求它加载 `SKILL.md`：

```
https://github.com/forestfantacy/khan-interactive-data-analysis
```

Agent 应从 `SKILL.md` 开始，按需加载 `references/` 下的支持文件。

## Usage

```
/ khan-interactive-data-analysis:khan-interactive-data-analysis

> "帮我清洗这份销售数据报表，然后做业务分析"
```

入口路由（按优先级匹配）：

| 路由 | 说明 |
|------|------|
| `Cleaning Only` | 仅清洗，输出清洗后文件 |
| `Analysis Only` | 仅分析，输入已清洗数据 |
| `End-to-End` | 先清洗再分析，全流程 |
| `Resume Session` | 恢复清洗或分析会话 |
| `Revise Decision` | 对已有结论提出质疑，触发回滚重跑 |
| `Finalize Report` | 导出已生成的报告为 Markdown 或 HTML |

清洗阶段工作流：Intake → 结构画像 → 规则确认 → 异常门控 → 执行 → 确认交接 → 确认分析目标

分析阶段工作流：Intake → 数据画像 → 异常门控 → 图表决策 → 正式分析 → 协调 → 定稿

## 核心工作流

### 清洗流程（5 阶段）

```
Intake → 结构画像 → 规则确认 → 异常门控 → 执行
```

- **Intake**：接收原始文件，自动识别格式（CSV/XLSX）
- **结构画像**：检测表头行、数据区域和排除候选，处理同名列多文件标签页合并；候选经用户确认后才排除
- **规则确认**：展示干跑结果，用户确认清洗规则
- **异常门控**：列出 blocking 异常，优先处理后才能继续
- **执行**：写入清洗后文件，同时输出 profile.json、rules.json、dry-run.json、handoff.json

### 分析流程（7 阶段）

```
Intake → 数据画像 → 异常门控 → 图表决策 → 正式分析 → 协调 → 定稿
```

- **数据画像**：推断列角色（指标/维度/时间/标识符），计算缺失率、数值统计、日期范围
- **异常门控**：检测 10 类异常并分级，用户逐条确认处置方式后才能进入分析
- **图表决策**：6 类候选图表（趋势线/排名柱/堆叠柱/帕累托/箱线/散点），按 8 项条件评分筛选
- **正式分析**：12 步业务分析（业务场景 → 字段理解 → 指标体系 → 业务问题 → 数据质量 → 描述性分析 → 归因 → 假设 → 洞察 → 行动建议 → 监控 → 后续计划）
- **协调**：多角度验证洞察，剔除噪声
- **定稿**：生成结构化报告（13 个章节），导出 Markdown 和/或 HTML

### 异常分类（10 类）

| 类别 | 说明 | 默认处理 |
|------|------|----------|
| 缺失值 | 缺失率超阈值或关键字段缺失 | warning |
| 重复行 | 主键重复或全行重复 | blocking |
| 零值 | 数值字段零值率 ≥90% | warning |
| 混合类型 | 同一字段含多种数据类型 | blocking |
| 离群点 | IQR 方法检测，3 级严重度 | warning |
| 时间早于范围 | 日期早于业务时间窗口 | blocking |
| 时间晚于范围 | 日期晚于业务时间窗口 | warning |
| 时间跨距异常 | 日期跨度超过合理范围 | warning |
| 枚举值异常 | 枚举字段含未定义值 | info |
| 数据类型不一致 | 声明类型与实际不符 | warning |

## 架构

本 Skill 采用**渐进披露**设计——主文件 `SKILL.md` 是工作流地图，支持文件按需加载：

| 文件 | 用途 | 加载时机 |
|------|------|----------|
| `SKILL.md` | 核心工作流与规则 | 始终 |
| `references/cleaning-workflow.md` | 清洗五阶段详细协议 | 清洗阶段 |
| `references/session-schema.md` | 分析会话结构（session.json、runs/） | 分析阶段 |
| `references/cleaning-session-schema.md` | 清洗会话结构 | 清洗阶段 |
| `references/cleaning-handoff-schema.md` | 交接 JSON schema | 清洗→分析交接 |
| `references/anomaly-taxonomy.md` | 10 类异常分类与默认处理 | 异常门控 |
| `references/chart-decision-rules.md` | 图表评分表与阈值规则 | 图表决策 |
| `references/interaction-protocol.md` | 阶段交互协议与输出格式 | 全程 |
| `references/user-input-style.md` | 用户确认面板标准格式 | 全程确认面板 |
| `references/original-sop.md` | 12 步业务分析原始 SOP | 正式分析阶段 |
| `scripts/clean_tabular_data.py` | 核心清洗：表头检测、XLSX 写入 | 清洗执行 |
| `scripts/cleaning_store.py` | 清洗会话持久化 CLI | 会话管理 |
| `scripts/session_store.py` | 分析会话持久化 CLI | 会话管理 |
| `scripts/profile_dataset.py` | 数据画像 | 分析阶段 |
| `scripts/detect_anomalies.py` | 异常检测 | 分析阶段 |
| `scripts/decide_charts.py` | 图表评分与筛选 | 分析阶段 |
| `scripts/export_report.py` | 报告导出（MD/HTML） | 定稿阶段 |
| `templates/cleaning-review-template.md` | 清洗干跑确认模板 | 规则确认 |
| `templates/final-report-template.md` | 最终报告模板（13 节） | 定稿 |
| `templates/anomaly-review-template.md` | 异常确认卡片模板 | 异常门控 |
| `templates/checkpoint-summary-template.md` | 检查点摘要模板 | 阶段切换 |

## 设计哲学

本 Skill 源于以下信念：

1. **业务数据天然脏乱** — 原始导出的数据充满系统行、双语表头、汇总行、缺失值，业务分析师不应被数据清洗绊住脚步。
2. **信任需要可见** — 每一步推理都应展示给用户，数据质量结论可反驳、可回滚。
3. **机器擅长执行，人擅长判断** — 异常分类、规则推导由程序完成；异常处置、分析方向由用户确认。
4. **会话可恢复比一次跑完更重要** — 真实业务分析往往跨越多天、多轮对话，会话持久化是基本要求。
5. **检查点即契约** — 每个检查点是一次明确的状态承诺，任何上游变更都必须触发下游失效重跑。

## Requirements

- Python 3.x（用于脚本执行）
- pandas、openpyxl（数据分析与 Excel 处理）
- 本地 Coding Agent，含文件系统访问和 Shell 命令执行能力
- Claude Code 仅用于 Skill 安装与 `/khan-interactive-data-analysis:khan-interactive-data-analysis` 命令调用
- 其他 Agent 可直接读取 `SKILL.md` 并按需加载支持文件

## Credits

Created by [@forestfantacy](https://github.com/forestfantacy).

## License

MIT — Use it, modify it, share it.
