# 会话文件结构

## 1. 目录结构

```text
.data-session/goals/<goal-id>/analysis-session/
├── session.json
├── anomalies.json
├── chart-decision.json
├── charts/
├── final-report.md
├── exports/
└── runs/
    ├── run-001.json
    └── run-002.json
```

## 2. session.json

```json
{
  "session_id": "session_20260524_001",
  "dataset_path": "sales.xlsx",
  "dataset_fingerprint": "sha256:...",
  "current_phase": "Phase 3: Anomaly Gate",
  "analysis_goal": "定位收入下滑原因",
  "analysis_goal_status": "confirmed",
  "decision_object": "差旅管理负责人",
  "focus": "费用结构、异常人员、跨期记录",
  "output_depth": "标准",
  "visualization_mode": "自动判定",
  "report_format": "Markdown + HTML",
  "business_context": "月度差旅费用复盘",
  "analysis_sheets": ["预存机票", "预存会员酒店"],
  "audience": "管理层",
  "goal_id": "goal-20260607120000",
  "goal_contract_path": ".data-session/goals/<goal-id>/goal-contract.json",
  "goal_contract_fingerprint": "sha256:...",
  "active_run_id": "run-002",
  "active_checkpoint": "C",
  "open_anomaly_ids": ["anomaly_missing_revenue_001"],
  "resolved_decision_ids": ["decision_2026_05_24_001"],
  "decisions": [],
  "history": []
}
```

## 3. anomalies.json

```json
{
  "generated_at": "2026-05-24T10:00:00+08:00",
  "dataset_path": "sales.xlsx",
  "anomalies": []
}
```

## 4. run 文件

每个 `runs/run-XXX.json` 至少包含：

- `run_id`
- `created_at`
- `checkpoint_basis`
- `accepted_assumptions`
- `ignored_anomalies`
- `custom_rules`
- `chart_decision`
- `chart_files`
- `summary`
- `report_sections`
- `status`

`chart_decision.status` 只能为 `pending_confirmation` 或 `confirmed`。渲染和最终导出只接受 `confirmed`；`chart_files` 保存成功 PNG 的绝对路径，`chart_failures` 保存未生成项及原因。

## 5. 检查点

- `A`：分析目标与业务背景
- `B`：粒度 / 字段 / 指标口径
- `C`：异常处理决策
- `D`：当前 run 结论

## 6. 失效规则

- 改 `A` 或 `B`：`C/D` 失效
- 改 `C`：`D` 失效
- 改 `D`：不允许直接改文案，必须回到 `B` 或 `C`

## 7. session_store.py 约定

- `init`：创建目录、初始化 `session.json` 和 `anomalies.json`
- 从清洗流程进入时，`init` 必须携带 `--goal-confirmed` 以及已确认的目标相关字段；否则不得进入画像。
- 新流程还必须携带 `--goal-contract`，且分析目标必须与契约一致。
- `dataset_path` 必须是当前目标的独立定向清洗文件，不得使用原始文件。
- `merge-anomalies`：合并扫描结果，更新 `open_anomaly_ids`
- `decide`：写入 decision record，更新异常状态
- `start-run`：创建新 run ID
- `save-run`：保存当前 run 结果
- `invalidate`：记录回退原因并将下游 run 标记为 `superseded`

图表候选由 `decide_charts.py` 生成并经用户确认，`render_charts.py --run-file` 将最终决定、成功文件和失败原因回写当前 run。

最终导出文件必须记录绝对路径，并写入 run 的 `report_files`。
