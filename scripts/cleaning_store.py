#!/usr/bin/env python3
"""Persist session state for interactive data cleaning workflows."""

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


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(str(path.resolve()).encode("utf-8"))
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def session_paths(session_dir: Path) -> tuple[Path, Path, Path, Path]:
    return (
        session_dir / "session.json",
        session_dir / "profile.json",
        session_dir / "rules.json",
        session_dir / "runs",
    )


def load_state(session_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    session_path, profile_path, rules_path, runs_dir = session_paths(session_dir)
    session = read_json(session_path, {})
    profile = read_json(profile_path, {})
    rules = read_json(rules_path, {})
    return session, profile, rules, runs_dir


def next_run_id(runs_dir: Path) -> str:
    existing = sorted(path.stem for path in runs_dir.glob("run-*.json"))
    if not existing:
        return "run-001"
    latest = max(int(name.split("-")[1]) for name in existing)
    return f"run-{latest + 1:03d}"


def cmd_init(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session_path, profile_path, rules_path, runs_dir = session_paths(session_dir)
    input_paths = [Path(item).expanduser().resolve() for item in args.inputs]
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    goal_contract = read_json(Path(args.goal_contract).expanduser().resolve(), {}) if args.goal_contract else {}
    if args.goal_contract and goal_contract.get("status") != "confirmed":
        raise SystemExit("Goal contract must be confirmed before initializing a cleaning session")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    session = {
        "session_id": f"cleaning_session_{timestamp}",
        "input_paths": [str(path) for path in input_paths],
        "input_fingerprints": {str(path): fingerprint(path) for path in input_paths},
        "output_path": str(output_path) if output_path else None,
        "target_sheet": args.target_sheet,
        "cleaning_goal": args.goal,
        "goal_id": goal_contract.get("goal_id"),
        "goal_contract_path": str(Path(args.goal_contract).expanduser().resolve()) if args.goal_contract else None,
        "goal_contract_fingerprint": goal_contract.get("contract_fingerprint"),
        "current_phase": "Phase A: Cleaning Goal",
        "active_checkpoint": "A",
        "active_run_id": None,
        "resolved_decision_ids": [],
        "decisions": [],
        "history": [{"event": "init", "at": now_iso()}],
    }
    session_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    write_json(session_path, session)
    write_json(profile_path, {})
    write_json(rules_path, {})
    print(json.dumps(session, ensure_ascii=False, indent=2))


def cmd_show(args: argparse.Namespace) -> None:
    session, profile, rules, _ = load_state(Path(args.session_dir))
    print(json.dumps({"session": session, "profile": profile, "rules": rules}, ensure_ascii=False, indent=2))


def cmd_save_profile(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, _, _ = load_state(session_dir)
    profile = read_json(Path(args.input), {})
    session["current_phase"] = "Phase B: Structure Profiling"
    session["active_checkpoint"] = "B"
    session.setdefault("history", []).append({"event": "save_profile", "at": now_iso()})
    write_json(session_dir / "profile.json", profile)
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "profile_items": len(profile.get("items", []))}, ensure_ascii=False, indent=2))


def cmd_save_rules(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, _, _ = load_state(session_dir)
    rules = read_json(Path(args.input), {})
    session["current_phase"] = "Phase C: Rule Confirmation"
    session["active_checkpoint"] = "C"
    session.setdefault("history", []).append({"event": "save_rules", "at": now_iso()})
    write_json(session_dir / "rules.json", rules)
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "rules_saved": True}, ensure_ascii=False, indent=2))


def cmd_decide(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, _, _ = load_state(session_dir)
    decision_id = f"cleaning_decision_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
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
    session.setdefault("decisions", []).append(decision)
    session.setdefault("resolved_decision_ids", []).append(decision_id)
    session.setdefault("history", []).append({"event": "decide", "decision_id": decision_id, "at": now_iso()})
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "decision_id": decision_id}, ensure_ascii=False, indent=2))


def cmd_confirm_exclusions(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, rules, _ = load_state(session_dir)
    candidates = [
        candidate
        for item in rules.get("items", [])
        for candidate in item.get("exclusion_candidates", [])
    ]
    if not candidates:
        print(json.dumps({"ok": True, "message": "没有需要确认的排除候选行"}, ensure_ascii=False, indent=2))
        return
    if not (args.accept_suggested or args.keep_all or args.exclude or args.keep):
        raise SystemExit("请使用 --accept-suggested、--keep-all、--exclude 或 --keep 提供用户确认结果")

    exclude_ids = set(args.exclude or [])
    keep_ids = set(args.keep or [])
    duplicated = exclude_ids & keep_ids
    if duplicated:
        raise SystemExit(f"同一候选不能同时保留和排除：{', '.join(sorted(duplicated))}")
    known_ids = {candidate.get("id") for candidate in candidates}
    unknown_ids = (exclude_ids | keep_ids) - known_ids
    if unknown_ids:
        raise SystemExit(f"找不到排除候选：{', '.join(sorted(unknown_ids))}")

    for candidate in candidates:
        candidate_id = candidate.get("id")
        if args.accept_suggested:
            candidate["decision"] = candidate.get("suggested_action", "exclude")
        if args.keep_all:
            candidate["decision"] = "keep"
        if candidate_id in exclude_ids:
            candidate["decision"] = "exclude"
        if candidate_id in keep_ids:
            candidate["decision"] = "keep"

    counts = {
        decision: sum(1 for candidate in candidates if candidate.get("decision") == decision)
        for decision in ("pending", "exclude", "keep")
    }
    decision_id = f"exclusion_decision_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
    decision = {
        "id": decision_id,
        "target_type": "exclusion_candidates",
        "choice": "confirmed",
        "accept_suggested": args.accept_suggested,
        "keep_all": args.keep_all,
        "exclude_ids": sorted(exclude_ids),
        "keep_ids": sorted(keep_ids),
        "counts": counts,
        "timestamp": now_iso(),
    }
    session.setdefault("decisions", []).append(decision)
    session.setdefault("resolved_decision_ids", []).append(decision_id)
    session["current_phase"] = "Phase D: Exclusion Decisions Confirmed"
    session["active_checkpoint"] = "D"
    session.setdefault("history", []).append(
        {"event": "confirm_exclusions", "decision_id": decision_id, "counts": counts, "at": now_iso()}
    )
    write_json(session_dir / "rules.json", rules)
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "decision_id": decision_id, "counts": counts}, ensure_ascii=False, indent=2))


def cmd_start_run(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, rules, runs_dir = load_state(session_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = next_run_id(runs_dir)
    session["active_run_id"] = run_id
    session["active_checkpoint"] = args.checkpoint
    session["current_phase"] = "Phase E: Cleaning Execution"
    session.setdefault("history", []).append({"event": "start_run", "run_id": run_id, "at": now_iso()})
    write_json(
        runs_dir / f"{run_id}.json",
        {
            "run_id": run_id,
            "created_at": now_iso(),
            "checkpoint_basis": args.checkpoint,
            "rules_snapshot": rules,
            "dry_run_summary": {},
            "output_path": session.get("output_path"),
            "target_sheet": session.get("target_sheet"),
            "status": "in_progress",
        },
    )
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "run_id": run_id}, ensure_ascii=False, indent=2))


def cmd_save_run(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, _, runs_dir = load_state(session_dir)
    run_id = args.run_id or session.get("active_run_id")
    if not run_id:
        raise SystemExit("No active run_id; call start-run first")
    current = read_json(runs_dir / f"{run_id}.json", {})
    incoming = read_json(Path(args.input), {})
    current.update(incoming)
    current["run_id"] = run_id
    current["saved_at"] = now_iso()
    current["status"] = args.status
    write_json(runs_dir / f"{run_id}.json", current)
    session.setdefault("history", []).append({"event": "save_run", "run_id": run_id, "at": now_iso()})
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "run_id": run_id, "status": args.status}, ensure_ascii=False, indent=2))


def cmd_invalidate(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    session, _, _, runs_dir = load_state(session_dir)
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


def cmd_confirm_handoff(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    handoff_path = session_dir / "handoff.json"
    handoff = read_json(handoff_path, {})
    if not handoff:
        raise SystemExit(f"Handoff file not found or empty: {handoff_path}")
    if handoff.get("cleaning_status") != "completed":
        raise SystemExit("Cleaning is not completed; analysis handoff cannot be confirmed")
    gate = handoff.setdefault("analysis_gate", {})
    gate["status"] = "confirmed"
    gate["confirmed_at"] = now_iso()
    gate["confirmation_note"] = args.note
    write_json(handoff_path, handoff)

    session, _, _, _ = load_state(session_dir)
    session["current_phase"] = "Handoff confirmed; analysis may start"
    session.setdefault("history", []).append(
        {"event": "confirm_handoff", "note": args.note, "at": now_iso()}
    )
    write_json(session_dir / "session.json", session)
    print(json.dumps({"ok": True, "analysis_gate": "confirmed"}, ensure_ascii=False, indent=2))


def cmd_confirm_analysis_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    handoff_path = session_dir / "handoff.json"
    handoff = read_json(handoff_path, {})
    if not handoff:
        raise SystemExit(f"Handoff file not found or empty: {handoff_path}")
    if handoff.get("analysis_gate", {}).get("status") != "confirmed":
        raise SystemExit("请先确认清洗结果，再确认分析目标")
    goal = args.goal.strip()
    if not goal:
        raise SystemExit("分析目标不能为空")
    available_sheets = [
        item.get("output_sheet")
        for item in handoff.get("output_sheets", [])
        if item.get("output_sheet")
    ]
    selected_sheets = args.analysis_sheets or available_sheets
    unknown_sheets = sorted(set(selected_sheets) - set(available_sheets))
    if available_sheets and unknown_sheets:
        raise SystemExit(f"分析范围包含不存在的工作表：{', '.join(unknown_sheets)}")

    handoff["analysis_goal_gate"] = {
        "status": "confirmed",
        "confirmed_at": now_iso(),
        "goal": goal,
        "decision_object": args.decision_object.strip(),
        "focus": args.focus.strip(),
        "output_depth": args.output_depth,
        "visualization_mode": args.visualization_mode,
        "report_format": args.report_format,
        "business_context": args.business_context.strip(),
        "analysis_sheets": selected_sheets,
    }
    write_json(handoff_path, handoff)

    session, _, _, _ = load_state(session_dir)
    session["current_phase"] = "Analysis goal confirmed; analysis may start"
    session.setdefault("history", []).append(
        {
            "event": "confirm_analysis_goal",
            "goal": goal,
            "analysis_sheets": selected_sheets,
            "at": now_iso(),
        }
    )
    write_json(session_dir / "session.json", session)
    print(
        json.dumps(
            {
                "ok": True,
                "analysis_goal_gate": "confirmed",
                "goal": goal,
                "analysis_sheets": selected_sheets,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--session-dir", required=True)
    init.add_argument("--inputs", nargs="+", required=True)
    init.add_argument("--output")
    init.add_argument("--target-sheet", default="原始数据_清洗后")
    init.add_argument("--goal", required=True)
    init.add_argument("--goal-contract")
    init.set_defaults(func=cmd_init)

    show = subparsers.add_parser("show")
    show.add_argument("--session-dir", required=True)
    show.set_defaults(func=cmd_show)

    save_profile = subparsers.add_parser("save-profile")
    save_profile.add_argument("--session-dir", required=True)
    save_profile.add_argument("--input", required=True)
    save_profile.set_defaults(func=cmd_save_profile)

    save_rules = subparsers.add_parser("save-rules")
    save_rules.add_argument("--session-dir", required=True)
    save_rules.add_argument("--input", required=True)
    save_rules.set_defaults(func=cmd_save_rules)

    decide = subparsers.add_parser("decide")
    decide.add_argument("--session-dir", required=True)
    decide.add_argument("--target-type", default="cleaning_rule")
    decide.add_argument("--target-id", required=True)
    decide.add_argument("--choice", required=True, choices=["accept", "ignore", "custom_rule", "need_more_data"])
    decide.add_argument("--rule-text", default="")
    decide.add_argument("--rationale", default="")
    decide.add_argument("--invalidates-from-phase", default="Phase C")
    decide.set_defaults(func=cmd_decide)

    confirm_exclusions = subparsers.add_parser("confirm-exclusions")
    confirm_exclusions.add_argument("--session-dir", required=True)
    confirm_exclusions.add_argument(
        "--accept-suggested",
        action="store_true",
        help="Apply each candidate's suggested action; currently summary/note/signoff candidates suggest exclusion.",
    )
    confirm_exclusions.add_argument("--keep-all", action="store_true", help="Keep every candidate row.")
    confirm_exclusions.add_argument("--exclude", nargs="*", metavar="CANDIDATE_ID")
    confirm_exclusions.add_argument("--keep", nargs="*", metavar="CANDIDATE_ID")
    confirm_exclusions.set_defaults(func=cmd_confirm_exclusions)

    start_run = subparsers.add_parser("start-run")
    start_run.add_argument("--session-dir", required=True)
    start_run.add_argument("--checkpoint", default="D", choices=["A", "B", "C", "D", "E"])
    start_run.set_defaults(func=cmd_start_run)

    save_run = subparsers.add_parser("save-run")
    save_run.add_argument("--session-dir", required=True)
    save_run.add_argument("--input", required=True)
    save_run.add_argument("--run-id")
    save_run.add_argument("--status", default="accepted")
    save_run.set_defaults(func=cmd_save_run)

    invalidate = subparsers.add_parser("invalidate")
    invalidate.add_argument("--session-dir", required=True)
    invalidate.add_argument("--checkpoint", required=True, choices=["A", "B", "C", "D", "E"])
    invalidate.add_argument("--reason", required=True)
    invalidate.set_defaults(func=cmd_invalidate)

    confirm_handoff = subparsers.add_parser("confirm-handoff")
    confirm_handoff.add_argument("--session-dir", required=True)
    confirm_handoff.add_argument("--note", default="用户已确认清洗结果并同意继续分析")
    confirm_handoff.set_defaults(func=cmd_confirm_handoff)

    confirm_goal = subparsers.add_parser("confirm-analysis-goal")
    confirm_goal.add_argument("--session-dir", required=True)
    confirm_goal.add_argument("--goal", required=True)
    confirm_goal.add_argument("--decision-object", default="")
    confirm_goal.add_argument("--focus", default="")
    confirm_goal.add_argument("--output-depth", choices=["简要", "标准", "深入"], default="标准")
    confirm_goal.add_argument(
        "--visualization-mode",
        choices=["自动判定", "不出图", "需要图表"],
        default="自动判定",
    )
    confirm_goal.add_argument(
        "--report-format",
        choices=["Markdown", "HTML", "Markdown + HTML"],
        default="Markdown + HTML",
    )
    confirm_goal.add_argument("--business-context", default="")
    confirm_goal.add_argument("--analysis-sheets", nargs="*")
    confirm_goal.set_defaults(func=cmd_confirm_analysis_goal)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
