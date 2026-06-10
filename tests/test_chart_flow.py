from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from PIL import Image


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


class ChartFlowTest(unittest.TestCase):
    def create_dataset(self, path: Path) -> None:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "目标数据"
        worksheet.append(["Date", "Revenue", "Customer", "Cost"])
        rows = [
            ("2026-01-01", 100, "A", 60),
            ("2026-02-01", 80, "B", 55),
            ("2026-03-01", 150, "A", 90),
            ("2026-04-01", 120, "C", 75),
            ("2026-05-01", 180, "C", 100),
            ("2026-06-01", 160, "B", 95),
            ("2026-07-01", 200, "A", 110),
            ("2026-08-01", 140, "C", 85),
        ]
        for row in rows:
            worksheet.append(row)
        workbook.save(path)

    def chart_decision(
        self,
        profile: Path,
        output: Path,
        *extra: str,
    ) -> dict:
        return run_script(
            "decide_charts.py",
            "--profile",
            str(profile),
            "--goal",
            "分析收入趋势和客户贡献",
            "--sheet",
            "目标数据",
            "--output",
            str(output),
            *extra,
        )

    def test_confirmation_render_run_update_and_html_embedding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            dataset = workdir / "targeted.xlsx"
            profile = workdir / "profile.json"
            decision_path = workdir / "chart-decision.json"
            charts = workdir / "charts"
            run_file = workdir / "run-001.json"
            self.create_dataset(dataset)
            run_script(
                "profile_dataset.py",
                str(dataset),
                "--sheet",
                "目标数据",
                "--output",
                str(profile),
            )

            pending = self.chart_decision(profile, decision_path)
            self.assertEqual(pending["status"], "pending_confirmation")
            self.assertTrue(pending["recommended_chart_ids"])
            self.assertIn("等待用户确认", pending["decision_summary"])

            confirmed = self.chart_decision(
                profile,
                decision_path,
                "--confirm",
                "--selected-chart",
                "trend",
                "--selected-chart",
                "comparison",
            )
            self.assertEqual(confirmed["status"], "confirmed")
            self.assertEqual(
                [item["id"] for item in confirmed["selected_charts"]],
                ["trend", "comparison"],
            )

            run_file.write_text(
                json.dumps({"run_id": "run-001", "status": "in_progress"}),
                encoding="utf-8",
            )
            result = run_script(
                "render_charts.py",
                "--dataset",
                str(dataset),
                "--decision",
                str(decision_path),
                "--output-dir",
                str(charts),
                "--run-file",
                str(run_file),
            )
            self.assertFalse(result["failed"])
            self.assertEqual(len(result["generated"]), 2)
            for item in result["generated"]:
                image_path = Path(item["path"])
                self.assertTrue(image_path.is_absolute())
                self.assertTrue(image_path.exists())
                with Image.open(image_path) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertGreaterEqual(image.width, 1000)

            saved_run = json.loads(run_file.read_text(encoding="utf-8"))
            self.assertEqual(saved_run["chart_decision"]["status"], "confirmed")
            self.assertEqual(saved_run["chart_files"], result["chart_files"])
            self.assertEqual(saved_run["chart_failures"], [])

            report = workdir / "final-report.md"
            report.write_text(
                "# 分析报告\n\n" + "\n\n".join(item["markdown"] for item in result["generated"]),
                encoding="utf-8",
            )
            exported = run_script(
                "export_report.py",
                str(report),
                "--output-dir",
                str(workdir / "exports"),
                "--format",
                "HTML",
                "--chart-decision",
                str(decision_path),
            )
            html = Path(exported["outputs"][0]).read_text(encoding="utf-8")
            self.assertIn("data:image/png;base64,", html)

    def test_confirmed_no_charts_and_individual_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            dataset = workdir / "targeted.xlsx"
            profile = workdir / "profile.json"
            decision_path = workdir / "chart-decision.json"
            self.create_dataset(dataset)
            run_script(
                "profile_dataset.py",
                str(dataset),
                "--sheet",
                "目标数据",
                "--output",
                str(profile),
            )

            cancelled = self.chart_decision(profile, decision_path, "--confirm")
            self.assertEqual(cancelled["status"], "confirmed")
            self.assertFalse(cancelled["should_create_charts"])
            empty_result = run_script(
                "render_charts.py",
                "--dataset",
                str(dataset),
                "--decision",
                str(decision_path),
                "--output-dir",
                str(workdir / "empty-charts"),
            )
            self.assertEqual(empty_result["generated"], [])
            self.assertEqual(empty_result["failed"], [])

            confirmed = self.chart_decision(
                profile,
                decision_path,
                "--confirm",
                "--selected-chart",
                "trend",
            )
            confirmed["selected_charts"][0]["fields"][1] = "MissingMetric"
            decision_path.write_text(json.dumps(confirmed, ensure_ascii=False), encoding="utf-8")
            failed_result = run_script(
                "render_charts.py",
                "--dataset",
                str(dataset),
                "--decision",
                str(decision_path),
                "--output-dir",
                str(workdir / "failed-charts"),
            )
            self.assertEqual(failed_result["generated"], [])
            self.assertEqual(failed_result["failed"][0]["id"], "trend")
            self.assertIn("Missing fields", failed_result["failed"][0]["error"])

    def test_unconfirmed_decision_cannot_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            dataset = workdir / "targeted.xlsx"
            profile = workdir / "profile.json"
            decision_path = workdir / "chart-decision.json"
            self.create_dataset(dataset)
            run_script(
                "profile_dataset.py",
                str(dataset),
                "--sheet",
                "目标数据",
                "--output",
                str(profile),
            )
            self.chart_decision(profile, decision_path)
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPTS / "render_charts.py"),
                    "--dataset",
                    str(dataset),
                    "--decision",
                    str(decision_path),
                    "--output-dir",
                    str(workdir / "charts"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("must be confirmed", completed.stderr)

            report = workdir / "final-report.md"
            report.write_text("# 分析报告\n", encoding="utf-8")
            export_attempt = subprocess.run(
                [
                    "python3",
                    str(SCRIPTS / "export_report.py"),
                    str(report),
                    "--output-dir",
                    str(workdir / "exports"),
                    "--chart-decision",
                    str(decision_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(export_attempt.returncode, 0)
            self.assertIn("must be confirmed", export_attempt.stderr)

    def test_no_chart_mode_is_confirmed_without_extra_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            dataset = workdir / "targeted.xlsx"
            profile = workdir / "profile.json"
            decision_path = workdir / "chart-decision.json"
            self.create_dataset(dataset)
            run_script(
                "profile_dataset.py",
                str(dataset),
                "--sheet",
                "目标数据",
                "--output",
                str(profile),
            )
            decision = self.chart_decision(
                profile,
                decision_path,
                "--visualization-mode",
                "不出图",
            )
            self.assertEqual(decision["status"], "confirmed")
            self.assertFalse(decision["should_create_charts"])

    def test_all_supported_chart_types_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            dataset = workdir / "targeted.xlsx"
            profile = workdir / "profile.json"
            decision_path = workdir / "chart-decision.json"
            self.create_dataset(dataset)
            run_script(
                "profile_dataset.py",
                str(dataset),
                "--sheet",
                "目标数据",
                "--output",
                str(profile),
            )
            chart_ids = [
                "trend",
                "comparison",
                "composition",
                "pareto",
                "distribution",
                "relationship",
            ]
            selection_args = [
                argument
                for chart_id in chart_ids
                for argument in ("--selected-chart", chart_id)
            ]
            confirmed = self.chart_decision(
                profile,
                decision_path,
                "--output-depth",
                "深入",
                "--confirm",
                *selection_args,
            )
            self.assertEqual(
                [item["id"] for item in confirmed["selected_charts"]],
                chart_ids,
            )
            result = run_script(
                "render_charts.py",
                "--dataset",
                str(dataset),
                "--decision",
                str(decision_path),
                "--output-dir",
                str(workdir / "charts"),
            )
            self.assertEqual(result["failed"], [])
            self.assertEqual(
                [item["id"] for item in result["generated"]],
                chart_ids,
            )


if __name__ == "__main__":
    unittest.main()
