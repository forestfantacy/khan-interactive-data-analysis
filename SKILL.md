---
name: khan-interactive-data-analysis
description: 目标驱动的 Excel/CSV 复杂数据清洗与业务分析 Skill。先只读侦察多文件、多 Sheet、错位表头和字段差异，以目标首页展示数据能力和分类候选；支持通过多轮对话共创自定义目标。每个目标独立确认数据范围、生成定向清洗文件并分析，可随时返回首页、恢复或继续其他目标。
---

# 目标驱动的数据清洗与分析

固定流程：

`目标首页 → 选择候选或共创目标 → 目标契约 → 字段映射 → 质量确认 → 独立定向清洗文件 → 分析 → 返回首页`

## Core Rules

1. 目标首页是流程起点和固定返回点；没有已确认目标，不执行正式清洗或分析。
2. 用户可从任意阶段返回首页；当前目标保留并标记为 `paused`。
3. 每个目标使用独立目录、契约、定向文件、清洗 run 和分析 run，不覆盖其他目标。
4. 原始文件只读；分析只能读取当前目标的定向清洗文件。
5. 用户不需要先整理文件、Sheet、表头或列；Skill 负责侦察、匹配和提出建议。
6. 字段不一致本身不阻断；只有目标必需字段无法映射时才阻断。
7. 数据问题按其对目标结论的影响处理；任何质量问题未确认时不得正式清洗。
8. 用户输入自定义目标时必须先进入多轮共创，不得直接写成目标契约。
9. 所有用户问题遵循 [references/user-input-style.md](references/user-input-style.md)，并提供“返回目标首页”。

## Workspace

```text
.data-session/
├── session.json
├── discovery.json
├── capability-summary.json
├── goal-catalog.json
├── intent-sessions/
└── goals/
    └── <goal-id>/
        ├── goal-contract.json
        ├── field-mapping.json
        ├── quality-impact.json
        ├── cleaning-session/
        └── analysis-session/
```

根目录下的 `goal-contract.json`、`field-mapping.json` 和 `quality-impact.json` 只是活动目标的兼容镜像；规范数据位于 `goals/<goal-id>/`。

## Phase 1: Discovery And Goal Home

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/profile_dataset.py <file-or-files> \
  --all-sheets \
  --output .data-session/discovery.json

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py init \
  --session-dir .data-session \
  --discovery .data-session/discovery.json

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py show-home \
  --session-dir .data-session
```

首页按 [templates/goal-home-template.md](templates/goal-home-template.md) 展示：

- 文件、Sheet、行数、时间覆盖、指标、维度、标识字段和跨表能力。
- 可可靠分析、受限分析和暂不支持的范围。
- 根据实际数据动态生成的类别；每个类别展示 3 至 5 个候选。
- 每个候选的决策价值、支持结论、不能支持的结论、数据要求、缺口、置信度和清洗成本。
- 候选标题必须使用用户容易理解的业务问题表达；分析方法和原始字段名分别放入详情与数据依据，不用技术动作充当目标。
- 进行中、暂停、受阻和已完成目标。
- 自定义目标、恢复目标、刷新侦察等入口。

候选不足时允许补充 `limited` 或 `blocked` 目标，但必须明确限制。不得用仅标题不同的候选凑数量。

选择目录候选：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py select-goal \
  --session-dir .data-session \
  --candidate-id <candidate-id> \
  --goal-id <goal-id>
```

## Phase 2: Custom Goal Co-creation

用户输入自由文本目标时读取 [templates/custom-goal-dialog-template.md](templates/custom-goal-dialog-template.md)。

创建意图会话：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py start-intent \
  --session-dir .data-session \
  --raw-input "<user-original-input>"
```

每轮：

1. 保留用户原话。
2. 结合数据能力更新已理解信息。
3. 只追问会改变分析方案的缺口，每轮最多 3 个问题。
4. 不询问能从文件或历史回答中推断的信息。
5. 允许用户纠正、跳过、直接生成候选或返回首页。

最低可执行条件：

- 核心问题明确。
- 关注对象、指标或问题范围明确。
- 决策用途或期望输出明确。
- 当前数据至少支持一个可执行方向。

Agent 将本轮理解写入 `--known`：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py update-intent \
  --session-dir .data-session \
  --raw-input "<latest-user-message>" \
  --known '<json-object>' \
  --assumptions '<json-list>' \
  --data-matches '<json-list>' \
  --data-gaps '<json-list>'
```

达到最低条件后，先展示并确认意图总结：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py summarize-intent \
  --session-dir .data-session \
  --summary "<confirmed-intent-summary>" \
  --confirmed
```

再生成 3 至 5 个候选：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py generate-custom-candidates \
  --session-dir .data-session
```

自定义候选围绕同一核心意图，从现状趋势、结构贡献、异常风险、驱动归因、行动监控等角度区分。用户可选择、要求重生成、继续完善，或组合两个候选：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py combine-custom-candidates \
  --session-dir .data-session \
  --candidate-id <candidate-1> <candidate-2>

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py create-custom-goal \
  --session-dir .data-session \
  --intent-id <intent-id> \
  --candidate-id <candidate-id> \
  --goal-id <goal-id>
```

## Phase 3: Goal Contract, Mapping And Quality

活动目标目录记为：

```text
GOAL_DIR=.data-session/goals/<goal-id>
```

目标契约必须包含目标问题、决策对象、文件和 Sheet 范围、必需字段、辅助字段、关联键、时间字段、假设和数据缺口。

确认字段映射：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py confirm-mapping \
  --session-dir .data-session \
  --mappings '<json-list-or-file>'
```

字段映射格式和旧格式兼容规则读取 [references/field-mapping-schema.md](references/field-mapping-schema.md)。来源文件或 Sheet 无法唯一推断时必须停止，不得生成来源为空的审计记录。

针对目标范围检测异常：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/detect_anomalies.py <dataset> \
  --sheet <sheet> \
  --profile <profile.json> \
  --goal-contract "$GOAL_DIR/goal-contract.json" \
  --field-mapping "$GOAL_DIR/field-mapping.json" \
  --output <quality-scan.json>

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py save-quality \
  --session-dir .data-session \
  --input <quality-scan.json>
```

影响级别：

- `blocking`：必须修复、补数据或调整目标。
- `material`：可能改变趋势、排名或归因，逐项确认。
- `limited`：局部影响，分组确认。
- `irrelevant`：汇总后批量确认忽略。

## Phase 4: Targeted Cleaning

清洗会话位于 `$GOAL_DIR/cleaning-session/`。读取 [references/cleaning-workflow.md](references/cleaning-workflow.md)，完成 dry-run 和确认后执行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py set-goal-status \
  --session-dir .data-session --status cleaning

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/clean_tabular_data.py <raw-files> \
  --output <targeted-output.xlsx> \
  --target-sheet 目标数据 \
  --goal-contract "$GOAL_DIR/goal-contract.json" \
  --field-mapping "$GOAL_DIR/field-mapping.json" \
  --quality-impact "$GOAL_DIR/quality-impact.json" \
  --rules "$GOAL_DIR/cleaning-session/rules.json" \
  --run-output "$GOAL_DIR/cleaning-session/run-summary.json" \
  --handoff-output "$GOAL_DIR/cleaning-session/handoff.json" \
  --cleaning-run-id <run-id> \
  --execute
```

每个目标生成独立文件，包含目标数据、`数据说明` 和 `清洗审计`。文件生成后必须停止并等待确认。

## Phase 5: Analysis And Completion

分析会话位于 `$GOAL_DIR/analysis-session/`：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py set-goal-status \
  --session-dir .data-session --status analyzing

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/session_store.py init \
  --session-dir "$GOAL_DIR/analysis-session" \
  --dataset <targeted-cleaning-file.xlsx> \
  --goal "<confirmed-goal>" \
  --goal-confirmed \
  --goal-contract "$GOAL_DIR/goal-contract.json" \
  --analysis-sheets <target-sheets>
```

分析严格围绕目标契约；不能支持的问题必须明确标为“当前无法回答”。

完成核心分析计算后、生成最终报告前，必须先生成图表候选：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/profile_dataset.py \
  <targeted-cleaning-file.xlsx> \
  --sheet <target-sheet> \
  --output "$GOAL_DIR/analysis-session/profile.json"

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/decide_charts.py \
  --profile "$GOAL_DIR/analysis-session/profile.json" \
  --anomalies "$GOAL_DIR/analysis-session/anomalies.json" \
  --goal "<confirmed-goal>" \
  --focus "<analysis-focus>" \
  --output-depth <简要|标准|深入> \
  --visualization-mode <自动判定|不出图|需要图表> \
  --sheet <target-sheet> \
  --output "$GOAL_DIR/analysis-session/chart-decision.json"
```

除 `不出图` 模式外，必须展示图表确认面板后暂停，不能直接渲染或完成目标。面板按推荐项预选，并列出：

- 图名、类型、回答的问题、使用字段和评分。
- 推荐项及数量上限。
- 确认推荐项、增删候选、全部不出图、返回目标首页。

用户确认后，使用最终选择重新写入已确认的决定；不传 `--selected-chart` 表示确认全部不出图：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/decide_charts.py \
  --profile "$GOAL_DIR/analysis-session/profile.json" \
  --anomalies "$GOAL_DIR/analysis-session/anomalies.json" \
  --goal "<confirmed-goal>" \
  --focus "<analysis-focus>" \
  --output-depth <简要|标准|深入> \
  --visualization-mode <自动判定|不出图|需要图表> \
  --sheet <target-sheet> \
  --confirm \
  --selected-chart <candidate-id> \
  --output "$GOAL_DIR/analysis-session/chart-decision.json"
```

开始分析 run 后渲染已确认图表：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/session_store.py start-run \
  --session-dir "$GOAL_DIR/analysis-session" \
  --checkpoint D

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/render_charts.py \
  --dataset <targeted-cleaning-file.xlsx> \
  --decision "$GOAL_DIR/analysis-session/chart-decision.json" \
  --output-dir "$GOAL_DIR/analysis-session/charts" \
  --run-file "$GOAL_DIR/analysis-session/runs/<run-id>.json"
```

将每张成功图表嵌入对应的分析章节，并在“图表判定”和附件中记录绝对路径。单张失败不阻断其他图表或分析结论，但报告必须披露失败项和原因。未生成 `status: confirmed` 的 `chart-decision.json` 时不得导出最终报告或完成目标。

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/export_report.py \
  "$GOAL_DIR/analysis-session/final-report.md" \
  --output-dir "$GOAL_DIR/analysis-session/exports" \
  --format <Markdown|HTML|Markdown + HTML> \
  --chart-decision "$GOAL_DIR/analysis-session/chart-decision.json"
```

目标完成后保存摘要和产物，并自动返回首页：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py complete-goal \
  --session-dir .data-session \
  --summary "<conclusion-summary>" \
  --targeted-files '<json-list>' \
  --report-files '<json-list>'
```

首页保留已完成目标，支持查看、恢复重跑或派生新目标。

## Navigation

任意阶段返回首页：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py return-home \
  --session-dir .data-session \
  --reason "<reason>"
```

恢复目标：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py resume-goal \
  --session-dir .data-session \
  --goal-id <goal-id>
```

基于已有目标派生：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/data_session_store.py derive-goal \
  --session-dir .data-session \
  --parent-goal-id <goal-id>
```

目标、范围、映射或质量决定变化时，按上游到下游顺序使旧产物失效，不得直接改报告文案。
