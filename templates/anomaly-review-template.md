# 异常确认卡片

```markdown
## 异常确认：{anomaly_title}

**异常 ID：** `{anomaly_id}`
**类别：** `{category}`
**严重级别：** `{severity}`
**对目标影响：** `{impact_level}`
**位置：** Tab「{sheet_name}」/ 字段「{field_name}」

**证据：**
{evidence}

**正常参考：**
{normal_reference}

**异常程度：**
{anomaly_degree}

**异常样例：**
{examples}

**对后续分析的影响：**
{impact}

**可能受影响的目标问题：**
{affected_goal_questions}

**忽略后的结论置信度：**
{confidence_after_ignoring}

**默认建议：**
{recommended_action}

---

### 需要你确认

> **问题：** 该异常应如何处理？

**可选操作**

- `1｜按建议处理（推荐）`：采用上述默认建议并记录处理决策。
- `2｜忽略并继续`：保留原数据，后续结论降低置信度并披露风险。
- `3｜指定处理规则`：由你提供更具体的保留、排除、替换或分组规则。
- `4｜暂停分析`：补充数据或背景后再继续。
- `5｜返回目标首页`：保留当前目标和已记录决定，稍后继续。

**请回复：** `1`、`2`、`3`、`4` 或 `5`
```

展示约束：

- 不直接向用户展示 `scope`、`rules_path` 等机器字段。
- 极端值必须展示正常范围、异常数量 / 占比、异常值范围和偏离程度。
- 时间异常必须明确标记为“正常范围之前”“正常范围之后”或“正常范围内部缺口”。
- `irrelevant` 异常按文件、Sheet 或字段组汇总确认，不逐项打断。
- 不存在的内容显示“无”，不要显示 `null`、空对象或空模板。
- 所有要求用户输入的内容必须遵循 [../references/user-input-style.md](../references/user-input-style.md)。
