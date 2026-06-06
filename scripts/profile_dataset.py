#!/usr/bin/env python3
"""Profile CSV/XLSX datasets for interactive analysis sessions."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - optional dependency
    load_workbook = None


DATE_HINTS = ("date", "time", "day", "week", "month", "year", "dt")
ID_HINTS = (
    "id",
    "uuid",
    "code",
    "no",
    "编号",
    "订单号",
    "单号",
    "卡号",
    "票号",
    "行号",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Path to a CSV or XLSX file")
    parser.add_argument("--sheet", help="Worksheet name for XLSX input")
    parser.add_argument("--output", help="Write JSON output to a file")
    return parser.parse_args()


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        if len(text) not in {6, 8}:
            return None
        if not text.startswith(("19", "20")):
            return None
    elif not any(separator in text for separator in ("-", "/", ":", "T", " ")):
        return None
    formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m",
        "%Y/%m",
        "%Y%m%d",
        "%Y%m",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return None


def load_rows(path: Path, sheet_name: str | None = None) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            reader = csv.DictReader(handle, dialect=dialect)
            return [dict(row) for row in reader]
    if suffix == ".xlsx":
        if load_workbook is None:
            raise SystemExit("openpyxl is required to profile .xlsx files")
        workbook = load_workbook(path, read_only=True, data_only=True)
        worksheet = workbook[sheet_name] if sheet_name else workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(cell).strip() if cell is not None else f"column_{idx+1}" for idx, cell in enumerate(rows[0])]
        result = []
        for row in rows[1:]:
            result.append({headers[idx]: row[idx] if idx < len(row) else None for idx in range(len(headers))})
        return result
    raise SystemExit(f"Unsupported dataset format: {path.suffix}")


def summarize_column(name: str, values: list[Any]) -> dict[str, Any]:
    non_empty = [value for value in values if value not in (None, "")]
    missing_count = len(values) - len(non_empty)
    numeric_values = [number for number in (parse_number(value) for value in non_empty) if number is not None]
    date_values = [date for date in (parse_date(value) for value in non_empty) if date is not None]
    sample_values = []
    seen = set()
    for value in non_empty:
        text = str(value)
        if text not in seen:
            sample_values.append(text)
            seen.add(text)
        if len(sample_values) >= 5:
            break

    distinct_count = len(set(map(str, non_empty))) if non_empty else 0
    numeric_ratio = len(numeric_values) / len(non_empty) if non_empty else 0
    date_ratio = len(date_values) / len(non_empty) if non_empty else 0

    inferred_role = "dimension"
    lowered = name.lower()
    if numeric_ratio >= 0.8 and not any(hint in lowered for hint in ID_HINTS):
        inferred_role = "metric"
    elif date_ratio >= 0.8 or any(hint in lowered for hint in DATE_HINTS):
        inferred_role = "time"
    elif any(hint in lowered for hint in ID_HINTS):
        inferred_role = "identifier"

    summary = {
        "name": name,
        "missing_count": missing_count,
        "missing_rate": round(missing_count / len(values), 4) if values else 0,
        "distinct_count": distinct_count,
        "sample_values": sample_values,
        "numeric_ratio": round(numeric_ratio, 4),
        "date_ratio": round(date_ratio, 4),
        "inferred_role": inferred_role,
    }
    if numeric_values:
        ordered = sorted(numeric_values)
        summary["numeric_summary"] = {
            "min": ordered[0],
            "max": ordered[-1],
            "mean": round(sum(ordered) / len(ordered), 4),
            "zero_rate": round(sum(1 for value in ordered if value == 0) / len(ordered), 4),
        }
    if date_values:
        ordered = sorted(date_values)
        summary["date_summary"] = {"min": ordered[0], "max": ordered[-1]}
    return summary


def build_profile(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = list(rows[0].keys()) if rows else []
    column_summaries = []
    for column in columns:
        column_summaries.append(summarize_column(column, [row.get(column) for row in rows]))

    roles = Counter(summary["inferred_role"] for summary in column_summaries)
    return {
        "dataset_path": str(path),
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": column_summaries,
        "candidate_time_fields": [summary["name"] for summary in column_summaries if summary["inferred_role"] == "time"],
        "candidate_metric_fields": [summary["name"] for summary in column_summaries if summary["inferred_role"] == "metric"],
        "candidate_dimension_fields": [summary["name"] for summary in column_summaries if summary["inferred_role"] == "dimension"],
        "role_counts": dict(roles),
    }


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).expanduser().resolve()
    rows = load_rows(dataset_path, args.sheet)
    profile = build_profile(dataset_path, rows)
    payload = json.dumps(profile, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
