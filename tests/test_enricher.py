"""Tests for ActivityEnricher — category, screenshot, OCR, phash, hostile apps."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from auto_daily_log_collector.enricher import ActivityEnricher


def _make_enricher(tmp_path, **overrides):
    defaults = dict(
        screenshot_dir=tmp_path / "ss",
        hostile_apps_applescript=["WeCom", "WeChat Work"],
        hostile_apps_screenshot=["WeCom"],
        phash_enabled=True,
        phash_threshold=20,
    )
    defaults.update(overrides)
    return ActivityEnricher(**defaults)


def test_enrich_classifies_coding_app(tmp_path):
    enricher = _make_enricher(tmp_path)
    result = enricher.enrich(
        app_name="Visual Studio Code",
        window_title="main.py — project",
        url=None,
        wecom_group=None,
        ocr_enabled=False,
        ocr_engine="tesseract",
    )
    assert result["category"] == "coding"
    assert result["confidence"] >= 0.85
    assert result["screenshot_local_path"] is None
    signals = json.loads(result["signals_json"])
    assert signals["browser_url"] is None
    assert signals["wecom_group_name"] is None
    assert signals["screenshot_path"] is None
    assert signals["ocr_text"] is None


def test_enrich_captures_screenshot_and_ocr_when_enabled(tmp_path):
    enricher = _make_enricher(tmp_path)
    ss_path = tmp_path / "ss" / "2026-04-15" / "shot.png"

    with patch(
        "auto_daily_log_collector.enricher.capture_screenshot",
        return_value=ss_path,
    ) as mock_cap, patch(
        "auto_daily_log_collector.enricher.compute_phash",
        return_value="hash_A",
    ), patch(
        "auto_daily_log_collector.enricher.is_similar",
        return_value=False,
    ), patch(
        "auto_daily_log_collector.enricher.ocr_image",
        return_value="some window text",
    ) as mock_ocr:
        result = enricher.enrich(
            app_name="Google Chrome",
            window_title="Jira - Chrome",
            url="https://jira.example.com/browse/ABC-1",
            wecom_group=None,
            ocr_enabled=True,
            ocr_engine="tesseract",
        )

    mock_cap.assert_called_once()
    mock_ocr.assert_called_once()
    assert result["screenshot_local_path"] == ss_path
    signals = json.loads(result["signals_json"])
    assert signals["screenshot_path"] == str(ss_path)
    assert signals["ocr_text"] == "some window text"
    assert signals["browser_url"] == "https://jira.example.com/browse/ABC-1"


def test_enrich_skips_screenshot_for_hostile_app(tmp_path):
    enricher = _make_enricher(tmp_path)

    with patch(
        "auto_daily_log_collector.enricher.capture_screenshot"
    ) as mock_cap, patch(
        "auto_daily_log_collector.enricher.ocr_image"
    ) as mock_ocr:
        result = enricher.enrich(
            app_name="WeCom",
            window_title="Some Chat",
            url=None,
            wecom_group="Team Channel",
            ocr_enabled=True,
            ocr_engine="tesseract",
        )

    mock_cap.assert_not_called()
    mock_ocr.assert_not_called()
    assert result["screenshot_local_path"] is None
    signals = json.loads(result["signals_json"])
    assert signals["screenshot_path"] is None
    assert signals["ocr_text"] is None
    assert signals["wecom_group_name"] == "Team Channel"


def test_enrich_reuses_ocr_when_phash_similar(tmp_path):
    enricher = _make_enricher(tmp_path)
    ss_a = tmp_path / "ss_a.png"
    ss_b = tmp_path / "ss_b.png"
    ss_a.write_bytes(b"a")
    ss_b.write_bytes(b"b")

    # First call — capture + OCR
    with patch(
        "auto_daily_log_collector.enricher.capture_screenshot",
        return_value=ss_a,
    ), patch(
        "auto_daily_log_collector.enricher.compute_phash",
        return_value="h1",
    ), patch(
        "auto_daily_log_collector.enricher.is_similar",
        return_value=False,
    ), patch(
        "auto_daily_log_collector.enricher.ocr_image",
        return_value="text v1",
    ):
        enricher.enrich("Chrome", "Tab A", None, None, True, "tesseract")

    # Second call — different window so same_window=False, phash similar → reuse OCR
    with patch(
        "auto_daily_log_collector.enricher.capture_screenshot",
        return_value=ss_b,
    ), patch(
        "auto_daily_log_collector.enricher.compute_phash",
        return_value="h1_close",
    ), patch(
        "auto_daily_log_collector.enricher.is_similar",
        return_value=True,
    ), patch(
        "auto_daily_log_collector.enricher.ocr_image",
        return_value="text v2",
    ) as mock_ocr_2:
        result = enricher.enrich("Chrome", "Tab B", None, None, True, "tesseract")

    mock_ocr_2.assert_not_called()
    signals = json.loads(result["signals_json"])
    assert signals["ocr_text"] == "text v1"
    assert signals["screenshot_path"] is None
    assert result["screenshot_local_path"] is None
    assert not ss_b.exists()  # similar shot deleted


def test_enrich_same_window_reuses_ocr_without_screenshot(tmp_path):
    enricher = _make_enricher(tmp_path)
    ss = tmp_path / "ss_first.png"
    ss.write_bytes(b"x")

    # First call fills cache
    with patch(
        "auto_daily_log_collector.enricher.capture_screenshot",
        return_value=ss,
    ), patch(
        "auto_daily_log_collector.enricher.compute_phash",
        return_value="h",
    ), patch(
        "auto_daily_log_collector.enricher.is_similar",
        return_value=False,
    ), patch(
        "auto_daily_log_collector.enricher.ocr_image",
        return_value="cached text",
    ):
        enricher.enrich("Chrome", "Tab X", None, None, True, "tesseract")

    # Second call same app+title — no screenshot at all, OCR reused
    with patch(
        "auto_daily_log_collector.enricher.capture_screenshot"
    ) as mock_cap, patch(
        "auto_daily_log_collector.enricher.ocr_image"
    ) as mock_ocr:
        result = enricher.enrich("Chrome", "Tab X", None, None, True, "tesseract")

    mock_cap.assert_not_called()
    mock_ocr.assert_not_called()
    signals = json.loads(result["signals_json"])
    assert signals["ocr_text"] == "cached text"


def test_is_hostile_applescript():
    enricher = ActivityEnricher(
        screenshot_dir=Path("/tmp"),
        hostile_apps_applescript=["WeCom", "WeChat Work"],
        hostile_apps_screenshot=[],
    )
    assert enricher.is_hostile_applescript("WeCom") is True
    assert enricher.is_hostile_applescript("wecom") is True
    assert enricher.is_hostile_applescript("WeChat Work") is True
    assert enricher.is_hostile_applescript("Google Chrome") is False
    assert enricher.is_hostile_applescript(None) is False
