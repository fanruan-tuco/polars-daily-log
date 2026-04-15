"""Activity enricher — adds category, screenshot, OCR, phash, hostile-app
handling, and wecom_group_name to raw activity samples.

Used by CollectorRuntime. Keeps enrichment logic separate from the
sampling loop and backend choice, so the same enricher runs identically
whether the collector writes to local SQLite or pushes over HTTP.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .monitor_internals.classifier import classify_activity
from .monitor_internals.ocr import ocr_image
from .monitor_internals.phash import compute_phash, is_similar
from .monitor_internals.screenshot import capture_screenshot


class ActivityEnricher:
    """Turn raw (app, title, url, wecom_group) tuples into enriched activity
    payloads with category/confidence/signals (including optional screenshot
    + OCR text).

    Keeps per-window state (last phash, last OCR text, last app/title) so
    consecutive sampling loops don't re-OCR an unchanged window.
    """

    def __init__(
        self,
        screenshot_dir: Path,
        hostile_apps_applescript: list[str],
        hostile_apps_screenshot: list[str],
        phash_enabled: bool = True,
        phash_threshold: int = 20,
    ):
        self._screenshot_dir = Path(screenshot_dir)
        self._hostile_as = {s.lower() for s in hostile_apps_applescript}
        self._hostile_ss = {s.lower() for s in hostile_apps_screenshot}
        self._phash_enabled = phash_enabled
        self._phash_threshold = phash_threshold

        # State for similarity-based OCR reuse
        self._last_phash = None
        self._last_ocr_text: Optional[str] = None
        self._last_app: Optional[str] = None
        self._last_title: Optional[str] = None

    def is_hostile_applescript(self, app_name: Optional[str]) -> bool:
        """Whether this app breaks when probed via AppleScript/UI APIs
        (e.g. WeChat Work self-exits). Caller should skip window title
        and browser tab probing for these apps."""
        return (app_name or "").lower() in self._hostile_as

    def enrich(
        self,
        app_name: str,
        window_title: Optional[str],
        url: Optional[str],
        wecom_group: Optional[str],
        ocr_enabled: bool,
        ocr_engine: str,
    ) -> dict:
        """Classify the activity and optionally take + OCR a screenshot.

        Returns a dict with keys:
            - category: str
            - confidence: float
            - signals_json: str (JSON-encoded signals dict)
            - screenshot_local_path: Optional[Path] (for backend.save_screenshot)
        """
        screenshot_path: Optional[Path] = None
        ocr_text: Optional[str] = None

        same_window = (
            app_name == self._last_app
            and window_title == self._last_title
            and self._last_app is not None
        )

        app_lower = (app_name or "").lower()
        _debug_no_skip = os.environ.get("PDL_DEBUG_NO_SKIP") == "1"
        skip_screenshot = (not _debug_no_skip) and (app_lower in self._hostile_ss)

        if ocr_enabled and not same_window and not skip_screenshot:
            today_dir = self._screenshot_dir / datetime.now().strftime("%Y-%m-%d")
            screenshot_path = capture_screenshot(today_dir)
            if screenshot_path:
                if self._phash_enabled:
                    current_hash = compute_phash(screenshot_path)
                    if is_similar(current_hash, self._last_phash, self._phash_threshold):
                        # Screenshot visually similar — reuse last OCR, delete file
                        ocr_text = self._last_ocr_text
                        try:
                            screenshot_path.unlink()
                        except OSError:
                            pass
                        screenshot_path = None
                    else:
                        ocr_text = ocr_image(screenshot_path, ocr_engine)
                        self._last_phash = current_hash
                        self._last_ocr_text = ocr_text
                else:
                    ocr_text = ocr_image(screenshot_path, ocr_engine)
        elif same_window:
            # Same window — reuse last OCR text, no screenshot
            ocr_text = self._last_ocr_text

        self._last_app = app_name
        self._last_title = window_title

        category, confidence, hints = classify_activity(app_name, window_title, url)

        signals = {
            "browser_url": url,
            "wecom_group_name": wecom_group,
            "screenshot_path": str(screenshot_path) if screenshot_path else None,
            "ocr_text": ocr_text,
            "hints": hints,
        }

        return {
            "category": category,
            "confidence": confidence,
            "signals_json": json.dumps(signals, ensure_ascii=False),
            "screenshot_local_path": screenshot_path,
        }
