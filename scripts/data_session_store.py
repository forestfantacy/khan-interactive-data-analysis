#!/usr/bin/env python3
"""Manage discovery, goal-home navigation, multi-goal state, and intent co-creation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


GOAL_ARTIFACTS = ("goal-contract.json", "field-mapping.json", "quality-impact.json")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def payload_fingerprint(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("contract_fingerprint", None)
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def load_json_value(value: str | None, expected_type: type, default: Any) -> Any:
    if not value:
        return default
    stripped = value.lstrip()
    if stripped.startswith(("[", "{")):
        payload = json.loads(value)
    else:
        path = Path(value).expanduser()
        if not path.exists():
            raise SystemExit(f"JSON file not found: {path}")
        payload = read_json(path, default)
    if not isinstance(payload, expected_type):
        raise SystemExit(f"Expected JSON {expected_type.__name__}")
    return payload


def load_list(value: str | None) -> list[Any]:
    return load_json_value(value, list, [])


def load_object(value: str | None) -> dict[str, Any]:
    return load_json_value(value, dict, {})


def session_path(session_dir: Path) -> Path:
    return session_dir / "session.json"


def goal_dir(session_dir: Path, goal_id: str) -> Path:
    return session_dir / "goals" / goal_id


def intent_path(session_dir: Path, intent_id: str) -> Path:
    return session_dir / "intent-sessions" / f"{intent_id}.json"


def load_state(session_dir: Path) -> dict[str, Any]:
    state = read_json(session_path(session_dir), {})
    if not state:
        raise SystemExit("Initialize the data session first")
    state.setdefault("schema_version", "2.0")
    state.setdefault("home_status", "ready")
    state.setdefault("active_goal_id", None)
    state.setdefault("active_intent_id", None)
    state.setdefault("goal_order", [])
    state.setdefault("goals", {})
    state.setdefault("history", [])
    return state


def save_state(session_dir: Path, state: dict[str, Any]) -> None:
    write_json(session_path(session_dir), state)


def mirror_goal_artifacts(session_dir: Path, selected_goal_dir: Path) -> None:
    for filename in GOAL_ARTIFACTS:
        source = selected_goal_dir / filename
        destination = session_dir / filename
        if source.exists():
            shutil.copyfile(source, destination)
        elif destination.exists():
            destination.unlink()


def clear_goal_artifact_mirrors(session_dir: Path) -> None:
    for filename in GOAL_ARTIFACTS:
        path = session_dir / filename
        if path.exists():
            path.unlink()


def active_goal_id(state: dict[str, Any], explicit_goal_id: str | None = None) -> str:
    goal_id = explicit_goal_id or state.get("active_goal_id")
    if not goal_id:
        raise SystemExit("No active goal; select or resume a goal first")
    if goal_id not in state.get("goals", {}):
        raise SystemExit(f"Unknown goal: {goal_id}")
    return goal_id


def flatten_candidates(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for category in catalog.get("categories", [])
        for candidate in category.get("candidates", [])
    ]


def goal_record_from_contract(
    contract: dict[str, Any],
    *,
    source: str,
    source_id: str | None = None,
    parent_goal_id: str | None = None,
) -> dict[str, Any]:
    return {
        "goal_id": contract["goal_id"],
        "title": contract["goal"],
        "goal_type": contract["goal_type"],
        "status": "selected",
        "source": source,
        "source_id": source_id,
        "parent_goal_id": parent_goal_id,
        "contract_fingerprint": contract["contract_fingerprint"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "summary": "",
        "targeted_files": [],
        "report_files": [],
        "completed_at": None,
    }


def activate_goal(
    session_dir: Path,
    state: dict[str, Any],
    contract: dict[str, Any],
    *,
    source: str,
    source_id: str | None = None,
    parent_goal_id: str | None = None,
) -> None:
    goal_id = contract["goal_id"]
    destination = goal_dir(session_dir, goal_id)
    write_json(destination / "goal-contract.json", contract)
    write_json(
        destination / "field-mapping.json",
        {
            "schema_version": "1.0",
            "goal_id": goal_id,
            "contract_fingerprint": contract["contract_fingerprint"],
            "status": "pending_confirmation",
            "mappings": [],
        },
    )
    record = state["goals"].get(goal_id) or goal_record_from_contract(
        contract,
        source=source,
        source_id=source_id,
        parent_goal_id=parent_goal_id,
    )
    record.update(
        {
            "title": contract["goal"],
            "goal_type": contract["goal_type"],
            "status": "selected",
            "contract_fingerprint": contract["contract_fingerprint"],
            "updated_at": now_iso(),
        }
    )
    state["goals"][goal_id] = record
    if goal_id not in state["goal_order"]:
        state["goal_order"].append(goal_id)
    state["active_goal_id"] = goal_id
    state["active_intent_id"] = None
    state["home_status"] = "goal_active"
    state["goal_contract_status"] = "confirmed"
    state.setdefault("history", []).append(
        {"event": "activate_goal", "goal_id": goal_id, "source": source, "at": now_iso()}
    )
    mirror_goal_artifacts(session_dir, destination)


def candidate_contract(
    candidate: dict[str, Any],
    discovery_id: str,
    goal_id: str,
    decision_object: str = "",
    parent_goal_id: str | None = None,
) -> dict[str, Any]:
    required_data = candidate.get("required_data", {})
    contract = {
        "schema_version": "1.0",
        "goal_id": goal_id,
        "goal": candidate["title"],
        "goal_type": candidate.get("goal_type", "business_analysis"),
        "decision_object": decision_object,
        "questions": candidate.get("questions") or [candidate.get("business_question", candidate["title"])],
        "required_data": {
            "scope": required_data.get("scope", candidate.get("required_scope", [])),
            "required_fields": required_data.get("required_fields", []),
            "supporting_fields": required_data.get("supporting_fields", []),
            "join_keys": required_data.get("join_keys", []),
            "time_fields": required_data.get("time_fields", []),
            "metric_definitions": required_data.get("metric_definitions", []),
        },
        "excluded_scope": [],
        "assumptions": candidate.get("assumptions", []),
        "candidate_id": candidate.get("id"),
        "parent_goal_id": parent_goal_id,
        "feasibility": candidate.get("feasibility"),
        "discovery_id": discovery_id,
        "status": "confirmed",
        "confirmed_at": now_iso(),
    }
    contract["contract_fingerprint"] = payload_fingerprint(contract)
    return contract


def migrate_legacy_goal(session_dir: Path, state: dict[str, Any]) -> None:
    legacy_contract = read_json(session_dir / "goal-contract.json", {})
    if legacy_contract.get("status") != "confirmed":
        return
    goal_id = legacy_contract.get("goal_id")
    if not goal_id or goal_id in state["goals"]:
        return
    destination = goal_dir(session_dir, goal_id)
    destination.mkdir(parents=True, exist_ok=True)
    for filename in GOAL_ARTIFACTS:
        source = session_dir / filename
        if source.exists():
            shutil.copyfile(source, destination / filename)
    state["goals"][goal_id] = goal_record_from_contract(legacy_contract, source="legacy")
    state["goals"][goal_id]["status"] = "paused"
    state["goal_order"].append(goal_id)


def cmd_init(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    discovery = read_json(Path(args.discovery), {})
    if discovery.get("mode") != "discovery":
        raise SystemExit("Discovery input must be generated by profile_dataset.py in discovery mode")
    existing = read_json(session_path(session_dir), {})
    discovery_changed = bool(existing.get("discovery_id") and existing.get("discovery_id") != discovery.get("discovery_id"))
    goals = existing.get("goals", {})
    if discovery_changed:
        for record in goals.values():
            record["data_refresh_status"] = "needs_review"
            record["data_refresh_at"] = now_iso()
    state = {
        "schema_version": "2.0",
        "created_at": existing.get("created_at", now_iso()),
        "updated_at": now_iso(),
        "discovery_id": discovery.get("discovery_id"),
        "home_status": "ready",
        "active_goal_id": None if discovery_changed else existing.get("active_goal_id"),
        "active_intent_id": existing.get("active_intent_id"),
        "goal_contract_status": existing.get("goal_contract_status", "pending_confirmation"),
        "goal_order": existing.get("goal_order", []),
        "goals": goals,
        "history": existing.get("history", []) + [{"event": "init_or_refresh", "at": now_iso()}],
    }
    session_dir.mkdir(parents=True, exist_ok=True)
    write_json(session_dir / "discovery.json", discovery)
    write_json(session_dir / "capability-summary.json", discovery.get("capability_summary", {}))
    write_json(session_dir / "goal-catalog.json", discovery.get("goal_catalog", {}))
    write_json(session_dir / "goal-candidates.json", {"goal_candidates": discovery.get("goal_candidates", [])})
    migrate_legacy_goal(session_dir, state)
    if discovery_changed:
        clear_goal_artifact_mirrors(session_dir)
    save_state(session_dir, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_show_home(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goals = [state["goals"][goal_id] for goal_id in state["goal_order"] if goal_id in state["goals"]]
    payload = {
        "schema_version": "1.0",
        "view": "goal_home",
        "discovery_id": state.get("discovery_id"),
        "capability_summary": read_json(session_dir / "capability-summary.json", {}),
        "goal_catalog": read_json(session_dir / "goal-catalog.json", {}),
        "active_goal_id": state.get("active_goal_id"),
        "active_intent_id": state.get("active_intent_id"),
        "goals": goals,
        "custom_goal_available": True,
        "navigation": [
            "select_goal",
            "start_custom_goal",
            "resume_goal",
            "view_completed_goal",
            "refresh_discovery",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_show_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state, args.goal_id)
    destination = goal_dir(session_dir, goal_id)
    payload = {
        "goal": state["goals"][goal_id],
        "goal_contract": read_json(destination / "goal-contract.json", {}),
        "field_mapping": read_json(destination / "field-mapping.json", {}),
        "quality_impact": read_json(destination / "quality-impact.json", {}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_set_goal_status(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state, args.goal_id)
    record = state["goals"][goal_id]
    record["status"] = args.status
    record["updated_at"] = now_iso()
    if args.note:
        record.setdefault("status_notes", []).append({"status": args.status, "note": args.note, "at": now_iso()})
    state.setdefault("history", []).append(
        {"event": "set_goal_status", "goal_id": goal_id, "status": args.status, "at": now_iso()}
    )
    save_state(session_dir, state)
    print(json.dumps(record, ensure_ascii=False, indent=2))


def cmd_select_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    catalog = read_json(session_dir / "goal-catalog.json", {})
    candidate = next(
        (item for item in flatten_candidates(catalog) if item.get("id") == args.candidate_id),
        None,
    )
    if not candidate:
        raise SystemExit(f"Candidate not found: {args.candidate_id}")
    if candidate.get("feasibility") == "blocked":
        raise SystemExit("Blocked candidates require additional data before selection")
    goal_id = args.goal_id or f"goal-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    contract = candidate_contract(
        candidate,
        state.get("discovery_id", ""),
        goal_id,
        args.decision_object,
    )
    activate_goal(session_dir, state, contract, source="catalog", source_id=args.candidate_id)
    save_state(session_dir, state)
    print(json.dumps(contract, ensure_ascii=False, indent=2))


def cmd_confirm_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal = args.goal.strip()
    if not goal:
        raise SystemExit("Goal cannot be empty")
    goal_id = args.goal_id or f"goal-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    contract = {
        "schema_version": "1.0",
        "goal_id": goal_id,
        "goal": goal,
        "goal_type": args.goal_type,
        "decision_object": args.decision_object.strip(),
        "questions": load_list(args.questions),
        "required_data": {
            "scope": load_list(args.scope),
            "required_fields": args.required_fields or [],
            "supporting_fields": args.supporting_fields or [],
            "join_keys": args.join_keys or [],
            "time_fields": args.time_fields or [],
            "metric_definitions": load_list(args.metric_definitions),
        },
        "excluded_scope": load_list(args.excluded_scope),
        "assumptions": load_list(args.assumptions),
        "discovery_id": state.get("discovery_id"),
        "status": "confirmed",
        "confirmed_at": now_iso(),
    }
    contract["contract_fingerprint"] = payload_fingerprint(contract)
    activate_goal(session_dir, state, contract, source="manual")
    save_state(session_dir, state)
    print(json.dumps(contract, ensure_ascii=False, indent=2))


def active_artifact_paths(session_dir: Path, state: dict[str, Any], filename: str) -> tuple[Path, Path]:
    goal_id = active_goal_id(state)
    return goal_dir(session_dir, goal_id) / filename, session_dir / filename


def cmd_confirm_mapping(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state)
    contract = read_json(goal_dir(session_dir, goal_id) / "goal-contract.json", {})
    if contract.get("status") != "confirmed":
        raise SystemExit("Confirm the goal contract before confirming field mappings")
    payload = {
        "schema_version": "1.0",
        "goal_id": contract["goal_id"],
        "contract_fingerprint": contract["contract_fingerprint"],
        "status": "confirmed",
        "confirmed_at": now_iso(),
        "mappings": load_list(args.mappings),
    }
    write_json(goal_dir(session_dir, goal_id) / "field-mapping.json", payload)
    write_json(session_dir / "field-mapping.json", payload)
    state["goals"][goal_id]["status"] = "preparing"
    state["goals"][goal_id]["updated_at"] = now_iso()
    save_state(session_dir, state)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_save_quality(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state)
    contract = read_json(goal_dir(session_dir, goal_id) / "goal-contract.json", {})
    payload = read_json(Path(args.input), {})
    if payload.get("contract_fingerprint") != contract.get("contract_fingerprint"):
        raise SystemExit("Quality assessment does not match the active goal contract")
    path = goal_dir(session_dir, goal_id) / "quality-impact.json"
    existing = read_json(path, {})
    if existing:
        anomaly_map = {
            (item.get("dataset_path"), item.get("scope"), item.get("category"), item.get("id")): item
            for item in existing.get("anomalies", [])
        }
        for item in payload.get("anomalies", []):
            anomaly_map[(item.get("dataset_path"), item.get("scope"), item.get("category"), item.get("id"))] = item
        payload["anomalies"] = list(anomaly_map.values())
        scope_map = {
            (item.get("file"), item.get("sheet")): item
            for item in existing.get("assessed_scopes", []) + payload.get("assessed_scopes", [])
        }
        payload["assessed_scopes"] = list(scope_map.values())
    payload["impact_summary"] = {
        level: sum(1 for anomaly in payload.get("anomalies", []) if anomaly.get("impact_level") == level)
        for level in ("blocking", "material", "limited", "irrelevant")
    }
    write_json(path, payload)
    write_json(session_dir / "quality-impact.json", payload)
    print(json.dumps({"ok": True, "impact_summary": payload["impact_summary"]}, ensure_ascii=False, indent=2))


def cmd_decide_quality(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state)
    path = goal_dir(session_dir, goal_id) / "quality-impact.json"
    payload = read_json(path, {})
    if not payload:
        raise SystemExit("Save a quality impact assessment before recording decisions")
    target_ids = set(args.target_id or [])
    matched = []
    for anomaly in payload.get("anomalies", []):
        selected = anomaly.get("id") in target_ids
        if args.all_irrelevant and anomaly.get("impact_level") == "irrelevant":
            selected = True
        if not selected:
            continue
        anomaly["status"] = "ignored" if args.choice == "ignore" else "resolved"
        anomaly["decision"] = {
            "choice": args.choice,
            "rule_text": args.rule_text,
            "rationale": args.rationale,
            "decided_at": now_iso(),
        }
        matched.append(anomaly["id"])
    if target_ids - set(matched):
        raise SystemExit(f"Unknown anomaly IDs: {', '.join(sorted(target_ids - set(matched)))}")
    write_json(path, payload)
    write_json(session_dir / "quality-impact.json", payload)
    print(json.dumps({"ok": True, "updated_anomaly_ids": matched}, ensure_ascii=False, indent=2))


def intent_unknowns(known: dict[str, Any]) -> list[str]:
    unknowns = []
    if not known.get("core_question"):
        unknowns.append("core_question")
    if not known.get("focus_objects"):
        unknowns.append("focus_objects")
    if not known.get("decision_use") and not known.get("expected_output"):
        unknowns.append("decision_use")
    return unknowns


def suggested_questions(unknowns: list[str]) -> list[str]:
    prompts = {
        "core_question": "你最终最想判断、解释或决定什么？",
        "focus_objects": "重点关注哪些指标、对象、环节或问题范围？",
        "decision_use": "结果将供谁使用，主要支持什么决策或输出？",
    }
    return [prompts[item] for item in unknowns[:3]]


def cmd_start_intent(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    current_goal_id = state.get("active_goal_id")
    if current_goal_id and current_goal_id in state["goals"]:
        current = state["goals"][current_goal_id]
        if current.get("status") not in {"completed", "blocked", "superseded"}:
            current["status"] = "paused"
            current["updated_at"] = now_iso()
    intent_id = args.intent_id or f"intent-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    raw_input = args.raw_input.strip()
    payload = {
        "schema_version": "1.0",
        "intent_id": intent_id,
        "parent_goal_id": args.parent_goal_id,
        "raw_inputs": [raw_input] if raw_input else [],
        "intent_summary": "",
        "known": {
            "core_question": "",
            "focus_objects": [],
            "decision_use": "",
            "time_scope": "",
            "metrics": [],
            "comparison_basis": [],
            "suspected_causes": [],
            "expected_output": "",
        },
        "unknowns": ["core_question", "focus_objects", "decision_use"],
        "assumptions": [],
        "data_matches": [],
        "data_gaps": [],
        "turns": [{"role": "user", "content": raw_input, "at": now_iso()}] if raw_input else [],
        "readiness": "collecting",
        "suggested_questions": suggested_questions(["core_question", "focus_objects", "decision_use"]),
        "custom_candidates": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    write_json(intent_path(session_dir, intent_id), payload)
    state["active_intent_id"] = intent_id
    state["active_goal_id"] = None
    state["home_status"] = "intent_active"
    clear_goal_artifact_mirrors(session_dir)
    state.setdefault("history", []).append({"event": "start_intent", "intent_id": intent_id, "at": now_iso()})
    save_state(session_dir, state)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_update_intent(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    intent_id = args.intent_id or state.get("active_intent_id")
    if not intent_id:
        raise SystemExit("No active intent session")
    path = intent_path(session_dir, intent_id)
    payload = read_json(path, {})
    if not payload:
        raise SystemExit(f"Intent session not found: {intent_id}")
    raw_input = args.raw_input.strip()
    if raw_input:
        payload.setdefault("raw_inputs", []).append(raw_input)
        payload.setdefault("turns", []).append({"role": "user", "content": raw_input, "at": now_iso()})
    known_update = load_object(args.known)
    for key, value in known_update.items():
        if key in payload["known"] and value not in (None, "", []):
            payload["known"][key] = value
    payload["assumptions"] = list(dict.fromkeys(payload.get("assumptions", []) + load_list(args.assumptions)))
    payload["data_matches"] = load_list(args.data_matches) or payload.get("data_matches", [])
    payload["data_gaps"] = load_list(args.data_gaps) or payload.get("data_gaps", [])
    payload["unknowns"] = intent_unknowns(payload["known"])
    payload["readiness"] = "ready_for_candidates" if not payload["unknowns"] else "collecting"
    payload["suggested_questions"] = suggested_questions(payload["unknowns"])
    payload["updated_at"] = now_iso()
    write_json(path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def default_intent_summary(payload: dict[str, Any]) -> str:
    known = payload["known"]
    parts = [known.get("core_question", "")]
    if known.get("focus_objects"):
        parts.append(f"重点关注：{'、'.join(map(str, known['focus_objects']))}")
    if known.get("decision_use"):
        parts.append(f"用途：{known['decision_use']}")
    elif known.get("expected_output"):
        parts.append(f"期望输出：{known['expected_output']}")
    return "；".join(part for part in parts if part)


def cmd_summarize_intent(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    intent_id = args.intent_id or state.get("active_intent_id")
    if not intent_id:
        raise SystemExit("No active intent session")
    path = intent_path(session_dir, intent_id)
    payload = read_json(path, {})
    payload["unknowns"] = intent_unknowns(payload.get("known", {}))
    if payload["unknowns"] and not args.force:
        raise SystemExit(f"Intent is not ready; unresolved fields: {', '.join(payload['unknowns'])}")
    payload["intent_summary"] = args.summary.strip() or default_intent_summary(payload)
    payload["readiness"] = "ready_for_candidates"
    payload["summary_confirmed"] = bool(args.confirmed)
    payload["updated_at"] = now_iso()
    write_json(path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def custom_candidate(
    intent: dict[str, Any],
    capability: dict[str, Any],
    *,
    candidate_id: str,
    category: str,
    title_template: str,
    question_template: str,
    decision_value: str,
    depth: str,
    methods: list[str],
    outputs: list[str],
    needs_time: bool = False,
    needs_dimensions: bool = False,
) -> dict[str, Any]:
    known = intent["known"]
    metrics = known.get("metrics") or capability.get("metric_fields", [])[:1]
    dimensions = known.get("focus_objects") or capability.get("dimension_fields", [])[:3]
    times = capability.get("time_fields", [])[:1]
    missing = []
    if needs_time and not times:
        missing.append("明确时间字段")
    if needs_dimensions and not dimensions:
        missing.append("可用于拆分的业务对象或维度")
    feasibility = "limited" if missing else "ready"
    core = known.get("core_question") or intent.get("intent_summary") or "用户自定义问题"
    title = title_template.format(core=core)
    question = question_template.format(core=core)
    data_basis = list(dict.fromkeys(metrics + (times if needs_time else []) + dimensions))
    return {
        "id": candidate_id,
        "intent_id": intent["intent_id"],
        "category": category,
        "goal_type": "business_analysis",
        "title": title,
        "business_question": question,
        "questions": [question],
        "decision_value": decision_value,
        "business_metric": metrics[0] if metrics else "",
        "business_object": dimensions[0] if dimensions else "",
        "data_basis": data_basis,
        "analysis_depth": depth,
        "supported_conclusions": outputs,
        "unsupported_conclusions": ["不凭相关性直接下因果结论"],
        "required_scope": capability.get("scope", []),
        "required_data": {
            "scope": capability.get("scope", []),
            "required_fields": metrics + (times if needs_time else []),
            "supporting_fields": dimensions,
        },
        "recommended_methods": methods,
        "expected_outputs": outputs,
        "data_quality_risks": intent.get("data_gaps", []),
        "missing_data": missing,
        "assumptions": intent.get("assumptions", []),
        "feasibility": feasibility,
        "confidence": "medium" if feasibility == "ready" else "low",
        "estimated_cleaning": "medium",
    }


def cmd_generate_custom_candidates(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    intent_id = args.intent_id or state.get("active_intent_id")
    if not intent_id:
        raise SystemExit("No active intent session")
    path = intent_path(session_dir, intent_id)
    intent = read_json(path, {})
    if intent.get("readiness") != "ready_for_candidates" or not intent.get("summary_confirmed"):
        raise SystemExit("Confirm the intent summary before generating candidates")
    capability = read_json(session_dir / "capability-summary.json", {})
    candidates = [
        custom_candidate(
            intent,
            capability,
            candidate_id=f"{intent_id}-overview",
            category="现状与趋势",
            title_template="围绕“{core}”，当前表现怎样，变化发生在哪里？",
            question_template="围绕“{core}”，当前规模、分布和变化方向分别是什么",
            decision_value="快速建立现状基线",
            depth="overview",
            methods=["描述统计", "趋势分析"],
            outputs=["现状基线", "主要变化", "重点观察项"],
            needs_time=True,
        ),
        custom_candidate(
            intent,
            capability,
            candidate_id=f"{intent_id}-structure",
            category="结构与贡献",
            title_template="围绕“{core}”，哪些对象贡献最大，应该重点关注谁？",
            question_template="围绕“{core}”，不同对象的贡献和结构差异是什么",
            decision_value="识别重点对象和资源方向",
            depth="diagnostic",
            methods=["结构分析", "贡献度分析"],
            outputs=["贡献排名", "结构差异", "重点对象"],
            needs_dimensions=True,
        ),
        custom_candidate(
            intent,
            capability,
            candidate_id=f"{intent_id}-anomaly",
            category="异常与风险",
            title_template="围绕“{core}”，哪些异常最值得优先核查？",
            question_template="围绕“{core}”，哪些记录或对象明显偏离常见水平，影响范围有多大",
            decision_value="定位需要优先核查的问题",
            depth="diagnostic",
            methods=["异常检测", "切片对比"],
            outputs=["异常清单", "影响范围", "核查优先级"],
        ),
        custom_candidate(
            intent,
            capability,
            candidate_id=f"{intent_id}-attribution",
            category="驱动与归因",
            title_template="围绕“{core}”，哪些因素最可能推动了当前结果？",
            question_template="围绕“{core}”，主要驱动因素、支持证据和待验证原因分别是什么",
            decision_value="支持问题诊断和解释",
            depth="attribution",
            methods=["贡献分解", "假设验证"],
            outputs=["主要驱动因素", "证据链", "待验证假设"],
            needs_time=True,
            needs_dimensions=True,
        ),
        custom_candidate(
            intent,
            capability,
            candidate_id=f"{intent_id}-action",
            category="行动与监控",
            title_template="围绕“{core}”，下一步应该先处理什么并持续关注什么？",
            question_template="围绕“{core}”，行动优先级、验证指标和持续监控方式分别是什么",
            decision_value="把分析结果转化为后续动作",
            depth="action",
            methods=["优先级评估", "监控指标设计"],
            outputs=["行动优先级", "验证指标", "监控建议"],
            needs_dimensions=True,
        ),
    ]
    intent["custom_candidates"] = candidates
    intent["readiness"] = "candidates_generated"
    intent["updated_at"] = now_iso()
    write_json(path, intent)
    print(
        json.dumps(
            {
                "intent_id": intent_id,
                "intent_summary": intent.get("intent_summary"),
                "candidates": candidates,
                "recommended_candidate_id": candidates[0]["id"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_combine_custom_candidates(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    intent_id = args.intent_id or state.get("active_intent_id")
    if not intent_id:
        raise SystemExit("No active intent session")
    path = intent_path(session_dir, intent_id)
    intent = read_json(path, {})
    candidate_map = {item["id"]: item for item in intent.get("custom_candidates", [])}
    selected = [candidate_map[item] for item in args.candidate_id if item in candidate_map]
    missing = set(args.candidate_id) - set(candidate_map)
    if missing:
        raise SystemExit(f"Custom candidate not found: {', '.join(sorted(missing))}")
    if len(selected) < 2:
        raise SystemExit("Combine at least two custom candidates")

    def merged_values(key: str) -> list[Any]:
        return list(
            dict.fromkeys(
                value
                for candidate in selected
                for value in candidate.get(key, [])
            )
        )

    required_fields = merged_values_from_nested(selected, "required_fields")
    supporting_fields = merged_values_from_nested(selected, "supporting_fields")
    combined_id = args.combined_id or f"{intent_id}-combined-{len(intent.get('custom_candidates', [])) + 1}"
    combined = {
        "id": combined_id,
        "intent_id": intent_id,
        "category": "组合目标",
        "goal_type": "business_analysis",
        "title": args.title or " + ".join(candidate["title"] for candidate in selected),
        "business_question": "；".join(candidate["business_question"] for candidate in selected),
        "questions": merged_values("questions"),
        "decision_value": "；".join(candidate["decision_value"] for candidate in selected),
        "analysis_depth": "combined",
        "supported_conclusions": merged_values("supported_conclusions"),
        "unsupported_conclusions": merged_values("unsupported_conclusions"),
        "required_scope": selected[0].get("required_scope", []),
        "required_data": {
            "scope": selected[0].get("required_data", {}).get("scope", []),
            "required_fields": required_fields,
            "supporting_fields": supporting_fields,
        },
        "recommended_methods": merged_values("recommended_methods"),
        "expected_outputs": merged_values("expected_outputs"),
        "data_quality_risks": merged_values("data_quality_risks"),
        "missing_data": merged_values("missing_data"),
        "assumptions": merged_values("assumptions"),
        "feasibility": "limited" if any(item.get("feasibility") != "ready" for item in selected) else "ready",
        "confidence": "medium",
        "estimated_cleaning": "heavy" if len(required_fields) + len(supporting_fields) > 6 else "medium",
        "combined_from": args.candidate_id,
    }
    intent.setdefault("custom_candidates", []).append(combined)
    intent["updated_at"] = now_iso()
    write_json(path, intent)
    print(json.dumps(combined, ensure_ascii=False, indent=2))


def merged_values_from_nested(candidates: list[dict[str, Any]], key: str) -> list[Any]:
    return list(
        dict.fromkeys(
            value
            for candidate in candidates
            for value in candidate.get("required_data", {}).get(key, [])
        )
    )


def cmd_create_custom_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    path = intent_path(session_dir, args.intent_id)
    intent = read_json(path, {})
    candidate = next(
        (item for item in intent.get("custom_candidates", []) if item.get("id") == args.candidate_id),
        None,
    )
    if not candidate:
        raise SystemExit(f"Custom candidate not found: {args.candidate_id}")
    if candidate.get("feasibility") == "blocked":
        raise SystemExit("Blocked candidates require additional data")
    goal_id = args.goal_id or f"goal-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    contract = candidate_contract(
        candidate,
        state.get("discovery_id", ""),
        goal_id,
        args.decision_object,
        intent.get("parent_goal_id"),
    )
    contract["intent_id"] = args.intent_id
    contract["intent_summary"] = intent.get("intent_summary")
    contract["contract_fingerprint"] = payload_fingerprint(contract)
    activate_goal(
        session_dir,
        state,
        contract,
        source="custom_intent",
        source_id=args.intent_id,
        parent_goal_id=intent.get("parent_goal_id"),
    )
    intent["readiness"] = "confirmed"
    intent["selected_candidate_id"] = args.candidate_id
    intent["goal_id"] = goal_id
    intent["updated_at"] = now_iso()
    write_json(path, intent)
    save_state(session_dir, state)
    print(json.dumps(contract, ensure_ascii=False, indent=2))


def cmd_return_home(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = state.get("active_goal_id")
    if goal_id and goal_id in state["goals"]:
        record = state["goals"][goal_id]
        if record.get("status") not in {"completed", "blocked", "superseded"}:
            record["status"] = "paused"
        record["updated_at"] = now_iso()
    state["active_goal_id"] = None
    state["active_intent_id"] = None
    state["home_status"] = "ready"
    clear_goal_artifact_mirrors(session_dir)
    state["last_home_return"] = {"reason": args.reason, "at": now_iso()}
    state.setdefault("history", []).append({"event": "return_home", "reason": args.reason, "at": now_iso()})
    save_state(session_dir, state)
    print(json.dumps({"ok": True, "view": "goal_home", "paused_goal_id": goal_id}, ensure_ascii=False, indent=2))


def cmd_resume_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state, args.goal_id)
    record = state["goals"][goal_id]
    if record.get("status") == "superseded":
        raise SystemExit("Superseded goals cannot be resumed")
    record["status"] = "selected" if record.get("status") == "paused" else record.get("status")
    record["updated_at"] = now_iso()
    state["active_goal_id"] = goal_id
    state["active_intent_id"] = None
    state["home_status"] = "goal_active"
    mirror_goal_artifacts(session_dir, goal_dir(session_dir, goal_id))
    state.setdefault("history", []).append({"event": "resume_goal", "goal_id": goal_id, "at": now_iso()})
    save_state(session_dir, state)
    print(json.dumps(record, ensure_ascii=False, indent=2))


def cmd_complete_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = active_goal_id(state, args.goal_id)
    analysis_dir = goal_dir(session_dir, goal_id) / "analysis-session"
    if analysis_dir.exists():
        chart_decision = read_json(analysis_dir / "chart-decision.json", {})
        if chart_decision.get("status") != "confirmed":
            raise SystemExit("Chart decision must be confirmed before completing the goal")
    record = state["goals"][goal_id]
    record.update(
        {
            "status": "completed",
            "summary": args.summary.strip(),
            "targeted_files": load_list(args.targeted_files),
            "report_files": load_list(args.report_files),
            "completed_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    state["active_goal_id"] = None
    state["home_status"] = "ready"
    clear_goal_artifact_mirrors(session_dir)
    state.setdefault("history", []).append({"event": "complete_goal", "goal_id": goal_id, "at": now_iso()})
    save_state(session_dir, state)
    print(json.dumps({"completed_goal": record, "next_view": "goal_home"}, ensure_ascii=False, indent=2))


def cmd_derive_goal(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    parent = state.get("goals", {}).get(args.parent_goal_id)
    if not parent:
        raise SystemExit(f"Parent goal not found: {args.parent_goal_id}")
    raw_input = args.raw_input or f"基于已完成目标「{parent['title']}」继续分析：{parent.get('summary', '')}"
    namespace = argparse.Namespace(
        session_dir=args.session_dir,
        intent_id=args.intent_id,
        raw_input=raw_input,
        parent_goal_id=args.parent_goal_id,
    )
    cmd_start_intent(namespace)


def cmd_show(args: argparse.Namespace) -> None:
    session_dir = Path(args.session_dir)
    state = load_state(session_dir)
    goal_id = state.get("active_goal_id")
    active_dir = goal_dir(session_dir, goal_id) if goal_id else None
    payload = {
        "session": state,
        "discovery": read_json(session_dir / "discovery.json", {}),
        "capability_summary": read_json(session_dir / "capability-summary.json", {}),
        "goal_catalog": read_json(session_dir / "goal-catalog.json", {}),
        "goal_contract": read_json(active_dir / "goal-contract.json", {}) if active_dir else {},
        "field_mapping": read_json(active_dir / "field-mapping.json", {}) if active_dir else {},
        "quality_impact": read_json(active_dir / "quality-impact.json", {}) if active_dir else {},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--session-dir", required=True)
    init.add_argument("--discovery", required=True)
    init.set_defaults(func=cmd_init)

    show_home = subparsers.add_parser("show-home")
    show_home.add_argument("--session-dir", required=True)
    show_home.set_defaults(func=cmd_show_home)

    show_goal = subparsers.add_parser("show-goal")
    show_goal.add_argument("--session-dir", required=True)
    show_goal.add_argument("--goal-id", required=True)
    show_goal.set_defaults(func=cmd_show_goal)

    set_status = subparsers.add_parser("set-goal-status")
    set_status.add_argument("--session-dir", required=True)
    set_status.add_argument("--goal-id")
    set_status.add_argument(
        "--status",
        required=True,
        choices=["selected", "preparing", "cleaning", "analyzing", "paused", "blocked", "superseded"],
    )
    set_status.add_argument("--note", default="")
    set_status.set_defaults(func=cmd_set_goal_status)

    select_goal = subparsers.add_parser("select-goal")
    select_goal.add_argument("--session-dir", required=True)
    select_goal.add_argument("--candidate-id", required=True)
    select_goal.add_argument("--goal-id")
    select_goal.add_argument("--decision-object", default="")
    select_goal.set_defaults(func=cmd_select_goal)

    confirm_goal = subparsers.add_parser("confirm-goal")
    confirm_goal.add_argument("--session-dir", required=True)
    confirm_goal.add_argument("--goal", required=True)
    confirm_goal.add_argument("--goal-id")
    confirm_goal.add_argument("--goal-type", choices=["business_analysis", "operational_cleaning"], required=True)
    confirm_goal.add_argument("--decision-object", default="")
    confirm_goal.add_argument("--questions")
    confirm_goal.add_argument("--scope")
    confirm_goal.add_argument("--required-fields", nargs="*", default=[])
    confirm_goal.add_argument("--supporting-fields", nargs="*", default=[])
    confirm_goal.add_argument("--join-keys", nargs="*", default=[])
    confirm_goal.add_argument("--time-fields", nargs="*", default=[])
    confirm_goal.add_argument("--metric-definitions")
    confirm_goal.add_argument("--excluded-scope")
    confirm_goal.add_argument("--assumptions")
    confirm_goal.set_defaults(func=cmd_confirm_goal)

    confirm_mapping = subparsers.add_parser("confirm-mapping")
    confirm_mapping.add_argument("--session-dir", required=True)
    confirm_mapping.add_argument("--mappings", required=True)
    confirm_mapping.set_defaults(func=cmd_confirm_mapping)

    save_quality = subparsers.add_parser("save-quality")
    save_quality.add_argument("--session-dir", required=True)
    save_quality.add_argument("--input", required=True)
    save_quality.set_defaults(func=cmd_save_quality)

    decide_quality = subparsers.add_parser("decide-quality")
    decide_quality.add_argument("--session-dir", required=True)
    decide_quality.add_argument("--target-id", nargs="*")
    decide_quality.add_argument("--all-irrelevant", action="store_true")
    decide_quality.add_argument("--choice", choices=["accept", "ignore", "custom_rule"], required=True)
    decide_quality.add_argument("--rule-text", default="")
    decide_quality.add_argument("--rationale", default="")
    decide_quality.set_defaults(func=cmd_decide_quality)

    start_intent = subparsers.add_parser("start-intent")
    start_intent.add_argument("--session-dir", required=True)
    start_intent.add_argument("--raw-input", required=True)
    start_intent.add_argument("--intent-id")
    start_intent.add_argument("--parent-goal-id")
    start_intent.set_defaults(func=cmd_start_intent)

    update_intent = subparsers.add_parser("update-intent")
    update_intent.add_argument("--session-dir", required=True)
    update_intent.add_argument("--intent-id")
    update_intent.add_argument("--raw-input", default="")
    update_intent.add_argument("--known")
    update_intent.add_argument("--assumptions")
    update_intent.add_argument("--data-matches")
    update_intent.add_argument("--data-gaps")
    update_intent.set_defaults(func=cmd_update_intent)

    summarize_intent = subparsers.add_parser("summarize-intent")
    summarize_intent.add_argument("--session-dir", required=True)
    summarize_intent.add_argument("--intent-id")
    summarize_intent.add_argument("--summary", default="")
    summarize_intent.add_argument("--confirmed", action="store_true")
    summarize_intent.add_argument("--force", action="store_true")
    summarize_intent.set_defaults(func=cmd_summarize_intent)

    generate = subparsers.add_parser("generate-custom-candidates")
    generate.add_argument("--session-dir", required=True)
    generate.add_argument("--intent-id")
    generate.set_defaults(func=cmd_generate_custom_candidates)

    combine = subparsers.add_parser("combine-custom-candidates")
    combine.add_argument("--session-dir", required=True)
    combine.add_argument("--intent-id")
    combine.add_argument("--candidate-id", nargs="+", required=True)
    combine.add_argument("--combined-id")
    combine.add_argument("--title")
    combine.set_defaults(func=cmd_combine_custom_candidates)

    create_custom = subparsers.add_parser("create-custom-goal")
    create_custom.add_argument("--session-dir", required=True)
    create_custom.add_argument("--intent-id", required=True)
    create_custom.add_argument("--candidate-id", required=True)
    create_custom.add_argument("--goal-id")
    create_custom.add_argument("--decision-object", default="")
    create_custom.set_defaults(func=cmd_create_custom_goal)

    return_home = subparsers.add_parser("return-home")
    return_home.add_argument("--session-dir", required=True)
    return_home.add_argument("--reason", default="用户返回目标首页")
    return_home.set_defaults(func=cmd_return_home)

    resume_goal = subparsers.add_parser("resume-goal")
    resume_goal.add_argument("--session-dir", required=True)
    resume_goal.add_argument("--goal-id", required=True)
    resume_goal.set_defaults(func=cmd_resume_goal)

    complete_goal = subparsers.add_parser("complete-goal")
    complete_goal.add_argument("--session-dir", required=True)
    complete_goal.add_argument("--goal-id")
    complete_goal.add_argument("--summary", required=True)
    complete_goal.add_argument("--targeted-files")
    complete_goal.add_argument("--report-files")
    complete_goal.set_defaults(func=cmd_complete_goal)

    derive_goal = subparsers.add_parser("derive-goal")
    derive_goal.add_argument("--session-dir", required=True)
    derive_goal.add_argument("--parent-goal-id", required=True)
    derive_goal.add_argument("--raw-input")
    derive_goal.add_argument("--intent-id")
    derive_goal.set_defaults(func=cmd_derive_goal)

    refresh = subparsers.add_parser("refresh-discovery")
    refresh.add_argument("--session-dir", required=True)
    refresh.add_argument("--discovery", required=True)
    refresh.set_defaults(func=cmd_init)

    show = subparsers.add_parser("show")
    show.add_argument("--session-dir", required=True)
    show.set_defaults(func=cmd_show)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
