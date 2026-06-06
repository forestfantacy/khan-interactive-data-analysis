---
name: khan-interactive-data-analysis
description: 交互式 Excel/CSV 业务数据清洗与分析 Skill。支持仅清洗、仅分析、先清洗再分析，以及恢复或回退已有会话。用于识别表头和真实数据区、确认清洗规则并输出新文件，也用于数据画像、异常确认、业务分析、图表判定和报告导出。适用于 Excel、CSV、经营报表、BI 明细表、数据库导出等需要可确认、可回退、可重跑和全程追溯的场景。
---

# 交互式业务数据清洗与分析

统一处理数据清洗和业务分析。根据用户意图进入清洗阶段、分析阶段或完整流程，不再依赖其他 skill。

## Core Rules

1. 原始文件只读；清洗输出不得覆盖任一输入文件。
2. 清洗正式写文件前必须完成 dry-run 和用户确认。
3. 完整流程必须在清洗结果确认、分析目标确认两个节点分别停止并等待用户下一条消息。
4. 正式分析前必须完成数据画像和异常闸门；阻断型异常未决时不得输出业务归因或建议。
5. 清洗阶段不输出业务洞察，分析阶段不直接修补清洗结果。
6. 用户不认可结果时必须回到对应检查点重跑，不允许只改输出文案或手工修改结果文件。
7. 清洗状态写入 `.cleaning-session/`，分析状态写入 `.analysis-session/`。
8. 所有需要用户回答的内容使用 [references/user-input-style.md](references/user-input-style.md) 的独立确认面板。

## Entry Routing

每轮先识别入口：

- `Cleaning Only`：用户明确要求清洗、整理、合并或标准化原始 Excel/CSV。
- `Analysis Only`：用户要求分析已有结构化文件，不要求先清洗。
- `End-to-End`：用户要求“先清洗再分析”“完整流程”或从原始报表生成最终洞察。
- `Resume Session`：数据目录存在 `.cleaning-session/` 或 `.analysis-session/`。
- `Revise Decision`：用户质疑表头、范围、口径、异常或结论，要求回退重跑。
- `Finalize Report`：当前分析 run 已被用户接受，需要导出最终报告。

路由优先级：

1. 用户明确要求回退或定稿时，优先执行该操作。
2. 存在未完成会话时优先恢复，不重复初始化。
3. 同时存在两个会话目录时：
   - 新清洗 run 尚未确认，或其 `cleaning_run_id` 与当前分析前提不一致：恢复清洗阶段。
   - 清洗交接已确认但分析未完成：恢复分析阶段。
   - 两个阶段都已完成：按用户本轮明确意图路由。
4. 没有会话时按用户意图选择 `Cleaning Only`、`Analysis Only` 或 `End-to-End`。

## Cleaning Stage

仅在 `Cleaning Only`、`End-to-End` 或清洗阶段恢复/回退时执行。

详细流程、检查点和命令读取 [references/cleaning-workflow.md](references/cleaning-workflow.md)，会话结构读取 [references/cleaning-session-schema.md](references/cleaning-session-schema.md)。

### Cleaning Invariants

- 不固定表头或数据起始行，使用结构特征和连续数据区识别。
- 多文件或多 sheet 字段不一致时必须阻断，除非用户提供明确规则。
- 同名 Tab 只比较同名 Tab 的表头；表头一致时必须询问合并或分别保留。
- dry-run 必须展示表头、数据区、排除行、预计输出行数、置信度和识别依据。
- 执行时使用已确认的 `.cleaning-session/rules.json`。
- 成功后生成 `.cleaning-session/handoff.json`。

初始化和 dry-run：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py init \
  --session-dir .cleaning-session \
  --inputs <raw-file-or-files> \
  --output <cleaned-output.xlsx> \
  --target-sheet 原始数据_清洗后 \
  --goal "<cleaning-goal>"

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/clean_tabular_data.py <raw-file-or-files> \
  --output <cleaned-output.xlsx> \
  --target-sheet 原始数据_清洗后 \
  --profile-output .cleaning-session/profile.json \
  --rules-output .cleaning-session/rules.json \
  --run-output .cleaning-session/dry-run.json
```

按 [templates/cleaning-review-template.md](templates/cleaning-review-template.md) 展示结果。用户确认规则后才允许执行。

### Cleaning Result Gate

清洗文件写出后，本轮必须停止。向用户报告：

- 清洗后文件绝对路径
- 输出工作表列表
- 每个输出 Tab 的来源行数和合并总行数
- 原文件未修改
- 规则已记录
- warning 摘要

然后要求用户选择确认并继续分析、返回调整规则或暂停。即使用户最初要求完整流程，也不得在同一轮自动进入分析。

用户下一条消息确认后运行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py confirm-handoff \
  --session-dir .cleaning-session
```

`Cleaning Only` 到此完成。`End-to-End` 继续进入分析目标确认。

### Analysis Goal Gate

清洗结果确认后，单独展示并确认：

- 分析目标
- 决策对象 / 报告使用者
- 重点关注指标或异常
- 输出深度：简要 / 标准 / 深入
- 图表模式：自动判定 / 不出图 / 需要图表
- 报告格式：Markdown / HTML / Markdown + HTML
- 业务背景
- 分析 Tab 范围

本轮再次停止，不执行数据画像。用户在后续消息确认后运行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py confirm-analysis-goal \
  --session-dir .cleaning-session \
  --goal "<analysis-goal>" \
  --decision-object "<decision-object>" \
  --focus "<focus>" \
  --output-depth <简要|标准|深入> \
  --visualization-mode <自动判定|不出图|需要图表> \
  --report-format "<Markdown|HTML|Markdown + HTML>" \
  --business-context "<business-context>" \
  --analysis-sheets <sheet-1> <sheet-2>
```

只有 `analysis_gate.status == "confirmed"` 且 `analysis_goal_gate.status == "confirmed"` 才能进入分析。

## Analysis Stage

仅在 `Analysis Only`、已通过两个确认点的 `End-to-End`，或分析阶段恢复/回退时执行。

### Phase 1: Intake

直接分析已有文件时，一次性确认：

- 数据文件路径与分析 Tab
- 分析目标
- 决策对象 / 报告使用者
- 业务背景
- 重点关注指标或异常
- 输出深度、图表模式和报告格式

信息不足时先补齐目标和业务背景，不直接计算。目标确认后初始化：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/session_store.py init \
  --session-dir .analysis-session \
  --dataset <dataset-path> \
  --goal "<confirmed-goal>" \
  --goal-confirmed \
  --decision-object "<decision-object>" \
  --focus "<focus>" \
  --output-depth <简要|标准|深入> \
  --visualization-mode <自动判定|不出图|需要图表> \
  --report-format <Markdown|HTML|Markdown + HTML> \
  --business-context "<business-context>" \
  --analysis-sheets <sheet-1> <sheet-2> \
  --audience "<audience>"
```

从清洗阶段进入时，读取 [references/cleaning-handoff-schema.md](references/cleaning-handoff-schema.md) 并验证：

- 清洗、清洗结果确认、分析目标确认均已完成。
- `cleaned_file_path` 存在且不等于任一源文件。
- 分析范围严格使用 `analysis_goal_gate.analysis_sheets`。
- 清洗 run、规则、warning 和追溯字段写入分析 run 前提。
- 追溯字段默认不作为业务指标或分析维度。

### Phase 2: Dataset Profiling

对每个已确认的分析 Tab 运行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/profile_dataset.py <dataset-path> \
  --sheet <sheet-name> \
  --output .analysis-session/profile.json
```

让用户确认每行含义、粒度、时间范围、关键字段和口径歧义。这一步不输出最终结论。详细规则读取 [references/interaction-protocol.md](references/interaction-protocol.md)。

### Phase 3: Anomaly Gate

业务正常时间范围未确认时必须先询问，不得直接把数据最小/最大日期视为正常范围。

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/detect_anomalies.py <dataset-path> \
  --sheet <sheet-name> \
  --profile .analysis-session/profile.json \
  --expected-start <YYYY-MM-DD-if-confirmed> \
  --expected-end <YYYY-MM-DD-if-confirmed> \
  --output .analysis-session/anomaly-scan.json

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/session_store.py merge-anomalies \
  --session-dir .analysis-session \
  --input .analysis-session/anomaly-scan.json
```

按 [templates/anomaly-review-template.md](templates/anomaly-review-template.md) 逐项展示 `blocking` 和 `warning`，要求用户确认处理、忽略、提供规则或补充数据。异常分类读取 [references/anomaly-taxonomy.md](references/anomaly-taxonomy.md)。

### Phase 4: Chart Decision

异常决策完成后读取 [references/chart-decision-rules.md](references/chart-decision-rules.md) 并运行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/decide_charts.py \
  --profile .analysis-session/profile.json \
  --anomalies .analysis-session/anomalies.json \
  --goal "<confirmed-goal>" \
  --focus "<confirmed-focus>" \
  --output-depth <简要|标准|深入> \
  --visualization-mode <自动判定|不出图|需要图表> \
  --sheet "<sheet-name>" \
  --output .analysis-session/chart-decision.json
```

图表写入 `.analysis-session/charts/`。数量上限为简要 2 张、标准 5 张、深入 10 张，允许 0 张；每张图必须解释业务含义。

### Phase 5: Formal Analysis

异常闸门通过后读取 [references/original-sop.md](references/original-sop.md)，再启动分析 run：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/session_store.py start-run \
  --session-dir .analysis-session
```

输出必须说明推断字段、已忽略异常、用户自定义规则，以及适用时的清洗 run、规则、输出文件、分析 Tab 和追溯字段。

### Phase 6: Reconciliation

用户质疑结果时先识别责任阶段：

- 表头、数据范围、字段标准化、合并或排除行：回退清洗检查点 `B/C/D`。
- 字段业务含义、指标口径、异常处理或结论：回退分析检查点 `B/C/D`。

使用对应 store 的 `invalidate`，重跑受影响阶段。清洗重跑后，必须用 `session_store.py invalidate` 将旧分析 run 标为 `superseded`，并基于新 `handoff.json` 启动分析。

分析重跑后生成差异摘要：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/summarize_run_diff.py \
  --session-dir .analysis-session \
  --format markdown
```

检查点与失效规则读取 [references/cleaning-session-schema.md](references/cleaning-session-schema.md) 和 [references/session-schema.md](references/session-schema.md)。

### Phase 7: Finalize

只有用户接受当前分析 run 后才生成最终报告。使用 [templates/final-report-template.md](templates/final-report-template.md)，并附带：

- 关键假设、已忽略异常、置信度和待补充数据
- 图表判定结果、实际图表和未出图原因
- 原始文件、清洗后文件、清洗 run、分析 run、清洗规则和 warning

先写入 `.analysis-session/final-report.md`，再导出：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/export_report.py \
  .analysis-session/final-report.md \
  --output-dir .analysis-session/exports \
  --basename business-analysis-report \
  --format "<Markdown|HTML|Markdown + HTML>" \
  --title "<report-title>"
```

最终回复列出所有导出文件的绝对路径。

## Resource Map

- 清洗流程：[references/cleaning-workflow.md](references/cleaning-workflow.md)
- 清洗会话：[references/cleaning-session-schema.md](references/cleaning-session-schema.md)
- 阶段交接：[references/cleaning-handoff-schema.md](references/cleaning-handoff-schema.md)
- 分析交互协议：[references/interaction-protocol.md](references/interaction-protocol.md)
- 分析会话：[references/session-schema.md](references/session-schema.md)
- 异常分类：[references/anomaly-taxonomy.md](references/anomaly-taxonomy.md)
- 图表规则：[references/chart-decision-rules.md](references/chart-decision-rules.md)
- 原分析 SOP：[references/original-sop.md](references/original-sop.md)
