import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import MonitorConfig
from ..models.database import Database
from .classifier import classify_activity
from .platforms.detect import get_platform_module
from .screenshot import capture_screenshot
from .ocr import ocr_image
from .phash import compute_phash, is_similar
from .idle import get_idle_seconds


class MonitorService:
    def __init__(self, db: Database, config: MonitorConfig, screenshot_dir: Path):
        self._db = db
        self._config = config
        self._screenshot_dir = screenshot_dir
        self._platform = get_platform_module()
        self._last_app: Optional[str] = None
        self._last_title: Optional[str] = None
        self._last_id: Optional[int] = None
        self._last_phash = None
        self._last_ocr_text: Optional[str] = None
        self._last_was_idle: bool = False
        self._running = False

    def _capture_raw_inner(self) -> dict:
        app_name = self._platform.get_frontmost_app()
        window_title = self._platform.get_window_title(app_name) if app_name else None
        tab_title, url = (
            self._platform.get_browser_tab(app_name) if app_name else (None, None)
        )
        wecom_group = self._platform.get_wecom_chat_name(app_name) if app_name else None
        return {
            "app_name": app_name,
            "window_title": tab_title or window_title,
            "url": url,
            "wecom_group": wecom_group,
        }

    def _capture_raw(self) -> dict:
        raw = self._capture_raw_inner()

        screenshot_path = None
        ocr_text = None

        # Skip screenshot+OCR if app and title haven't changed (biggest resource saver)
        app = raw.get("app_name")
        title = raw.get("window_title")
        same_window = (app == self._last_app and title == self._last_title
                       and self._last_app is not None)

        if self._config.ocr_enabled and not same_window:
            today_dir = self._screenshot_dir / datetime.now().strftime("%Y-%m-%d")
            screenshot_path = capture_screenshot(today_dir)
            if screenshot_path:
                if self._config.phash_enabled:
                    current_hash = compute_phash(screenshot_path)
                    if is_similar(current_hash, self._last_phash, self._config.phash_threshold):
                        # Screenshot visually similar — reuse last OCR, delete file
                        ocr_text = self._last_ocr_text
                        try:
                            screenshot_path.unlink()
                        except OSError:
                            pass
                        screenshot_path = None
                    else:
                        ocr_text = ocr_image(screenshot_path, self._config.ocr_engine)
                        self._last_phash = current_hash
                        self._last_ocr_text = ocr_text
                else:
                    ocr_text = ocr_image(screenshot_path, self._config.ocr_engine)
        elif same_window:
            # Same window — reuse last OCR text, no screenshot
            ocr_text = self._last_ocr_text

        raw["screenshot_path"] = str(screenshot_path) if screenshot_path else None
        raw["ocr_text"] = ocr_text
        return raw

    def _is_blocked(self, raw: dict) -> bool:
        app = raw.get("app_name") or ""
        url = raw.get("url") or ""
        for blocked in self._config.privacy.blocked_apps:
            if blocked.lower() in app.lower():
                return True
        for blocked in self._config.privacy.blocked_urls:
            if blocked.lower() in url.lower():
                return True
        return False

    async def sample_once(self) -> None:
        idle_sec = get_idle_seconds()
        is_idle = idle_sec >= self._config.idle_threshold_sec

        if is_idle:
            if self._last_was_idle and self._last_id:
                await self._db.execute(
                    "UPDATE activities SET duration_sec = duration_sec + ? WHERE id = ?",
                    (self._config.interval_sec, self._last_id),
                )
                return

            row_id = await self._db.execute(
                """INSERT INTO activities
                   (timestamp, app_name, window_title, category, confidence, duration_sec)
                   VALUES (?, ?, ?, 'idle', 0.99, ?)""",
                (datetime.now().isoformat(), "System", "Idle", self._config.interval_sec),
            )
            self._last_app = None
            self._last_title = None
            self._last_id = row_id
            self._last_was_idle = True
            return

        self._last_was_idle = False

        raw = self._capture_raw()
        if not raw["app_name"] or self._is_blocked(raw):
            return

        app_name = raw["app_name"]
        window_title = raw["window_title"]

        if app_name == self._last_app and window_title == self._last_title and self._last_id:
            await self._db.execute(
                "UPDATE activities SET duration_sec = duration_sec + ? WHERE id = ?",
                (self._config.interval_sec, self._last_id),
            )
            return

        category, confidence, hints = classify_activity(app_name, window_title, raw["url"])

        signals = {
            "browser_url": raw["url"],
            "wecom_group_name": raw["wecom_group"],
            "screenshot_path": raw["screenshot_path"],
            "ocr_text": raw["ocr_text"],
            "hints": hints,
        }

        row_id = await self._db.execute(
            """INSERT INTO activities
               (timestamp, app_name, window_title, category, confidence, url, signals, duration_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                app_name,
                window_title,
                category,
                confidence,
                raw["url"],
                json.dumps(signals, ensure_ascii=False),
                self._config.interval_sec,
            ),
        )

        self._last_app = app_name
        self._last_title = window_title
        self._last_id = row_id

    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.sample_once()
            except Exception as e:
                print(f"[Monitor] Error: {e}")
            await asyncio.sleep(self._config.interval_sec)

    def stop(self) -> None:
        self._running = False
