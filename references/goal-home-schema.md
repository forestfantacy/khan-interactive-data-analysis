# Goal Home And Multi-goal Workspace

`.data-session/session.json` 管理一个数据工作区中的多个目标。

```json
{
  "schema_version": "2.0",
  "discovery_id": "...",
  "home_status": "ready",
  "active_goal_id": null,
  "active_intent_id": null,
  "goal_order": ["goal-001"],
  "goals": {
    "goal-001": {
      "title": "定位收入下降原因",
      "status": "completed",
      "source": "custom_intent",
      "summary": "...",
      "targeted_files": [],
      "report_files": []
    }
  }
}
```

目标状态：

- `selected`
- `preparing`
- `cleaning`
- `analyzing`
- `completed`
- `paused`
- `blocked`
- `superseded`

规范目标产物位于 `.data-session/goals/<goal-id>/`。根目录契约文件仅用于兼容旧命令。
