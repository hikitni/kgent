# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.utils"""

import logging
import re

import pytest

from daily_reporter.utils import (
    hm_to_label,
    SNAP_ID_RE,
    paginate,
    setup_logging,
)


# ---------------------------------------------------------------------------
# hm_to_label
# ---------------------------------------------------------------------------

class TestHmToLabel:
    def test_early_morning(self):
        assert hm_to_label("05:00") == "morning"

    def test_morning(self):
        assert hm_to_label("08:30") == "morning"

    def test_morning_boundary(self):
        assert hm_to_label("09:59") == "morning"

    def test_noon_start(self):
        assert hm_to_label("10:00") == "noon"

    def test_noon_mid(self):
        assert hm_to_label("12:00") == "noon"

    def test_noon_end(self):
        assert hm_to_label("13:59") == "noon"

    def test_afternoon_start(self):
        assert hm_to_label("14:00") == "afternoon"

    def test_afternoon_mid(self):
        assert hm_to_label("16:00") == "afternoon"

    def test_afternoon_end(self):
        assert hm_to_label("18:59") == "afternoon"

    def test_evening_start(self):
        assert hm_to_label("19:00") == "evening"

    def test_evening_late(self):
        assert hm_to_label("23:59") == "evening"

    def test_midnight(self):
        assert hm_to_label("00:00") == "evening"

    def test_before_dawn(self):
        assert hm_to_label("04:00") == "evening"


# ---------------------------------------------------------------------------
# SNAP_ID_RE
# ---------------------------------------------------------------------------

class TestSnapIdRe:
    def test_valid_id(self):
        assert SNAP_ID_RE.match("20260305-093000") is not None

    def test_valid_id_midnight(self):
        assert SNAP_ID_RE.match("20260101-000000") is not None

    def test_invalid_no_dash(self):
        assert SNAP_ID_RE.match("20260305093000") is None

    def test_invalid_too_short(self):
        assert SNAP_ID_RE.match("2026030-093000") is None

    def test_invalid_letters(self):
        assert SNAP_ID_RE.match("abcdefgh-ijklmn") is None

    def test_invalid_extra_chars(self):
        assert SNAP_ID_RE.match("20260305-093000-extra") is None

    def test_empty_string(self):
        assert SNAP_ID_RE.match("") is None


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------

class TestPaginate:
    def test_single_page(self):
        items = [1, 2, 3]
        page_items, total_pages, actual_page = paginate(items, 1, page_size=10)
        assert page_items == [1, 2, 3]
        assert total_pages == 1
        assert actual_page == 1

    def test_multi_page_first(self):
        items = list(range(25))
        page_items, total_pages, actual_page = paginate(items, 1, page_size=10)
        assert len(page_items) == 10
        assert page_items == list(range(10))
        assert total_pages == 3
        assert actual_page == 1

    def test_multi_page_middle(self):
        items = list(range(25))
        page_items, total_pages, actual_page = paginate(items, 2, page_size=10)
        assert page_items == list(range(10, 20))
        assert actual_page == 2

    def test_multi_page_last(self):
        items = list(range(25))
        page_items, total_pages, actual_page = paginate(items, 3, page_size=10)
        assert page_items == list(range(20, 25))
        assert actual_page == 3

    def test_page_beyond_max_clamps(self):
        items = [1, 2, 3]
        page_items, total_pages, actual_page = paginate(items, 999, page_size=10)
        assert actual_page == 1  # clamped to total_pages
        assert page_items == [1, 2, 3]

    def test_page_zero_clamps_to_one(self):
        items = [1, 2, 3]
        page_items, total_pages, actual_page = paginate(items, 0, page_size=10)
        assert actual_page == 1

    def test_negative_page_clamps(self):
        items = [1, 2, 3]
        page_items, total_pages, actual_page = paginate(items, -5, page_size=10)
        assert actual_page == 1

    def test_empty_list(self):
        page_items, total_pages, actual_page = paginate([], 1, page_size=10)
        assert page_items == []
        assert total_pages == 1
        assert actual_page == 1

    def test_exact_page_boundary(self):
        items = list(range(20))
        page_items, total_pages, actual_page = paginate(items, 2, page_size=10)
        assert page_items == list(range(10, 20))
        assert total_pages == 2

    def test_default_page_size(self):
        items = list(range(50))
        page_items, total_pages, actual_page = paginate(items, 1)
        assert len(page_items) == 20  # default page_size=20


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def test_sets_level(self):
        setup_logging(logging.DEBUG)
        root = logging.getLogger("daily_reporter")
        assert root.level == logging.DEBUG

    def test_adds_handler(self):
        setup_logging()
        root = logging.getLogger("daily_reporter")
        assert len(root.handlers) >= 1

    def test_idempotent(self):
        setup_logging()
        count_before = len(logging.getLogger("daily_reporter").handlers)
        setup_logging()
        count_after = len(logging.getLogger("daily_reporter").handlers)
        assert count_after == count_before  # no duplicate handlers
