#!/usr/bin/env python3
"""Score chart candidates for an analysis report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEPTH_LIMITS = {"简要": 2, "标准": 5, "深入": 10}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="Dataset profile JSON")
    parser.add_argument("--anomalies", help="Resolved/current anomaly JSON")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--focus", default="")
    parser.add_argument("--output-depth", choices=DEPTH_LIMITS, default="标准")
    parser.add_argument(
        "--visualization-mode",
        choices=["自动判定", "不出图", "需要图表"],
        default="自动判定",
    )
    parser.add_argument("--sheet", default="未指定")
    parser.add_argument(
        "--selected-chart",
        action="append",
        default=[],
        help="Confirmed chart candidate ID; repeat for multiple charts",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Mark the decision as user-confirmed; no selected IDs means no charts",
    )
    parser.add_argument("--output", help="Write chart decision JSON")
    return parser.parse_args()


def read_json(path: str | None, default: Any) -> Any:
    if not path:
        return default
    return json.loads(Path(path).read_text(encoding="utf-8"))


def goal_hits(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def unresolved_fields(anomalies: dict[str, Any]) -> set[str]:
    fields = set()
    for anomaly in anomalies.get("anomalies", []):
        if anomaly.get("status") not in {"open", None}:
            continue
        field = anomaly.get("details", {}).get("field_name")
        if field:
            fields.add(field)
    return fields


def score_candidate(
    *,
    direct: bool,
    reveals_pattern: bool,
    hard_in_text: bool,
    supports_action: bool,
    readable: bool,
    duplicate: bool,
    quality_risk: bool,
    decorative: bool,
) -> tuple[int, list[dict[str, Any]]]:
    components = [
        ("直接回答核心分析问题", 3 if direct else 0),
        ("揭示趋势、结构、对比、分布或关系", 2 if reveals_pattern else 0),
        ("仅用文字不容易看清", 2 if hard_in_text else 0),
        ("直接支撑行动建议", 2 if supports_action else 0),
        ("数据量和类别数量适合阅读", 1 if readable else 0),
        ("与已有图表重复", -2 if duplicate else 0),
        ("数据质量或口径尚未确认", -3 if quality_risk else 0),
        ("只能起装饰作用", -3 if decorative else 0),
    ]
    return sum(value for _, value in components), [
        {"reason": reason, "score": value} for reason, value in components if value
    ]


def make_candidate(
    *,
    candidate_id: str,
    title: str,
    chart_type: str,
    question: str,
    fields: list[str],
    direct: bool,
    supports_action: bool,
    readable: bool,
    quality_risk: bool,
    duplicate: bool = False,
    decorative: bool = False,
) -> dict[str, Any]:
    score, scoring = score_candidate(
        direct=direct,
        reveals_pattern=True,
        hard_in_text=True,
        supports_action=supports_action,
        readable=readable,
        duplicate=duplicate,
        quality_risk=quality_risk,
        decorative=decorative,
    )
    decision = "必须出图" if score >= 6 else "可选" if score >= 3 else "不出图"
    return {
        "id": candidate_id,
        "title": title,
        "chart_type": chart_type,
        "question": question,
        "fields": fields,
        "score": score,
        "decision": decision,
        "scoring": scoring,
    }


def build_candidates(
    profile: dict[str, Any],
    anomalies: dict[str, Any],
    goal: str,
    focus: str,
    sheet_name: str,
) -> list[dict[str, Any]]:
    time_fields = profile.get("candidate_time_fields", [])
    metric_fields = profile.get("candidate_metric_fields", [])
    dimension_fields = profile.get("candidate_dimension_fields", [])
    row_count = profile.get("row_count", 0)
    risky_fields = unresolved_fields(anomalies)
    intent = f"{goal} {focus}"
    candidates = []

    if time_fields and metric_fields:
        fields = [time_fields[0], metric_fields[0]]
        candidates.append(
            make_candidate(
                candidate_id="trend",
                title=f"Tab「{sheet_name}」{metric_fields[0]}时间趋势",
                chart_type="折线图",
                question=f"{metric_fields[0]}如何随{time_fields[0]}变化？",
                fields=fields,
                direct=goal_hits(intent, ("趋势", "变化", "增长", "下降", "波动", "时间", "月度", "按月", "按周", "按日")),
                supports_action=True,
                readable=row_count >= 4,
                quality_risk=any(field in risky_fields for field in fields),
            )
        )

    if dimension_fields and metric_fields:
        fields = [dimension_fields[0], metric_fields[0]]
        candidates.append(
            make_candidate(
                candidate_id="comparison",
                title=f"Tab「{sheet_name}」按{dimension_fields[0]}对比{metric_fields[0]}",
                chart_type="排序柱状图",
                question=f"不同{dimension_fields[0]}之间的{metric_fields[0]}差异有多大？",
                fields=fields,
                direct=goal_hits(intent, ("对比", "差异", "排名", "最高", "最低", "部门", "人员", "区域", "供应商")),
                supports_action=True,
                readable=row_count >= 2,
                quality_risk=any(field in risky_fields for field in fields),
            )
        )
        candidates.append(
            make_candidate(
                candidate_id="composition",
                title=f"Tab「{sheet_name}」{metric_fields[0]}结构构成",
                chart_type="堆叠柱状图",
                question=f"{metric_fields[0]}由哪些{dimension_fields[0]}构成？",
                fields=([time_fields[0]] if time_fields else []) + fields,
                direct=goal_hits(intent, ("结构", "构成", "占比", "贡献", "集中")),
                supports_action=True,
                readable=row_count >= 2,
                quality_risk=any(field in risky_fields for field in fields),
            )
        )
        candidates.append(
            make_candidate(
                candidate_id="pareto",
                title=f"Tab「{sheet_name}」{metric_fields[0]}Top贡献",
                chart_type="帕累托图",
                question=f"Top {dimension_fields[0]}贡献了多少{metric_fields[0]}？",
                fields=fields,
                direct=goal_hits(intent, ("top", "排名", "集中", "贡献", "重点", "异常")),
                supports_action=True,
                readable=row_count >= 5,
                quality_risk=any(field in risky_fields for field in fields),
                duplicate=True,
            )
        )

    if metric_fields:
        field = metric_fields[0]
        has_outliers = any(
            anomaly.get("category") == "outlier"
            and anomaly.get("details", {}).get("field_name") == field
            for anomaly in anomalies.get("anomalies", [])
        )
        candidates.append(
            make_candidate(
                candidate_id="distribution",
                title=f"Tab「{sheet_name}」{field}分布与极端值",
                chart_type="箱线图",
                question=f"{field}的正常分布和极端值在哪里？",
                fields=[field],
                direct=has_outliers or goal_hits(intent, ("异常", "极端", "分布", "风险")),
                supports_action=has_outliers,
                readable=row_count >= 8,
                quality_risk=field in risky_fields and not has_outliers,
            )
        )

    if len(metric_fields) >= 2:
        fields = metric_fields[:2]
        candidates.append(
            make_candidate(
                candidate_id="relationship",
                title=f"Tab「{sheet_name}」{fields[0]}与{fields[1]}关系",
                chart_type="散点图",
                question=f"{fields[0]}与{fields[1]}是否存在关系？",
                fields=fields,
                direct=goal_hits(intent, ("关系", "相关", "驱动", "影响", "归因")),
                supports_action=goal_hits(intent, ("归因", "驱动", "影响")),
                readable=row_count >= 8,
                quality_risk=any(field in risky_fields for field in fields),
            )
        )
    return candidates


def select_candidates(candidates: list[dict[str, Any]], mode: str, depth: str) -> list[dict[str, Any]]:
    if mode == "不出图":
        return []
    threshold = 3 if mode == "需要图表" else 6
    eligible = [candidate for candidate in candidates if candidate["score"] >= threshold]
    eligible.sort(key=lambda item: (-item["score"], item["id"]))
    if mode == "需要图表" and not eligible and candidates:
        eligible = [max(candidates, key=lambda item: item["score"])]
    return eligible[: DEPTH_LIMITS[depth]]


def main() -> None:
    args = parse_args()
    profile = read_json(args.profile, {})
    anomalies = read_json(args.anomalies, {"anomalies": []})
    candidates = build_candidates(profile, anomalies, args.goal, args.focus, args.sheet)
    recommended = select_candidates(candidates, args.visualization_mode, args.output_depth)
    candidate_map = {candidate["id"]: candidate for candidate in candidates}
    unknown_ids = [candidate_id for candidate_id in args.selected_chart if candidate_id not in candidate_map]
    if unknown_ids:
        raise SystemExit(f"Unknown chart candidate IDs: {', '.join(unknown_ids)}")
    if args.confirm and args.visualization_mode == "不出图" and args.selected_chart:
        raise SystemExit("Visualization mode is 不出图; confirmed selection must be empty")
    if args.confirm and len(set(args.selected_chart)) > DEPTH_LIMITS[args.output_depth]:
        raise SystemExit(f"Confirmed selection exceeds the {args.output_depth} chart limit")
    selected = (
        [candidate_map[candidate_id] for candidate_id in dict.fromkeys(args.selected_chart)]
        if args.confirm
        else recommended
    )
    status = "confirmed" if args.confirm or args.visualization_mode == "不出图" else "pending_confirmation"
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "sheet": args.sheet,
        "visualization_mode": args.visualization_mode,
        "output_depth": args.output_depth,
        "chart_limit": DEPTH_LIMITS[args.output_depth],
        "should_create_charts": bool(selected),
        "selected_chart_count": len(selected),
        "selected_charts": selected,
        "recommended_chart_ids": [candidate["id"] for candidate in recommended],
        "all_candidates": candidates,
        "decision_summary": (
            "用户已确认不出图。"
            if status == "confirmed" and not selected
            else f"用户已确认生成 {len(selected)} 张关键图表。"
            if args.confirm
            else "用户已选择不出图。"
            if args.visualization_mode == "不出图"
            else f"建议生成 {len(selected)} 张关键图表，等待用户确认。"
            if selected
            else "没有候选图表达到当前模式的出图标准，等待用户确认是否增选。"
        ),
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
