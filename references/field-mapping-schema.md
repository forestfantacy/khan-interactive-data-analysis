# Field Mapping Schema

字段映射规范格式：

```json
{
  "schema_version": "2.0",
  "status": "confirmed",
  "contract_fingerprint": "sha256:...",
  "mappings": [
    {
      "source_file": "/data/travel.xlsx",
      "source_sheet": "火车票",
      "source_header_row": 3,
      "source_field": "乘车人",
      "target_field": "出行人",
      "target_sheet": "目标数据"
    }
  ]
}
```

## Compatibility

读取旧映射时支持：

- `sheet` → `source_sheet`
- `goal_field` → `target_field`
- `output_sheet` → `target_sheet`

缺少 `source_file` 和 `source_header_row` 时，清洗画像根据来源 Sheet 和字段补齐。若匹配到多个来源文件或无法匹配，必须阻断执行。

handoff 中：

- `field_mapping` 保存规范化映射。
- `original_field_mapping` 保存用户确认时的原始映射。

字段映射属于列级操作，`清洗审计` 的“来源表头行”记录字段所在表头行，“源数据行号”显示“不适用”。
