#!/usr/bin/env python3
"""Detect common anomalies in CSV/XLSX datasets."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from profile_dataset import build_profile, load_rows, parse_date, parse_number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Path to a CSV or XLSX file")
    parser.add_argument("--sheet", help="Worksheet name for XLSX input")
    parser.add_argument("--profile", help="Existing profile JSON file")
    parser.add_argument("--goal-contract", help="Confirmed goal-data contract JSON")
    parser.add_argument("--field-mapping", help="Confirmed source-to-target field mapping JSON")
    parser.add_argument("--output", help="Write anomaly JSON to a file")
    parser.add_argument("--expected-start", help="Expected normal date range start, YYYY-MM-DD")
    parser.add_argument("--expected-end", help="Expected normal date range end, YYYY-MM-DD")
    return parser.parse_args()


def load_profile(path: Path | None, dataset_path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if path:
        return json.loads(path.read_text(encoding="utf-8"))
    return build_profile(dataset_path, rows)


def anomaly_id(category: str, name: str, index: int) -> str:
    normalized = name.lower().replace(" ", "_")
    return f"anomaly_{category}_{normalized}_{index:03d}"


def make_anomaly(
    *,
    anomaly_key: str,
    title: str,
    category: str,
    severity: str,
    scope: str,
    evidence: str,
    impact: str,
    recommended_action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": anomaly_key,
        "title": title,
        "category": category,
        "severity": severity,
        "scope": scope,
        "evidence": evidence,
        "impact": impact,
        "recommended_action": recommended_action,
        "status": "open",
    }
    if details:
        payload["details"] = details
    return payload


def field_label(sheet_name: str, field_name: str) -> str:
    return f"Tab「{sheet_name}」字段「{field_name}」"


def field_scope(sheet_name: str, field_name: str) -> str:
    return f"tab:{sheet_name}/field:{field_name}"


def format_number(value: float) -> str:
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def detect_missing(profile: dict[str, Any], sheet_name: str) -> list[dict[str, Any]]:
    anomalies = []
    index = 1
    for column in profile["columns"]:
        missing_rate = column["missing_rate"]
        if missing_rate < 0.1:
            continue
        severity = "blocking" if column["inferred_role"] == "metric" and missing_rate >= 0.2 else "warning"
        anomalies.append(
            make_anomaly(
                anomaly_key=anomaly_id("missing_value", column["name"], index),
                title=f"{field_label(sheet_name, column['name'])}存在缺失值",
                category="missing_value",
                severity=severity,
                scope=field_scope(sheet_name, column["name"]),
                evidence=f"{field_label(sheet_name, column['name'])}缺失率为 {missing_rate:.1%}。",
                impact="可能导致指标失真、样本偏差或分子分母不一致。",
                recommended_action="确认该字段是否允许缺失，并决定填补、剔除或保留缺失行。",
                details={"sheet_name": sheet_name, "field_name": column["name"], "missing_rate": missing_rate},
            )
        )
        index += 1
    return anomalies


def detect_duplicate_rows(rows: list[dict[str, Any]], sheet_name: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    canonical = [json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows]
    duplicate_count = len(canonical) - len(set(canonical))
    if duplicate_count == 0:
        return []
    rate = duplicate_count / len(rows)
    severity = "blocking" if rate >= 0.05 else "warning"
    return [
        make_anomaly(
            anomaly_key=anomaly_id("duplicate_row", "dataset", 1),
            title=f"Tab「{sheet_name}」存在重复记录",
            category="duplicate_row",
            severity=severity,
            scope=f"tab:{sheet_name}",
            evidence=f"Tab「{sheet_name}」检测到 {duplicate_count} 条重复记录，重复率为 {rate:.1%}。",
            impact="重复记录会直接放大规模、收入、成本等聚合指标。",
            recommended_action="确认重复是否真实存在；若非业务重复，先去重后再分析。",
            details={"sheet_name": sheet_name, "duplicate_count": duplicate_count, "duplicate_rate": rate},
        )
    ]


def detect_zero_and_mixed(profile: dict[str, Any], sheet_name: str) -> list[dict[str, Any]]:
    anomalies = []
    index = 1
    for column in profile["columns"]:
        numeric_summary = column.get("numeric_summary")
        if numeric_summary:
            zero_rate = numeric_summary["zero_rate"]
            if zero_rate >= 0.9:
                anomalies.append(
                    make_anomaly(
                        anomaly_key=anomaly_id("suspicious_zero", column["name"], index),
                        title=f"{field_label(sheet_name, column['name'])}的 0 值占比过高",
                        category="suspicious_zero",
                        severity="warning",
                        scope=field_scope(sheet_name, column["name"]),
                        evidence=f"{field_label(sheet_name, column['name'])}的 0 值占比为 {zero_rate:.1%}。",
                        impact="可能代表业务真实停摆，也可能是缺失被编码成 0。",
                        recommended_action="确认 0 的业务含义，再决定是否视为缺失或真实取值。",
                        details={"sheet_name": sheet_name, "field_name": column["name"], "zero_rate": zero_rate},
                    )
                )
                index += 1
        if 0.2 <= column["numeric_ratio"] < 0.8:
            anomalies.append(
                make_anomaly(
                    anomaly_key=anomaly_id("mixed_type", column["name"], index),
                    title=f"{field_label(sheet_name, column['name'])}的数据类型混杂",
                    category="mixed_type",
                    severity="warning",
                    scope=field_scope(sheet_name, column["name"]),
                    evidence=(
                        f"{field_label(sheet_name, column['name'])}同时包含数值与非数值内容，"
                        f"数值占比为 {column['numeric_ratio']:.1%}。"
                    ),
                    impact="类型混杂会导致聚合错误、排序异常或异常值误判。",
                    recommended_action="确认是否存在脏数据、单位拼接或编码字段混入。",
                    details={
                        "sheet_name": sheet_name,
                        "field_name": column["name"],
                        "numeric_ratio": column["numeric_ratio"],
                    },
                )
            )
            index += 1
    return anomalies


def outlier_degree(distance_iqr: float) -> str:
    if distance_iqr <= 1:
        return "轻度异常"
    if distance_iqr <= 3:
        return "明显异常"
    return "极端异常"


def detect_outliers(rows: list[dict[str, Any]], profile: dict[str, Any], sheet_name: str) -> list[dict[str, Any]]:
    anomalies = []
    index = 1
    for column in profile["columns"]:
        if column["inferred_role"] != "metric":
            continue
        values = [parse_number(row.get(column["name"])) for row in rows]
        values = [value for value in values if value is not None]
        if len(values) < 8:
            continue
        ordered = sorted(values)
        midpoint = len(ordered) // 2
        lower = ordered[:midpoint]
        upper = ordered[midpoint + (0 if len(ordered) % 2 == 0 else 1) :]
        if not lower or not upper:
            continue
        q1 = statistics.median(lower)
        q3 = statistics.median(upper)
        iqr = q3 - q1
        if iqr == 0:
            continue
        low = q1 - 1.5 * iqr
        high = q3 + 1.5 * iqr
        outliers = [value for value in values if value < low or value > high]
        if not outliers:
            continue

        deviations = []
        for value in outliers:
            boundary = low if value < low else high
            distance_iqr = abs(value - boundary) / iqr
            deviations.append((distance_iqr, value, boundary))
        deviations.sort(reverse=True)
        max_distance_iqr, most_extreme, nearest_boundary = deviations[0]
        degree = outlier_degree(max_distance_iqr)
        outlier_min = min(outliers)
        outlier_max = max(outliers)
        rate = len(outliers) / len(values)
        examples = [
            {
                "value": value,
                "distance_from_normal_boundary": round(abs(value - boundary), 4),
                "distance_iqr": round(distance_iqr, 2),
                "degree": outlier_degree(distance_iqr),
            }
            for distance_iqr, value, boundary in deviations[:5]
        ]

        anomalies.append(
            make_anomaly(
                anomaly_key=anomaly_id("outlier", column["name"], index),
                title=f"{field_label(sheet_name, column['name'])}存在{degree}",
                category="outlier",
                severity="warning",
                scope=field_scope(sheet_name, column["name"]),
                evidence=(
                    f"{field_label(sheet_name, column['name'])}按 IQR 判断的正常范围约为 "
                    f"{format_number(low)} 至 {format_number(high)}；检测到 {len(outliers)} 个异常值"
                    f"（占 {rate:.1%}），异常值范围为 {format_number(outlier_min)} 至 {format_number(outlier_max)}。"
                    f"最极端值 {format_number(most_extreme)} 超出最近正常边界 "
                    f"{format_number(abs(most_extreme - nearest_boundary))}，约为 {max_distance_iqr:.1f} 个 IQR，"
                    f"推断为{degree}。"
                ),
                impact=f"{degree}可能显著影响均值、波动和归因结果，需确认其是否为真实业务事件。",
                recommended_action="确认是否保留极端值、截尾处理，或将异常样本单独分组解释。",
                details={
                    "sheet_name": sheet_name,
                    "field_name": column["name"],
                    "method": "IQR",
                    "normal_range": {"min": low, "max": high},
                    "quartiles": {"q1": q1, "q3": q3, "iqr": iqr},
                    "outlier_count": len(outliers),
                    "outlier_rate": rate,
                    "outlier_range": {"min": outlier_min, "max": outlier_max},
                    "max_distance_iqr": round(max_distance_iqr, 2),
                    "degree": degree,
                    "examples": examples,
                },
            )
        )
        index += 1
    return anomalies


def parse_expected_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"Invalid expected date {value!r}; use YYYY-MM-DD") from exc


def detect_time_anomalies(
    rows: list[dict[str, Any]],
    profile: dict[str, Any],
    sheet_name: str,
    expected_start: date | None,
    expected_end: date | None,
) -> list[dict[str, Any]]:
    anomalies = []
    index = 1
    for name in profile.get("candidate_time_fields", []):
        parsed = []
        for row in rows:
            date_text = parse_date(row.get(name))
            if date_text is not None:
                parsed.append(datetime.fromisoformat(date_text).date())

        if expected_start:
            before = [value for value in parsed if value < expected_start]
            if before:
                anomalies.append(
                    make_anomaly(
                        anomaly_key=anomaly_id("time_before_range", name, index),
                        title=f"{field_label(sheet_name, name)}存在正常范围之前的数据",
                        category="time_before_range",
                        severity="warning",
                        scope=field_scope(sheet_name, name),
                        evidence=(
                            f"已确认正常时间范围从 {expected_start.isoformat()} 开始；检测到 {len(before)} 条更早数据，"
                            f"最早为 {min(before).isoformat()}，比正常起点早 {(expected_start - min(before)).days} 天。"
                        ),
                        impact="范围之前的数据可能属于历史补录、退款改签或跨期记录，混入当前期间会影响期间指标。",
                        recommended_action="确认这些记录应计入当前分析、单独标记，还是按业务期间排除。",
                        details={
                            "sheet_name": sheet_name,
                            "field_name": name,
                            "normal_range": {
                                "start": expected_start.isoformat(),
                                "end": expected_end.isoformat() if expected_end else None,
                            },
                            "direction": "before",
                            "count": len(before),
                            "date_range": {"min": min(before).isoformat(), "max": max(before).isoformat()},
                            "max_deviation_days": (expected_start - min(before)).days,
                        },
                    )
                )
                index += 1

        if expected_end:
            after = [value for value in parsed if value > expected_end]
            if after:
                anomalies.append(
                    make_anomaly(
                        anomaly_key=anomaly_id("time_after_range", name, index),
                        title=f"{field_label(sheet_name, name)}存在正常范围之后的数据",
                        category="time_after_range",
                        severity="warning",
                        scope=field_scope(sheet_name, name),
                        evidence=(
                            f"已确认正常时间范围截至 {expected_end.isoformat()}；检测到 {len(after)} 条更晚数据，"
                            f"最晚为 {max(after).isoformat()}，比正常终点晚 {(max(after) - expected_end).days} 天。"
                        ),
                        impact="范围之后的数据可能是提前预订、跨期履约或未来计划，混入当前期间会影响期间指标。",
                        recommended_action="确认这些记录应按预订期、发生期还是结算期分析，并决定是否单独标记。",
                        details={
                            "sheet_name": sheet_name,
                            "field_name": name,
                            "normal_range": {
                                "start": expected_start.isoformat() if expected_start else None,
                                "end": expected_end.isoformat(),
                            },
                            "direction": "after",
                            "count": len(after),
                            "date_range": {"min": min(after).isoformat(), "max": max(after).isoformat()},
                            "max_deviation_days": (max(after) - expected_end).days,
                        },
                    )
                )
                index += 1

        in_range = [
            value
            for value in parsed
            if (expected_start is None or value >= expected_start)
            and (expected_end is None or value <= expected_end)
        ]
        unique_sorted = sorted(set(in_range))
        if len(unique_sorted) < 4:
            continue
        deltas = [(unique_sorted[idx] - unique_sorted[idx - 1]).days for idx in range(1, len(unique_sorted))]
        positive_deltas = [delta for delta in deltas if delta > 0]
        if not positive_deltas:
            continue
        common_delta = Counter(positive_deltas).most_common(1)[0][0]
        if positive_deltas.count(common_delta) / len(positive_deltas) < 0.8:
            continue
        gaps = [
            {
                "from": unique_sorted[idx - 1].isoformat(),
                "to": unique_sorted[idx].isoformat(),
                "gap_days": delta,
            }
            for idx, delta in enumerate(deltas, start=1)
            if delta > common_delta
        ]
        if not gaps:
            continue
        anomalies.append(
            make_anomaly(
                anomaly_key=anomaly_id("time_gap", name, index),
                title=(
                    f"{field_label(sheet_name, name)}在正常范围内部存在时间缺口"
                    if expected_start or expected_end
                    else f"{field_label(sheet_name, name)}的时间序列存在内部缺口"
                ),
                category="time_gap",
                severity="warning",
                scope=field_scope(sheet_name, name),
                evidence=(
                    f"{field_label(sheet_name, name)}的常见间隔约为 {common_delta} 天，"
                    f"但正常范围内部出现 {len(gaps)} 处更长缺口；最大缺口为 "
                    f"{max(item['gap_days'] for item in gaps)} 天。"
                ),
                impact="时间序列不连续会影响趋势、环比和异常波动判断。",
                recommended_action="确认是否允许时间缺口，或先补齐 / 标注缺失周期。",
                details={
                    "sheet_name": sheet_name,
                    "field_name": name,
                    "direction": "within",
                    "common_interval_days": common_delta,
                    "gap_count": len(gaps),
                    "gaps": gaps[:10],
                },
            )
        )
        index += 1
    return anomalies


def load_goal_contract(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("status") != "confirmed":
        raise SystemExit("Goal contract must be confirmed before goal-related anomaly assessment")
    return contract


def load_field_mapping(path: Path | None, contract: dict[str, Any]) -> dict[str, Any]:
    if not path:
        return {"mappings": []}
    mapping = json.loads(path.read_text(encoding="utf-8"))
    if mapping.get("status") != "confirmed":
        raise SystemExit("Field mapping must be confirmed before goal-related anomaly assessment")
    if mapping.get("contract_fingerprint") != contract.get("contract_fingerprint"):
        raise SystemExit("Field mapping does not match the goal contract")
    return mapping


def apply_standard_field_name(
    anomaly: dict[str, Any],
    field_mapping: dict[str, Any],
    dataset_path: Path,
    sheet_name: str,
) -> dict[str, Any]:
    details = anomaly.get("details", {})
    source_field = details.get("field_name")
    if not source_field:
        return anomaly
    for mapping in field_mapping.get("mappings", []):
        if mapping.get("source_field") != source_field:
            continue
        if mapping.get("source_file") and mapping.get("source_file") not in {
            str(dataset_path),
            dataset_path.name,
        }:
            continue
        mapping_sheet = mapping.get("source_sheet") or mapping.get("sheet")
        if mapping_sheet and mapping_sheet != sheet_name:
            continue
        details["source_field_name"] = source_field
        details["field_name"] = mapping.get("target_field") or mapping.get("goal_field") or source_field
        anomaly["standard_field_name"] = details["field_name"]
        break
    return anomaly


def classify_goal_impact(anomaly: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    field_name = anomaly.get("details", {}).get("field_name")
    anomaly["affected_fields"] = [field_name] if field_name else []
    anomaly["affected_goal_questions"] = contract.get("questions", [])
    if not contract:
        impact_level = "blocking" if anomaly["severity"] == "blocking" else "material"
    else:
        required_data = contract.get("required_data", {})
        required = set(required_data.get("required_fields", []))
        supporting = set(required_data.get("supporting_fields", []))
        critical = required | set(required_data.get("join_keys", [])) | set(required_data.get("time_fields", []))
        category = anomaly.get("category")
        if field_name in critical:
            impact_level = "blocking" if category in {"missing_value", "mixed_type", "time_gap"} else "material"
        elif field_name in supporting:
            impact_level = "limited"
        elif category == "duplicate_row":
            impact_level = "material" if required or supporting else "limited"
            anomaly["affected_fields"] = sorted(critical | supporting)
        else:
            impact_level = "irrelevant"

    anomaly["impact_level"] = impact_level
    anomaly["severity"] = (
        "blocking"
        if impact_level == "blocking"
        else "warning"
        if impact_level in {"material", "limited"}
        else "info"
    )
    anomaly["impact_on_conclusion"] = (
        anomaly["impact"]
        if impact_level != "irrelevant"
        else "该问题位于当前目标契约之外，不影响本轮目标结论。"
    )
    anomaly["recommended_treatment"] = anomaly["recommended_action"]
    anomaly["confidence_after_ignoring"] = {
        "blocking": "low",
        "material": "low",
        "limited": "medium",
        "irrelevant": "high",
    }[impact_level]
    anomaly["goal_id"] = contract.get("goal_id")
    anomaly["contract_fingerprint"] = contract.get("contract_fingerprint")
    return anomaly


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).expanduser().resolve()
    rows = load_rows(dataset_path, args.sheet)
    profile = load_profile(Path(args.profile) if args.profile else None, dataset_path, rows)
    goal_contract = load_goal_contract(Path(args.goal_contract) if args.goal_contract else None)
    field_mapping = load_field_mapping(Path(args.field_mapping) if args.field_mapping else None, goal_contract)
    sheet_name = args.sheet or dataset_path.stem
    expected_start = parse_expected_date(args.expected_start)
    expected_end = parse_expected_date(args.expected_end)
    if expected_start and expected_end and expected_start > expected_end:
        raise SystemExit("--expected-start must be on or before --expected-end")

    anomalies = []
    anomalies.extend(detect_missing(profile, sheet_name))
    anomalies.extend(detect_duplicate_rows(rows, sheet_name))
    anomalies.extend(detect_zero_and_mixed(profile, sheet_name))
    anomalies.extend(detect_outliers(rows, profile, sheet_name))
    anomalies.extend(detect_time_anomalies(rows, profile, sheet_name, expected_start, expected_end))
    anomalies = [
        classify_goal_impact(
            apply_standard_field_name(anomaly, field_mapping, dataset_path, sheet_name),
            goal_contract,
        )
        for anomaly in anomalies
    ]
    for anomaly in anomalies:
        anomaly["dataset_path"] = str(dataset_path)
    payload = {
        "schema_version": "2.0",
        "generated_at": datetime.now().astimezone().isoformat(),
        "dataset_path": str(dataset_path),
        "sheet_name": sheet_name,
        "assessed_scopes": [{"file": str(dataset_path), "sheet": sheet_name}],
        "goal_id": goal_contract.get("goal_id"),
        "contract_fingerprint": goal_contract.get("contract_fingerprint"),
        "expected_time_range": {
            "start": expected_start.isoformat() if expected_start else None,
            "end": expected_end.isoformat() if expected_end else None,
        },
        "profile_summary": {
            "row_count": profile["row_count"],
            "column_count": profile["column_count"],
        },
        "anomalies": anomalies,
        "impact_summary": {
            level: sum(1 for anomaly in anomalies if anomaly.get("impact_level") == level)
            for level in ("blocking", "material", "limited", "irrelevant")
        },
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
