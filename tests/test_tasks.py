# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.tasks"""

import subprocess
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from daily_reporter.config import AppConfig
from daily_reporter.tasks import (
    _hm_to_task_name,
    _hm_to_label,
    _find_main_py,
    list_tasks,
    delete_task,
    delete_all_tasks,
    registered_task_names,
    register_tasks,
    run_task_now,
    _TASK_PREFIX,
)


# ---------------------------------------------------------------------------
# _hm_to_task_name
# ---------------------------------------------------------------------------

class TestHmToTaskName:
    def test_morning(self):
        assert _hm_to_task_name("06:00") == "DailyReporter-0600"

    def test_evening(self):
        assert _hm_to_task_name("18:00") == "DailyReporter-1800"

    def test_midnight(self):
        assert _hm_to_task_name("00:00") == "DailyReporter-0000"

    def test_noon(self):
        assert _hm_to_task_name("12:30") == "DailyReporter-1230"

    def test_prefix_present(self):
        name = _hm_to_task_name("09:15")
        assert name.startswith(_TASK_PREFIX)

    def test_colon_removed(self):
        name = _hm_to_task_name("08:45")
        assert ":" not in name


# ---------------------------------------------------------------------------
# _hm_to_label
# ---------------------------------------------------------------------------

class TestHmToLabel:
    def test_05_is_morning(self):
        assert _hm_to_label("05:00") == "morning"

    def test_06_is_morning(self):
        assert _hm_to_label("06:00") == "morning"

    def test_09_is_morning(self):
        assert _hm_to_label("09:59") == "morning"

    def test_10_is_noon(self):
        assert _hm_to_label("10:00") == "noon"

    def test_13_is_noon(self):
        assert _hm_to_label("13:59") == "noon"

    def test_14_is_afternoon(self):
        assert _hm_to_label("14:00") == "afternoon"

    def test_18_is_afternoon(self):
        assert _hm_to_label("18:59") == "afternoon"  # 18 < 19

    def test_19_is_evening(self):
        assert _hm_to_label("19:00") == "evening"

    def test_00_is_evening(self):
        assert _hm_to_label("00:00") == "evening"

    def test_23_is_evening(self):
        assert _hm_to_label("23:59") == "evening"


# ---------------------------------------------------------------------------
# _find_main_py
# ---------------------------------------------------------------------------

class TestFindMainPy:
    def test_returns_string(self):
        result = _find_main_py()
        assert isinstance(result, str)

    def test_ends_with_main_py(self):
        result = _find_main_py()
        assert result.endswith("main.py")

    def test_is_absolute(self):
        result = _find_main_py()
        assert Path(result).is_absolute()


# ---------------------------------------------------------------------------
# list_tasks — with mocked schtasks
# ---------------------------------------------------------------------------

def _make_schtasks_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.stdout = stdout
    result.returncode = returncode
    return result


class TestListTasks:
    def test_empty_when_no_tasks(self):
        empty_output = ""
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(empty_output)):
            tasks = list_tasks()
        assert tasks == []

    def test_finds_matching_task(self):
        output = (
            "任务名:           \\DailyReporter-0600\n"
            "下次运行时间:     2026/03/06 06:00:00\n"
            "状态:             就绪\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "DailyReporter-0600"

    def test_time_parsed_from_task_name(self):
        output = (
            "任务名:           \\DailyReporter-1800\n"
            "状态:             就绪\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert tasks[0]["time"] == "18:00"

    def test_ignores_non_daily_reporter_tasks(self):
        output = (
            "任务名:           \\SomeOtherTask\n"
            "状态:             就绪\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert tasks == []

    def test_next_run_defaults_to_na(self):
        output = (
            "任务名:           \\DailyReporter-0600\n"
            "状态:             就绪\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert tasks[0]["next_run"] == "N/A"

    def test_status_defaults_to_unknown(self):
        output = (
            "任务名:           \\DailyReporter-0600\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert tasks[0]["status"] == "未知"

    def test_multiple_tasks(self):
        output = (
            "任务名:           \\DailyReporter-0600\n"
            "状态:             就绪\n"
            "\n"
            "任务名:           \\DailyReporter-1800\n"
            "状态:             就绪\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert len(tasks) == 2

    def test_registered_flag_true(self):
        output = (
            "任务名:           \\DailyReporter-0600\n"
            "状态:             就绪\n"
        )
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            tasks = list_tasks()
        assert tasks[0]["registered"] is True


# ---------------------------------------------------------------------------
# registered_task_names
# ---------------------------------------------------------------------------

class TestRegisteredTaskNames:
    def test_empty_output(self):
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result("")):
            names = registered_task_names()
        assert names == []

    def test_finds_prefixed_tasks(self):
        # CSV /FO format: "TaskName","...",...
        output = '"\\DailyReporter-0600","SYSTEM","Ready"\n'
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            names = registered_task_names()
        assert "DailyReporter-0600" in names

    def test_ignores_other_tasks(self):
        output = '"\\OtherTask","SYSTEM","Ready"\n'
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result(output)):
            names = registered_task_names()
        assert names == []


# ---------------------------------------------------------------------------
# delete_task
# ---------------------------------------------------------------------------

class TestDeleteTask:
    def test_returns_true_on_success(self):
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result("", 0)):
            result = delete_task("DailyReporter-0600")
        assert result is True

    def test_returns_false_on_failure(self):
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result("ERROR", 1)):
            result = delete_task("DailyReporter-0600")
        assert result is False

    def test_calls_schtasks_delete(self):
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result("", 0)) as mock_run:
            delete_task("DailyReporter-0600")
        args = mock_run.call_args[0]
        assert "/Delete" in args
        assert "DailyReporter-0600" in args


# ---------------------------------------------------------------------------
# delete_all_tasks
# ---------------------------------------------------------------------------

class TestDeleteAllTasks:
    def test_deletes_all_found_tasks(self):
        tasks_output = (
            '"\\DailyReporter-0600","SYSTEM","Ready"\n'
            '"\\DailyReporter-1800","SYSTEM","Ready"\n'
        )

        def side_effect(*args):
            if "/Query" in args:
                return _make_schtasks_result(tasks_output, 0)
            return _make_schtasks_result("", 0)

        with patch("daily_reporter.tasks._run_schtasks", side_effect=side_effect):
            count = delete_all_tasks()
        assert count == 2

    def test_returns_zero_when_no_tasks(self):
        with patch("daily_reporter.tasks._run_schtasks", return_value=_make_schtasks_result("", 0)):
            count = delete_all_tasks()
        assert count == 0


# ---------------------------------------------------------------------------
# register_tasks
# ---------------------------------------------------------------------------

class TestRegisterTasks:
    def test_creates_tasks_from_config(self, tmp_path):
        cfg = AppConfig(
            watch_paths=[tmp_path],
            auto_snapshot_times=["09:00", "18:00"],
        )
        config_path = tmp_path / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        def side_effect(*args):
            if "/Query" in args:
                return _make_schtasks_result("", 0)
            return _make_schtasks_result("", 0)

        with patch("daily_reporter.tasks._run_schtasks", side_effect=side_effect):
            registered = register_tasks(cfg, config_path)
        assert len(registered) == 2

    def test_deletes_old_tasks(self, tmp_path):
        cfg = AppConfig(
            watch_paths=[tmp_path],
            auto_snapshot_times=["09:00"],
        )
        config_path = tmp_path / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        calls_log = []

        def side_effect(*args):
            calls_log.append(args)
            if "/Query" in args:
                # Simulate existing task DailyReporter-1800 (not in new config)
                return _make_schtasks_result('"\\DailyReporter-1800","SYSTEM","Ready"\n', 0)
            return _make_schtasks_result("", 0)

        with patch("daily_reporter.tasks._run_schtasks", side_effect=side_effect):
            register_tasks(cfg, config_path)

        # Check that /Delete was called for the old task
        delete_calls = [c for c in calls_log if "/Delete" in c]
        assert len(delete_calls) >= 1


# ---------------------------------------------------------------------------
# run_task_now
# ---------------------------------------------------------------------------

class TestRunTaskNow:
    def test_returns_snapshot_dict(self, tmp_path):
        cfg = AppConfig(
            watch_paths=[tmp_path],
            snapshot_root=tmp_path / ".daily_reporter",
            output_root=tmp_path / "reports",
        )
        result = run_task_now(cfg, "09:00")
        assert result is not None
        assert "id" in result
        assert result["label"] == "morning"

    def test_returns_none_on_error(self, tmp_path):
        cfg = AppConfig(
            watch_paths=[tmp_path],
            snapshot_root=tmp_path / ".daily_reporter",
            output_root=tmp_path / "reports",
        )
        with patch("daily_reporter.tasks.take_snapshot", side_effect=RuntimeError("boom")):
            result = run_task_now(cfg, "12:00")
        assert result is None
