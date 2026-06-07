# Cleaning to Analysis Handoff

清洗阶段执行成功后生成 `.cleaning-session/handoff.json`，作为统一 skill 进入分析阶段的唯一标准交接入口。

```json
{
  "schema_version": "1.1",
  "generated_at": "2026-06-06T09:00:00+08:00",
  "cleaning_status": "completed",
  "analysis_gate": {
    "status": "awaiting_user_confirmation",
    "confirmed_at": null
  },
  "analysis_goal_gate": {
    "status": "awaiting_confirmation",
    "confirmed_at": null,
    "goal": null,
    "decision_object": null,
    "focus": null,
    "output_depth": null,
    "visualization_mode": "自动判定",
    "report_format": "Markdown + HTML",
    "business_context": null,
    "analysis_sheets": []
  },
  "cleaned_file_path": "/data/携程3月_清洗后.xlsx",
  "sheet_name": "原始数据_清洗后",
  "cleaning_run_id": "run-001",
  "rules": {
    "status": "saved",
    "path": "/data/.cleaning-session/rules.json",
    "description": "本轮清洗实际采用的表头、数据范围和排除规则"
  },
  "rules_path": "/data/.cleaning-session/rules.json",
  "source_files": ["/data/携程3月.xlsx"],
  "lineage_columns": ["源文件名", "源工作表名", "源行号"],
  "output_sheets": [
    {
      "output_sheet": "预存会员酒店",
      "source_count": 3,
      "source_stats": [
        {
          "source_file": "/data/携程3月.xlsx",
          "source_sheet": "预存会员酒店",
          "actual_data_rows": 174
        }
      ],
      "total_data_rows": 521
    }
  ],
  "exclusion_audit": {
    "sheet_name": "清洗排除记录",
    "excluded_row_count": 3
  },
  "excluded_rows": [],
  "warnings": [],
  "profile_summary": {
    "source_count": 1,
    "output_row_count": 378,
    "items": []
  }
}
```

## 用户可见说明

不要把原始 JSON 字段直接展示给用户。交接报告使用以下业务语言：

- `cleaned_file_path`：清洗后的数据文件
- `sheet_name`：清洗结果所在工作表
- `profile_summary.output_row_count`：清洗后保留的数据行数
- `output_sheets`：每个输出 Tab 的各来源实际行数和合并总行数
- `rules.status == saved`：清洗规则已记录，可用于重跑和追溯
- `warnings`：清洗时需要用户知晓的事项；为空时显示“无”
- `exclusion_audit`：清洗工作簿中的排除审计 Tab 及最终排除行数
- `excluded_rows`：用户确认排除的来源行、类型、依据和原始内容
- `analysis_gate.status == awaiting_user_confirmation`：已完成清洗，正在等待用户确认是否继续分析
- `analysis_goal_gate.status == awaiting_confirmation`：清洗结果已确认，但分析目标尚未确认

不要显示：

- `rules_path: null`
- 空 JSON
- “rules.json 为空模板”

如果规则文件异常，应显示：

> 清洗规则记录不完整，暂时不能进入分析。请先重新保存本轮清洗规则。

## Contract

- `cleaning_status` 必须为 `completed`。
- 清洗执行完成后，`analysis_gate.status` 必须先是 `awaiting_user_confirmation`。
- 只有用户明确确认后，才通过 `cleaning_store.py confirm-handoff` 改为 `confirmed`。
- 清洗结果确认后，必须单独确认分析目标。
- 只有执行 `cleaning_store.py confirm-analysis-goal` 后，`analysis_goal_gate.status` 才能改为 `confirmed`。
- 分析阶段只接受清洗结果和分析目标均为 `confirmed` 的交接。
- `cleaned_file_path` 必须存在，且不得等于任一 `source_files`。
- `cleaned_file_path` 对用户展示时必须使用绝对路径。
- 单一输出 Tab 时使用 `sheet_name`；多 Tab 输出时使用 `output_sheets`，进入分析前由用户确认分析范围。
- `cleaning_run_id` 用于分析报告追溯；没有 run id 时不得伪造。
- `rules_path` 指向本轮确认后的规则快照。
- `warnings` 必须原样带入分析前提，不得静默丢弃。
- `lineage_columns` 只用于追溯，不应默认作为业务维度或指标。
- `analysis_goal_gate.analysis_sheets` 是用户确认的分析范围。
- `analysis_goal_gate.visualization_mode` 是用户确认的图表模式，默认 `自动判定`。
- `analysis_goal_gate.report_format` 是报告导出格式，支持 `Markdown`、`HTML`、`Markdown + HTML`。
