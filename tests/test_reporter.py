# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.reporter"""

import pytest
from pathlib import Path

from daily_reporter.config import AppConfig
from daily_reporter.reporter import (
    generate_report,
    ai_report_path,
    list_reports,
    delete_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    watch = tmp_path / "watch"
    watch.mkdir()
    return AppConfig(
        watch_paths=[watch],
        snapshot_root=tmp_path / ".daily_reporter",
        output_root=tmp_path / "reports",
    )


def _snap(snap_id: str, label: str = "test", files: dict | None = None) -> dict:
    return {
        "id": snap_id,
        "timestamp": f"2026-03-05T09:00:00",
        "label": label,
        "files": files or {},
    }


def _snap_with_file(snap_id: str, path: str, lines: list) -> dict:
    import hashlib
    content = "\n".join(lines)
    h = hashlib.md5(content.encode()).hexdigest()
    return {
        "id": snap_id,
        "timestamp": "2026-03-05T09:00:00",
        "label": "test",
        "files": {path: {"hash": h, "lines": lines}},
    }


# ---------------------------------------------------------------------------
# ai_report_path
# ---------------------------------------------------------------------------

class TestAiReportPath:
    def test_adds_ai_suffix(self):
        p = Path("/reports/report-A-to-B.md")
        result = ai_report_path(p)
        assert result.name == "report-A-to-B-ai.md"

    def test_same_directory(self):
        p = Path("/reports/report-A-to-B.md")
        result = ai_report_path(p)
        assert result.parent == p.parent

    def test_suffix_preserved(self):
        p = Path("/reports/report-X-to-Y.md")
        result = ai_report_path(p)
        assert result.suffix == ".md"

    def test_different_name(self):
        p = Path("/out/some-report.md")
        result = ai_report_path(p)
        assert result.name == "some-report-ai.md"


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_returns_path(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000", "morning")
        snap_b = _snap("20260305-180000", "evening")
        out = generate_report(cfg, snap_a, snap_b)
        assert isinstance(out, Path)

    def test_file_created(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        assert out.exists()

    def test_filename_includes_snapshot_ids(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        assert "20260305-090000" in out.name
        assert "20260305-180000" in out.name

    def test_report_contains_header(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        content = out.read_text(encoding="utf-8")
        assert "# 工作日报" in content

    def test_report_contains_overview_section(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        content = out.read_text(encoding="utf-8")
        assert "今日概览" in content

    def test_report_contains_snapshot_ids(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        content = out.read_text(encoding="utf-8")
        assert "20260305-090000" in content
        assert "20260305-180000" in content

    def test_report_created_files_section(self, cfg: AppConfig):
        snap_a = _snap("A")
        snap_b = _snap_with_file("B", "/project/new.py", ["x = 1"])
        out = generate_report(cfg, snap_a, snap_b)
        content = out.read_text(encoding="utf-8")
        assert "新增文件" in content

    def test_report_modified_files_section(self, cfg: AppConfig):
        import hashlib
        snap_a = _snap_with_file("A", "/project/app.py", ["v1"])
        snap_b = _snap_with_file("B", "/project/app.py", ["v2"])
        out = generate_report(cfg, snap_a, snap_b)
        content = out.read_text(encoding="utf-8")
        assert "修改文件" in content

    def test_zero_changes_report(self, cfg: AppConfig):
        """Identical snapshots should still produce a valid report."""
        snap = _snap("20260305-090000")
        out = generate_report(cfg, snap, snap)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "# 工作日报" in content

    def test_output_root_created(self, cfg: AppConfig):
        assert not cfg.output_root.exists()
        snap_a = _snap("X")
        snap_b = _snap("Y")
        generate_report(cfg, snap_a, snap_b)
        assert cfg.output_root.exists()

    def test_report_summary_section(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        content = out.read_text(encoding="utf-8")
        assert "工作总结" in content


# ---------------------------------------------------------------------------
# list_reports
# ---------------------------------------------------------------------------

class TestListReports:
    def test_empty_when_no_reports(self, cfg: AppConfig):
        result = list_reports(cfg)
        assert result == []

    def test_empty_when_output_root_missing(self, cfg: AppConfig):
        result = list_reports(cfg)
        assert result == []

    def test_finds_generated_report(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        generate_report(cfg, snap_a, snap_b)
        result = list_reports(cfg)
        assert len(result) == 1

    def test_is_ai_false_for_raw(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        generate_report(cfg, snap_a, snap_b)
        result = list_reports(cfg)
        assert result[0]["is_ai"] is False

    def test_is_ai_true_for_ai_report(self, cfg: AppConfig):
        cfg.output_root.mkdir(parents=True)
        ai_file = cfg.output_root / "report-A-to-B-ai.md"
        ai_file.write_text("# AI Report", encoding="utf-8")
        result = list_reports(cfg)
        ai_entry = next(r for r in result if r["filename"].endswith("-ai.md"))
        assert ai_entry["is_ai"] is True

    def test_snap_a_b_parsed(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        generate_report(cfg, snap_a, snap_b)
        result = list_reports(cfg)
        assert result[0]["snap_a"] == "20260305-090000"
        assert result[0]["snap_b"] == "20260305-180000"

    def test_returns_size_kb(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        generate_report(cfg, snap_a, snap_b)
        result = list_reports(cfg)
        assert result[0]["size_kb"] >= 0

    def test_multiple_reports_sorted_by_mtime_desc(self, cfg: AppConfig):
        import time
        cfg.output_root.mkdir(parents=True)
        f1 = cfg.output_root / "report-A-to-B.md"
        f1.write_text("first", encoding="utf-8")
        time.sleep(0.02)  # ensure different mtime
        f2 = cfg.output_root / "report-C-to-D.md"
        f2.write_text("second", encoding="utf-8")
        result = list_reports(cfg)
        # Most recently modified should be first
        assert result[0]["filename"] == f2.name


# ---------------------------------------------------------------------------
# delete_report
# ---------------------------------------------------------------------------

class TestDeleteReport:
    def test_delete_existing_file(self, cfg: AppConfig):
        snap_a = _snap("20260305-090000")
        snap_b = _snap("20260305-180000")
        out = generate_report(cfg, snap_a, snap_b)
        result = delete_report(out)
        assert result is True
        assert not out.exists()

    def test_delete_nonexistent_returns_false(self, cfg: AppConfig):
        p = cfg.output_root / "nonexistent.md"
        result = delete_report(p)
        assert result is False

    def test_delete_only_removes_target(self, cfg: AppConfig):
        snap_a = _snap("A")
        snap_b = _snap("B")
        snap_c = _snap("C")
        out1 = generate_report(cfg, snap_a, snap_b)
        out2 = generate_report(cfg, snap_b, snap_c)
        delete_report(out1)
        assert not out1.exists()
        assert out2.exists()
