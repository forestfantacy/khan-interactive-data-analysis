# 目标驱动的定向清洗流程

## Preconditions

执行清洗前必须存在：

- 已确认的 `.data-session/goals/<goal-id>/goal-contract.json`
- 已确认的 `.data-session/goals/<goal-id>/field-mapping.json`
- 已完成决策的 `.data-session/goals/<goal-id>/quality-impact.json`
- 已确认的表头、数据区、排除候选和合并方式

## Checkpoints

- `A`：目标契约
- `B`：来源范围与字段映射
- `C`：表头、数据区和排除候选
- `D`：目标相关质量处置
- `E`：独立定向清洗文件

上游检查点变化时，所有下游检查点失效。

## Dry-run

dry-run 必须展示：

- 当前 `goal_id`、目标和契约指纹
- 纳入与排除的文件、Sheet
- 每个标准字段对应的来源字段
- 缺失的必需字段和存在歧义的映射
- 表头、数据区、排除候选和预计行数
- `blocking`、`material`、`limited`、`irrelevant` 的质量问题摘要
- 独立输出文件绝对路径

字段结构不同但可映射到同一目标字段集合时允许合并。缺失必需字段时阻断；缺失辅助字段时保留为空并披露限制。

## Execute

正式执行必须使用已确认规则、目标契约、字段映射和质量影响文件。输出不得覆盖输入，且每个目标生成独立文件。

字段映射在执行前按 [field-mapping-schema.md](field-mapping-schema.md) 规范化。旧字段别名允许读取，但来源无法唯一确定时必须阻断。

定向文件至少包含：

- 一个或多个目标数据 Sheet
- `数据说明`
- `清洗审计`

`数据说明` 记录目标、字段范围、来源和适用限制；`清洗审计` 记录排除行、字段映射和质量处置。字段映射行必须包含来源文件、来源 Sheet、来源表头行、来源字段、目标字段和目标 Sheet。

## Result Gate

文件生成后必须停止并展示：

- 定向文件绝对路径
- `goal_id` 和目标
- 输出 Sheet、行数和字段
- 来源文件与 Sheet
- 排除、映射和质量处置摘要
- 原文件未修改

用户确认后才允许进入分析。分析只能读取该定向文件。
