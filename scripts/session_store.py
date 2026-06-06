#!/usr/bin/env python3
"""Persist session state for interactive data analysis workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprint(dataset_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(str(dataset_path.resolve()).encode("utf-8"))
    with dataset_path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
    return f"sha256:{digest.hexdigest()}"


def session_paths(session_dir: Path) -> tuple[Path, Path, Path]:
    return (
        session_dir / "session.json",
        session_dir / "anomalies.json",
        session_dir / "runs",
    )


def load_state(session_dir: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    session_path, anomalies_path, runs_dir = session_paths(session_dir)
    session = read_json(session_path, {})
    anomalies = read_json(anomalies_path, {"anomalies": []})
    return session, anomalies, runs_dir


def cmd_init(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    dataset_path = Path(args.dataset).expanduser().resolve()
    session_path, anomalies_path, runs_dir = session_paths(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    session = {
        "session_id": f"session_{timestamp}",
        "dataset_path": str(dataset_path),
        "dataset_fingerprint": fingerprint(dataset_path),
        "current_phase": "Phase 1: Intake",
        "analysis_goal": args.goal,
        "analysis_goal_status": "confirmed" if args.goal_confirmed else "pending_confirmation",
        "decision_object": args.decision_object,
        "focus": args.focus,
        "output_depth": args.output_depth,
        "visualization_mode": args.visualization_mode,
        "report_format": args.report_format,
        "business_context": args.business_context,
        "analysis_sheets": args.analysis_sheets,
        "audience": args.audience,
        "active_run_id": None,
        "active_checkpoint": "A",
        "open_anomaly_ids": [],
        "resolved_decision_ids": [],
        "decisions": [],
        "history": [{"event": "init", "at": now_iso()}],
    }
    write_json(session_path, session)
    write_json(anomalies_path, {"generated_at": now_iso(), "dataset_path": str(dataset_path), "anomalies": []})
    print(json.dumps(session, ensure_ascii=False, indent=2))


def cmd_show(args: argparse.Namespace) -> None:
    session, anomalies, _ = load_state(Path(args.session_dir))
    payload = {"session": session, "anomalies": anomalies}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_set_phase(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, anomalies, _ = load_state(session_dir)
    session["current_phase"] = args.phase
    session.setdefault("history", []).append({"event": "set_phase", "phase": args.phase, "at": now_iso()})
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "phase": args.phase}, ensure_ascii=False, indent=2))


def cmd_merge_anomalies(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, _ = load_state(session_dir)
    incoming = read_json(Path(args.input), {"anomalies": []})
    anomaly_map = {item["id"]: item for item in incoming.get("anomalies", [])}
    open_ids = [item_id for item_id, item in anomaly_map.items() if item["status"] == "open"]
    session["open_anomaly_ids"] = open_ids
    session.setdefault("history", []).append(
        {"event": "merge_anomalies", "count": len(anomaly_map), "open_count": len(open_ids), "at": now_iso()}
    )
    write_json(session_dir / "session.json", session)
    write_json(session_dir / "anomalies.json", incoming)
    print(json.dumps({"ok": True, "open_anomaly_ids": open_ids}, ensure_ascii=False, indent=2))


def cmd_decide(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, anomalies_payload, _ = load_state(session_dir)
    decisions = session.setdefault("decisions", [])
    decision_id = f"decision_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
    decision = {
        "id": decision_id,
        "target_type": args.target_type,
        "target_id": args.target_id,
        "choice": args.choice,
        "rule_text": args.rule_text,
        "rationale": args.rationale,
        "invalidates_from_phase": args.invalidates_from_phase,
        "timestamp": now_iso(),
    }
    decisions.append(decision)
    session.setdefault("resolved_decision_ids", []).append(decision_id)
    anomalies = anomalies_payload.get("anomalies", [])
    for anomaly in anomalies:
        if anomaly["id"] != args.target_id:
            continue
        anomaly["status"] = "ignored" if args.choice == "ignore" else "resolved"
    session["open_anomaly_ids"] = [anomaly["id"] for anomaly in anomalies if anomaly["status"] == "open"]
    session.setdefault("history", []).append({"event": "decide", "decision_id": decision_id, "at": now_iso()})
    write_json(session_dir / "session.json", session)
    write_json(session_dir / "anomalies.json", anomalies_payload)
    print(json.dumps({"ok": True, "decision_id": decision_id}, ensure_ascii=False, indent=2))


def next_run_id(runs_dir: Path) -> str:
    existing = sorted(path.stem for path in runs_dir.glob("run-*.json"))
    if not existing:
        return "run-001"
    latest = max(int(name.split("-")[1]) for name in existing)
    return f"run-{latest + 1:03d}"


def cmd_start_run(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, runs_dir = load_state(session_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = next_run_id(runs_dir)
    session["active_run_id"] = run_id
    session["active_checkpoint"] = args.checkpoint
    session["current_phase"] = "Phase 4: SOP Execution"
    session.setdefault("history", []).append({"event": "start_run", "run_id": run_id, "at": now_iso()})
    write_json(
        runs_dir / f"{run_id}.json",
        {
            "run_id": run_id,
            "created_at": now_iso(),
            "checkpoint_basis": args.checkpoint,
            "accepted_assumptions": [],
            "ignored_anomalies": [],
            "custom_rules": [],
            "chart_decision": {},
            "chart_files": [],
            "report_files": [],
            "summary": "",
            "report_sections": {},
            "status": "in_progress",
        },
    )
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "run_id": run_id}, ensure_ascii=False, indent=2))


def cmd_save_run(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, anomalies_payload, runs_dir = load_state(session_dir)
    run_id = args.run_id or session.get("active_run_id")
    if not run_id:
        raise SystemExit("No active run_id; call start-run first")
    current = read_json(runs_dir / f"{run_id}.json", {})
    incoming = read_json(Path(args.input), {})
    current.update(incoming)
    current["run_id"] = run_id
    current["saved_at"] = now_iso()
    current["ignored_anomalies"] = [
        anomaly["id"] for anomaly in anomalies_payload.get("anomalies", []) if anomaly["status"] == "ignored"
    ]
    current["custom_rules"] = [
        decision for decision in session.get("decisions", []) if decision.get("choice") == "custom_rule"
    ]
    current["status"] = args.status
    write_json(runs_dir / f"{run_id}.json", current)
    session.setdefault("history", []).append({"event": "save_run", "run_id": run_id, "at": now_iso()})
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "run_id": run_id, "status": args.status}, ensure_ascii=False, indent=2))


def cmd_invalidate(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, runs_dir = load_state(session_dir)
    session["active_checkpoint"] = args.checkpoint
    session["current_phase"] = f"Rollback from checkpoint {args.checkpoint}"
    session.setdefault("history", []).append(
        {"event": "invalidate", "checkpoint": args.checkpoint, "reason": args.reason, "at": now_iso()}
    )
    for run_file in sorted(runs_dir.glob("run-*.json")):
        payload = read_json(run_file, {})
        payload["status"] = "superseded"
        payload["invalidated_by"] = {"checkpoint": args.checkpoint, "reason": args.reason, "at": now_iso()}
        write_json(run_file, payload)
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "checkpoint": args.checkpoint}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--session-dir", required=True)
    init.add_argument("--dataset", required=True)
    init.add_argument("--goal", required=True)
    init.add_argument("--goal-confirmed", action="store_true")
    init.add_argument("--decision-object", default="")
    init.add_argument("--focus", default="")
    init.add_argument("--output-depth", choices=["简要", "标准", "深入"], default="标准")
    init.add_argument(
        "--visualization-mode",
        choices=["自动判定", "不出图", "需要图表"],
        default="自动判定",
    )
    init.add_argument(
        "--report-format",
        choices=["Markdown", "HTML", "Markdown + HTML"],
        default="Markdown + HTML",
    )
    init.add_argument("--business-context", default="")
    init.add_argument("--analysis-sheets", nargs="*", default=[])
    init.add_argument("--audience", default="未指定")
    init.set_defaults(func=cmd_init)

    show = subparsers.add_parser("show")
    show.add_argument("--session-dir", required=True)
    show.set_defaults(func=cmd_show)

    set_phase = subparsers.add_parser("set-phase")
    set_phase.add_argument("--session-dir", required=True)
    set_phase.add_argument("--phase", required=True)
    set_phase.set_defaults(func=cmd_set_phase)

    merge = subparsers.add_parser("merge-anomalies")
    merge.add_argument("--session-dir", required=True)
    merge.add_argument("--input", required=True)
    merge.set_defaults(func=cmd_merge_anomalies)

    decide = subparsers.add_parser("decide")
    decide.add_argument("--session-dir", required=True)
    decide.add_argument("--target-type", default="anomaly")
    decide.add_argument("--target-id", required=True)
    decide.add_argument("--choice", required=True, choices=["accept", "ignore", "custom_rule", "need_more_data"])
    decide.add_argument("--rule-text", default="")
    decide.add_argument("--rationale", default="")
    decide.add_argument("--invalidates-from-phase", default="Phase 3")
    decide.set_defaults(func=cmd_decide)

    start_run = subparsers.add_parser("start-run")
    start_run.add_argument("--session-dir", required=True)
    start_run.add_argument("--checkpoint", default="C")
    start_run.set_defaults(func=cmd_start_run)

    save_run = subparsers.add_parser("save-run")
    save_run.add_argument("--session-dir", required=True)
    save_run.add_argument("--input", required=True)
    save_run.add_argument("--run-id")
    save_run.add_argument("--status", default="accepted")
    save_run.set_defaults(func=cmd_save_run)

    invalidate = subparsers.add_parser("invalidate")
    invalidate.add_argument("--session-dir", required=True)
    invalidate.add_argument("--checkpoint", required=True, choices=["A", "B", "C", "D"])
    invalidate.add_argument("--reason", required=True)
    invalidate.set_defaults(func=cmd_invalidate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
