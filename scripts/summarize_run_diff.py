#!/usr/bin/env python3
"""Summarize differences between analysis runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(payload: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else key
            result.update(flatten(value, next_prefix))
        return result
    if isinstance(payload, list):
        return {prefix: payload}
    return {prefix: payload}


def compare(old_payload: dict[str, Any], new_payload: dict[str, Any]) -> list[dict[str, Any]]:
    old_flat = flatten(old_payload)
    new_flat = flatten(new_payload)
    keys = sorted(set(old_flat) | set(new_flat))
    diffs = []
    for key in keys:
        if old_flat.get(key) == new_flat.get(key):
            continue
        diffs.append({"field": key, "old": old_flat.get(key), "new": new_flat.get(key)})
    return diffs


def render_markdown(old_name: str, new_name: str, diffs: list[dict[str, Any]]) -> str:
    lines = [
        "# Run Diff Summary",
        "",
        f"**From:** `{old_name}`",
        f"**To:** `{new_name}`",
        "",
    ]
    if not diffs:
        lines.append("两轮 run 没有差异。")
        return "\n".join(lines)
    lines.append("## Changed Fields")
    for diff in diffs:
        lines.append(f"- `{diff['field']}`")
        lines.append(f"  - old: `{json.dumps(diff['old'], ensure_ascii=False)}`")
        lines.append(f"  - new: `{json.dumps(diff['new'], ensure_ascii=False)}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", help="Session directory containing runs/")
    parser.add_argument("--old-run", help="Old run JSON file")
    parser.add_argument("--new-run", help="New run JSON file")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    return parser.parse_args()


def resolve_run_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.old_run and args.new_run:
        return Path(args.old_run), Path(args.new_run)
    if not args.session_dir:
        raise SystemExit("Provide --session-dir or both --old-run and --new-run")
    run_dir = Path(args.session_dir) / "runs"
    run_files = sorted(run_dir.glob("run-*.json"))
    if len(run_files) < 2:
        raise SystemExit("Need at least two run files to summarize differences")
    return run_files[-2], run_files[-1]


def main() -> None:
    args = parse_args()
    old_path, new_path = resolve_run_paths(args)
    old_payload = read_json(old_path)
    new_payload = read_json(new_path)
    diffs = compare(old_payload, new_payload)
    if args.format == "markdown":
        print(render_markdown(old_path.name, new_path.name, diffs))
        return
    print(
        json.dumps(
            {"from": old_path.name, "to": new_path.name, "diff_count": len(diffs), "diffs": diffs},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
