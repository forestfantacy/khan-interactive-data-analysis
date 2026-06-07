# Goal-data contract

`.data-session/goals/<goal-id>/goal-contract.json` 是单个目标的清洗和分析共同前提。`.data-session/goal-contract.json` 仅是活动目标的兼容镜像。

```json
{
  "schema_version": "1.0",
  "goal_id": "goal-20260607120000",
  "goal": "定位收入下降的主要来源",
  "goal_type": "business_analysis",
  "decision_object": "经营负责人",
  "questions": ["哪些时间和客户导致收入下降"],
  "required_data": {
    "scope": [{"file": "/data/sales.xlsx", "sheet": "订单"}],
    "required_fields": ["收入"],
    "supporting_fields": ["客户", "区域"],
    "join_keys": ["订单号"],
    "time_fields": ["订单日期"],
    "metric_definitions": []
  },
  "excluded_scope": [],
  "assumptions": [],
  "status": "confirmed",
  "contract_fingerprint": "sha256:..."
}
```

## Contract

- `goal_id` 唯一标识一个目标。
- `contract_fingerprint` 绑定目标、范围和字段定义。
- `scope` 只允许使用已确认的文件和 Sheet。
- `required_fields` 无法映射时阻断。
- `supporting_fields` 缺失时降低分析深度，不必阻断。
- `join_keys` 和 `time_fields` 按必需字段处理。
- 目标、范围或字段定义变化时必须生成新指纹并使下游结果失效。
