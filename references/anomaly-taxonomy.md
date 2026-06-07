# 目标相关的数据质量影响分类

异常严重性由“是否影响当前目标”决定，而不是只看数据本身是否异常。

## Impact Levels

- `blocking`：目标无法可靠回答，必须修复、补数据或修改目标。
- `material`：可能改变趋势、排名、金额或归因方向，必须逐项确认。
- `limited`：影响局部精度或分析深度，可以分组确认。
- `irrelevant`：位于目标契约之外，不影响本轮结论，汇总后批量确认忽略。

## Classification

| 问题 | 必需字段 / 关联键 / 时间字段 | 辅助字段 | 契约外字段 |
| --- | --- | --- | --- |
| 高缺失或类型混杂 | `blocking` | `limited` | `irrelevant` |
| 极端值或可疑 0 | `material` | `limited` | `irrelevant` |
| 时间范围或时间缺口 | `blocking` / `material` | `limited` | `irrelevant` |
| 重复记录 | 通常 `material` | 通常 `limited` | 视目标范围判断 |
| 指标口径、单位或粒度不清 | `blocking` | `limited` | `irrelevant` |
| 小样本 | `material` / `limited` | `limited` | `irrelevant` |

## Required Fields

每个异常必须记录：

- 受影响的目标问题和字段
- `impact_level`
- 对结论的具体影响
- 推荐处置
- 忽略后的结论置信度
- 用户决定及理由

任何异常仍为 `open` 时，不得生成定向清洗文件。用户选择忽略后，相关结论必须披露风险并降低置信度。
