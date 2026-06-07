# 清洗会话文件结构

## 1. 目录结构

```text
.data-session/goals/<goal-id>/cleaning-session/
├── session.json
├── profile.json
├── rules.json
├── dry-run.json
├── run-summary.json
└── runs/
    ├── run-001.json
    └── run-002.json
```

## 2. session.json

```json
{
  "session_id": "cleaning_session_20260606000100",
  "input_paths": ["raw.xlsx"],
  "input_fingerprints": {
    "raw.xlsx": "sha256:..."
  },
  "output_path": "raw_清洗后.xlsx",
  "target_sheet": "原始数据_清洗后",
  "cleaning_goal": "提取真实明细数据",
  "goal_id": "goal-20260607120000",
  "goal_contract_path": ".data-session/goals/<goal-id>/goal-contract.json",
  "goal_contract_fingerprint": "sha256:...",
  "current_phase": "Phase C: Rule Confirmation",
  "active_checkpoint": "C",
  "active_run_id": "run-001",
  "resolved_decision_ids": [],
  "decisions": [],
  "history": []
}
```

## 3. profile.json

由 `scripts/clean_tabular_data.py --profile-output` 生成，核心字段：

- `items[].source_file`
- `items[].source_sheet`
- `items[].header_row`
- `items[].header_rows`
- `items[].data_start_row`
- `items[].data_end_row`
- `items[].included_row_count`
- `items[].exclusion_candidates`
- `items[].exclusion_candidate_counts`
- `items[].skipped_rows`（仅包含用户确认排除的行）
- `items[].headers`
- `items[].confidence`
- `items[].evidence`

## 4. rules.json

记录可复用清洗规则：

- 表头识别方式
- 数据区起止规则
- 是否跳过双语 / 系统字段表头
- 排除候选的来源行、类型、命中内容、原始行内容和内容哈希
- 每条候选的用户决策：`pending` / `exclude` / `keep`
- 正式执行前不得存在 `pending`
- 输出文件与目标 tab
- 同名 Tab 的处理方式：等待确认 / 合并 / 分别保留
- 追溯字段
- 目标字段投影与标准字段名
- 定向文件路径

## 5. run 文件

每个 `runs/run-XXX.json` 至少包含：

- `run_id`
- `created_at`
- `checkpoint_basis`
- `rules_snapshot`
- `dry_run_summary`
- `output_path`
- `target_sheet`
- `status`

## 6. cleaning_store.py 命令

- `init`：初始化当前目标的 `cleaning-session`
- `save-profile`：保存结构画像
- `save-rules`：保存清洗规则
- `decide`：记录用户对规则或异常的决策
- `confirm-exclusions`：将用户对排除候选的确认写入 `rules.json`
- `start-run`：创建清洗 run
- `save-run`：保存 dry-run 或执行摘要
- `invalidate`：回退检查点，并将旧 run 标记为 `superseded`

新流程必须绑定已确认目标契约。旧会话缺少 `goal_id` 时可以读取，但继续执行前必须迁移到 `.data-session/goals/<goal-id>/`。
