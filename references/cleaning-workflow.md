# 交互式数据清洗标准化流程

## 1. 目标

将 Excel/CSV/多 sheet/多文件原始导出数据清洗为结构稳定的新文件。默认只读原文件，输出新文件，不覆盖或修改原始文件。

## 2. 检查点

- `A`：清洗目标与输出方式
- `B`：文件结构识别
- `C`：表头 / 数据区规则确认
- `D`：异常处理决策
- `E`：清洗执行结果

失效规则：

- 改 `A`：`B/C/D/E` 失效
- 改 `B`：`C/D/E` 失效
- 改 `C`：`D/E` 失效
- 改 `D`：`E` 失效
- 改 `E`：不得手改输出结果，必须回到 `C` 或 `D` 重跑

## 3. 标准阶段

### Phase A: Intake

确认：

- 输入文件路径，可为单文件或多文件
- 文件类型：Excel / CSV
- 清洗目标：提取明细、合并多月、多 sheet 归一等
- 输出路径与目标 tab 名，默认 `原始数据_清洗后`
- 是否增加追溯字段：源文件名、源工作表名、源行号

### Phase B: Structure Profiling

先 dry-run：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/clean_tabular_data.py <input.xlsx> \
  --profile-output .cleaning-session/profile.json \
  --rules-output .cleaning-session/rules.json \
  --run-output .cleaning-session/dry-run.json
```

识别内容：

- 说明区
- 字段表头行
- 双语 / 系统字段表头行
- 数据起止行
- 合计 / 备注 / 说明 / 签字等排除候选行
- 每条候选的来源行、命中内容、判定依据、建议动作和候选 ID
- 置信度与证据
- 按 Tab 名分组的跨文件表头一致性
- 每个来源文件 / Tab 的实际数据行数
- 同名 Tab 合并后的预计总行数

### Phase C: Rule Confirmation

把识别结果交给用户确认。不要固定行号；必须说明识别依据。

重点确认：

- 使用哪一行作为最终字段名
- 双语表头是否跳过
- 数据区起止行是否合理
- 每条排除候选是保留还是排除
- 是否增加追溯字段
- 同名 Tab 是否合并

同名 Tab 出现在不同文件时：

1. 只比较同名 Tab 的表头，不拿不同业务 Tab 互相比较。
2. 表头一致时，分别展示每个来源文件的实际数据行数和合并总行数。
3. 明确询问用户选择合并或分别保留。
4. 合并时输出一个原名 Tab，例如 `预存会员酒店`，不得生成带月份后缀的多个 Tab。
5. 表头不一致时列出具体列差异，不得直接合并。

### Phase D: Anomaly Gate

阻断型异常包括：

- 找不到稳定表头
- 多个候选表头置信度接近
- 数据区不连续且无法判断是否应保留
- 多文件合并时字段结构不一致
- 输出路径与输入路径相同
- 仍有 `pending` 的排除候选
- 已确认候选对应的源行内容发生变化

warning 包括：

- 少量空行
- 存在用户已确认排除的合计 / 备注 / 签字行
- 部分 sheet 没有数据区
- 字段名重复但已自动去重

### Phase E: Execute

用户确认规则后再执行：

接受全部建议：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py confirm-exclusions \
  --session-dir .cleaning-session \
  --accept-suggested
```

逐项确认时，通过候选 ID 使用 `--exclude <id...>` 和 `--keep <id...>`；未明确处理的候选保持 `pending`，不得执行。

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py start-run --session-dir .cleaning-session

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/clean_tabular_data.py <input.xlsx> \
  --output <input>_清洗后.xlsx \
  --target-sheet 原始数据_清洗后 \
  --rules .cleaning-session/rules.json \
  --profile-output .cleaning-session/profile.json \
  --run-output .cleaning-session/run-summary.json \
  --handoff-output .cleaning-session/handoff.json \
  --cleaning-run-id run-XXX \
  --merge-same-sheets \
  --execute

python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py save-run \
  --session-dir .cleaning-session \
  --input .cleaning-session/run-summary.json \
  --status accepted
```

用户选择分别保留时，将 `--merge-same-sheets` 改为 `--keep-separate-sheets`。

执行完成后必须停止，向用户报告：

- 清洗后文件的绝对路径
- 输出工作表列表
- 每个输出 Tab 的各来源实际数据行数
- 每个输出 Tab 的合并总行数
- 原文件未修改
- 规则已记录
- warning 摘要
- `清洗排除记录` Tab 名与最终排除行数
- 每条最终排除行的来源、类型和依据

只有用户下一条消息明确回复继续分析后，才执行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py confirm-handoff \
  --session-dir .cleaning-session
```

确认前 `analysis_gate.status` 为 `awaiting_user_confirmation`；确认后为 `confirmed`。

清洗结果确认后，必须继续停在 Intake，不得立即画像。使用独立确认面板展示并确认：

- 分析目标
- 决策对象 / 报告使用者
- 重点关注指标或异常
- 输出深度
- 图表模式：自动判定 / 不出图 / 需要图表
- 报告格式：Markdown / HTML / Markdown + HTML
- 业务背景
- 分析 Tab 范围

用户确认后执行：

```bash
python3 ~/.claude/skills/khan-interactive-data-analysis/scripts/cleaning_store.py confirm-analysis-goal \
  --session-dir .cleaning-session \
  --goal "<analysis-goal>" \
  --decision-object "<decision-object>" \
  --focus "<focus>" \
  --output-depth 标准 \
  --visualization-mode 自动判定 \
  --report-format "Markdown + HTML" \
  --business-context "<business-context>" \
  --analysis-sheets <sheet-1> <sheet-2>
```

只有 `analysis_goal_gate.status == confirmed` 后才能进入分析画像。

## 4. 与分析阶段的交接

清洗阶段输出给分析阶段：

- `.cleaning-session/handoff.json`

分析阶段在正式分析前必须引用这些前提，不得隐式修改清洗后数据。

交接字段定义见 [cleaning-handoff-schema.md](cleaning-handoff-schema.md)。
