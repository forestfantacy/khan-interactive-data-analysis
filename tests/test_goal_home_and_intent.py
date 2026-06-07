from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name: str, *args: str) -> dict:
    completed = subprocess.run(
        ["python3", str(SCRIPTS / name), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"{name} failed with exit code {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


class GoalHomeAndIntentTest(unittest.TestCase):
    def test_catalog_uses_business_questions_and_preserves_scoring_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset = Path(temporary_directory) / "sales.csv"
            with dataset.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerows(
                    [
                        ["Date", "Revenue", "Customer", "Region"],
                        ["2026-01-01", 100, "A", "East"],
                        ["2026-02-01", 80, "B", "West"],
                    ]
                )

            discovery = run_script("profile_dataset.py", str(dataset), "--all-sheets")
            candidates = {
                candidate["id"]: candidate
                for category in discovery["goal_catalog"]["categories"]
                for candidate in category["candidates"]
            }
            trend = candidates["trend-overview"]
            ranking = candidates["structure-ranking"]

            self.assertEqual(trend["decision_value"], "判断整体表现和变化方向")
            self.assertEqual(trend["confidence"], "high")
            self.assertEqual(trend["estimated_cleaning"], "medium")
            self.assertIn("收入", trend["title"])
            self.assertTrue(trend["title"].endswith("？"))
            self.assertEqual(trend["business_metric"], "收入")
            self.assertEqual(trend["data_basis"][:2], ["Revenue", "Date"])

            self.assertIn("客户", ranking["title"])
            self.assertEqual(ranking["business_object"], "客户")
            self.assertIn("Customer", ranking["data_basis"])

            abstract_prefixes = ("分析", "识别", "评估", "建立", "形成", "设计", "定位", "比较")
            for candidate in candidates.values():
                self.assertFalse(candidate["title"].startswith(abstract_prefixes))
                self.assertIn("data_basis", candidate)
                self.assertIn("decision_value", candidate)
                self.assertIn("confidence", candidate)
                self.assertIn("estimated_cleaning", candidate)

    def test_unknown_headers_remain_traceable_without_invented_meaning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset = Path(temporary_directory) / "opaque.csv"
            with dataset.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerows(
                    [
                        ["biz_dt", "x9_value", "group_z"],
                        ["2026-01-01", 10, "A"],
                        ["2026-02-01", 12, "B"],
                    ]
                )

            discovery = run_script("profile_dataset.py", str(dataset), "--all-sheets")
            candidate = next(
                item
                for category in discovery["goal_catalog"]["categories"]
                for item in category["candidates"]
                if item["id"] == "trend-overview"
            )
            self.assertIn("「x9_value」指标", candidate["title"])
            self.assertIn("x9_value", candidate["data_basis"])

    def test_goal_home_custom_intent_and_multi_goal_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            dataset = workdir / "sales.csv"
            with dataset.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerows(
                    [
                        ["Date", "Revenue", "Customer", "Region"],
                        ["2026-01-01", 100, "A", "East"],
                        ["2026-02-01", 80, "A", "East"],
                        ["2026-03-01", 150, "B", "West"],
                    ]
                )

            session = workdir / ".data-session"
            discovery = session / "discovery.json"
            run_script(
                "profile_dataset.py",
                str(dataset),
                "--all-sheets",
                "--output",
                str(discovery),
            )
            discovery_payload = json.loads(discovery.read_text(encoding="utf-8"))
            catalog = discovery_payload["goal_catalog"]
            self.assertGreaterEqual(len(catalog["categories"]), 3)
            for category in catalog["categories"]:
                self.assertGreaterEqual(len(category["candidates"]), 3)
                self.assertLessEqual(len(category["candidates"]), 5)
                for candidate in category["candidates"]:
                    self.assertIn("decision_value", candidate)
                    self.assertIn("supported_conclusions", candidate)
                    self.assertIn("unsupported_conclusions", candidate)
                    self.assertIn("estimated_cleaning", candidate)
                    self.assertIn("time_coverage", candidate)
                    self.assertIn("data_scope_summary", candidate)
                    self.assertIn("data_basis", candidate)

            run_script(
                "data_session_store.py",
                "init",
                "--session-dir",
                str(session),
                "--discovery",
                str(discovery),
            )
            home = run_script(
                "data_session_store.py",
                "show-home",
                "--session-dir",
                str(session),
            )
            self.assertEqual(home["view"], "goal_home")
            self.assertTrue(home["custom_goal_available"])
            self.assertIn("reliable_capabilities", home["capability_summary"])

            intent = run_script(
                "data_session_store.py",
                "start-intent",
                "--session-dir",
                str(session),
                "--intent-id",
                "intent-revenue",
                "--raw-input",
                "我想知道收入为什么变差，以及应该先处理哪些客户",
            )
            self.assertEqual(intent["readiness"], "collecting")
            self.assertEqual(len(intent["suggested_questions"]), 3)

            intent = run_script(
                "data_session_store.py",
                "update-intent",
                "--session-dir",
                str(session),
                "--intent-id",
                "intent-revenue",
                "--raw-input",
                "重点看客户和区域，结果给销售负责人制定跟进顺序",
                "--known",
                json.dumps(
                    {
                        "core_question": "解释收入下降并确定客户跟进优先级",
                        "focus_objects": ["Customer", "Region", "Revenue"],
                        "decision_use": "供销售负责人制定客户跟进顺序",
                        "metrics": ["Revenue"],
                    },
                    ensure_ascii=False,
                ),
            )
            self.assertEqual(intent["readiness"], "ready_for_candidates")
            self.assertFalse(intent["unknowns"])

            summary = run_script(
                "data_session_store.py",
                "summarize-intent",
                "--session-dir",
                str(session),
                "--intent-id",
                "intent-revenue",
                "--confirmed",
            )
            self.assertTrue(summary["intent_summary"])
            candidates = run_script(
                "data_session_store.py",
                "generate-custom-candidates",
                "--session-dir",
                str(session),
                "--intent-id",
                "intent-revenue",
            )
            self.assertEqual(len(candidates["candidates"]), 5)
            self.assertTrue(all(item["title"].endswith("？") for item in candidates["candidates"]))
            self.assertTrue(all("data_basis" in item for item in candidates["candidates"]))
            self.assertIn("下一步应该先处理什么", candidates["candidates"][-1]["title"])
            self.assertEqual(
                {item["analysis_depth"] for item in candidates["candidates"]},
                {"overview", "diagnostic", "attribution", "action"},
            )
            combined = run_script(
                "data_session_store.py",
                "combine-custom-candidates",
                "--session-dir",
                str(session),
                "--intent-id",
                "intent-revenue",
                "--candidate-id",
                "intent-revenue-attribution",
                "intent-revenue-action",
                "--combined-id",
                "intent-revenue-combined",
            )
            self.assertEqual(
                combined["combined_from"],
                ["intent-revenue-attribution", "intent-revenue-action"],
            )
            self.assertEqual(combined["analysis_depth"], "combined")

            first_goal = run_script(
                "data_session_store.py",
                "create-custom-goal",
                "--session-dir",
                str(session),
                "--intent-id",
                "intent-revenue",
                "--candidate-id",
                "intent-revenue-attribution",
                "--goal-id",
                "goal-custom-attribution",
            )
            self.assertEqual(first_goal["intent_id"], "intent-revenue")
            run_script(
                "data_session_store.py",
                "return-home",
                "--session-dir",
                str(session),
                "--reason",
                "切换到其他目标",
            )
            home = run_script(
                "data_session_store.py",
                "show-home",
                "--session-dir",
                str(session),
            )
            first_record = next(item for item in home["goals"] if item["goal_id"] == "goal-custom-attribution")
            self.assertEqual(first_record["status"], "paused")

            run_script(
                "data_session_store.py",
                "resume-goal",
                "--session-dir",
                str(session),
                "--goal-id",
                "goal-custom-attribution",
            )
            completed = run_script(
                "data_session_store.py",
                "complete-goal",
                "--session-dir",
                str(session),
                "--summary",
                "收入下降主要集中在重点客户，需要进一步核查。",
                "--targeted-files",
                '["/tmp/targeted.xlsx"]',
                "--report-files",
                '["/tmp/report.md"]',
            )
            self.assertEqual(completed["next_view"], "goal_home")
            self.assertEqual(completed["completed_goal"]["status"], "completed")

            second_goal = run_script(
                "data_session_store.py",
                "select-goal",
                "--session-dir",
                str(session),
                "--candidate-id",
                "anomaly-values",
                "--goal-id",
                "goal-anomaly",
            )
            self.assertEqual(second_goal["goal_id"], "goal-anomaly")
            home = run_script(
                "data_session_store.py",
                "show-home",
                "--session-dir",
                str(session),
            )
            self.assertEqual(len(home["goals"]), 2)
            completed_record = next(item for item in home["goals"] if item["goal_id"] == "goal-custom-attribution")
            self.assertEqual(completed_record["summary"], "收入下降主要集中在重点客户，需要进一步核查。")

            refreshed = dict(discovery_payload)
            refreshed["discovery_id"] = "new-discovery-id"
            refreshed_path = workdir / "refreshed-discovery.json"
            refreshed_path.write_text(json.dumps(refreshed, ensure_ascii=False), encoding="utf-8")
            run_script(
                "data_session_store.py",
                "refresh-discovery",
                "--session-dir",
                str(session),
                "--discovery",
                str(refreshed_path),
            )
            home = run_script(
                "data_session_store.py",
                "show-home",
                "--session-dir",
                str(session),
            )
            self.assertIsNone(home["active_goal_id"])
            self.assertTrue(all(item["data_refresh_status"] == "needs_review" for item in home["goals"]))


if __name__ == "__main__":
    unittest.main()
