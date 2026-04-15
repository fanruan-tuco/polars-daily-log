"""Unit tests for the unified CollectorRuntime.

These exercise the sampling loop via mock adapter + mock backend, so we
don't rely on a real platform or a live server.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auto_daily_log_collector.config import CollectorConfig
from auto_daily_log_collector.enricher import ActivityEnricher
from auto_daily_log_collector.runner import CollectorRuntime


def _make_config(tmp_path, interval_sec=30, idle_threshold_sec=180, **extra):
    return CollectorConfig(
        server_url="http://server.test",
        name="Test-Mac",
        interval_sec=interval_sec,
        idle_threshold_sec=idle_threshold_sec,
        ocr_enabled=False,
        ocr_engine="tesseract",
        phash_enabled=False,
        data_dir=str(tmp_path / "cdata"),
        **extra,
    )


def _make_adapter(app="Visual Studio Code", title="main.py", url=None, tab_title=None, idle=0.0,
                  wecom_group=None):
    adapter = MagicMock()
    adapter.platform_id.return_value = "macos"
    adapter.platform_detail.return_value = "macOS test"
    adapter.capabilities.return_value = {"screenshot", "idle"}
    adapter.get_frontmost_app.return_value = app
    adapter.get_window_title.return_value = title
    adapter.get_browser_tab.return_value = (tab_title, url)
    adapter.get_wecom_chat_name.return_value = wecom_group
    adapter.get_idle_seconds.return_value = idle
    return adapter


def _make_backend(next_ids=None):
    backend = MagicMock()
    ids_iter = iter(next_ids or [])

    async def save_activities(machine_id, activities):
        assigned = []
        for _ in activities:
            try:
                assigned.append(next(ids_iter))
            except StopIteration:
                raise AssertionError("test exhausted next_ids — extend count off")
        return assigned

    async def extend_duration(machine_id, row_id, extra_sec):
        return None

    async def save_screenshot(machine_id, path):
        return str(path)

    async def heartbeat(machine_id):
        return None

    backend.save_activities = AsyncMock(side_effect=save_activities)
    backend.extend_duration = AsyncMock(side_effect=extend_duration)
    backend.save_screenshot = AsyncMock(side_effect=save_screenshot)
    backend.heartbeat = AsyncMock(side_effect=heartbeat)
    backend.close = AsyncMock()
    return backend


def _make_runtime(tmp_path, adapter, backend, **cfg_overrides):
    config = _make_config(tmp_path, **cfg_overrides)
    enricher = ActivityEnricher(
        screenshot_dir=tmp_path / "ss",
        hostile_apps_applescript=["WeCom"],
        hostile_apps_screenshot=[],
        phash_enabled=False,
    )
    runtime = CollectorRuntime(
        config=config,
        backend=backend,
        adapter=adapter,
        enricher=enricher,
        machine_id="local",
        skip_http_register=True,
    )
    return runtime


@pytest.mark.asyncio
async def test_sample_once_inserts_new_window(tmp_path):
    adapter = _make_adapter(app="Visual Studio Code", title="main.py")
    backend = _make_backend(next_ids=[42])
    runtime = _make_runtime(tmp_path, adapter, backend)

    row_id = await runtime.sample_once()

    assert row_id == 42
    assert backend.save_activities.await_count == 1
    assert backend.extend_duration.await_count == 0
    call_args = backend.save_activities.await_args
    machine_id, payloads = call_args[0]
    assert machine_id == "local"
    assert len(payloads) == 1
    assert payloads[0].app_name == "Visual Studio Code"
    assert payloads[0].window_title == "main.py"
    assert payloads[0].category == "coding"
    assert payloads[0].duration_sec == 30


@pytest.mark.asyncio
async def test_sample_same_window_accumulates_locally_without_backend_call(tmp_path):
    adapter = _make_adapter(app="Visual Studio Code", title="main.py")
    backend = _make_backend(next_ids=[7])
    runtime = _make_runtime(tmp_path, adapter, backend)

    await runtime.sample_once()  # inserts row 7
    await runtime.sample_once()  # same window — pending locally
    await runtime.sample_once()  # same window — pending locally

    # Only 1 save_activities call, 0 extend calls so far
    assert backend.save_activities.await_count == 1
    assert backend.extend_duration.await_count == 0
    assert runtime._pending_extend_sec == 60  # 30 + 30


@pytest.mark.asyncio
async def test_sample_window_change_flushes_pending_extend(tmp_path):
    adapter = _make_adapter(app="Visual Studio Code", title="main.py")
    backend = _make_backend(next_ids=[7, 8])
    runtime = _make_runtime(tmp_path, adapter, backend)

    await runtime.sample_once()  # row 7 — Code/main.py
    await runtime.sample_once()  # same — pending +30

    adapter.get_frontmost_app.return_value = "Safari"
    adapter.get_window_title.return_value = "Docs"
    adapter.get_browser_tab.return_value = (None, "https://example.com")

    await runtime.sample_once()  # window changed — flush + insert row 8

    assert backend.save_activities.await_count == 2
    assert backend.extend_duration.await_count == 1
    extend_call = backend.extend_duration.await_args
    assert extend_call[0] == ("local", 7, 30)


@pytest.mark.asyncio
async def test_sample_idle_aggregates(tmp_path):
    adapter = _make_adapter(idle=300.0)  # well above default threshold 180
    backend = _make_backend(next_ids=[100])
    runtime = _make_runtime(tmp_path, adapter, backend)

    id1 = await runtime.sample_once()  # first idle insert
    id2 = await runtime.sample_once()  # extend idle
    id3 = await runtime.sample_once()  # extend idle

    assert id1 == 100
    assert id2 is None
    assert id3 is None
    assert backend.save_activities.await_count == 1
    assert backend.extend_duration.await_count == 2
    idle_call = backend.save_activities.await_args_list[0]
    _, payloads = idle_call[0]
    assert payloads[0].category == "idle"
    assert payloads[0].app_name == "System"


@pytest.mark.asyncio
async def test_sample_hostile_app_skips_title_probe_and_no_wecom_call(tmp_path):
    adapter = _make_adapter(app="WeCom", title="ShouldNotBeRead")
    backend = _make_backend(next_ids=[55])
    runtime = _make_runtime(tmp_path, adapter, backend)

    await runtime.sample_once()

    adapter.get_window_title.assert_not_called()
    adapter.get_browser_tab.assert_not_called()
    adapter.get_wecom_chat_name.assert_not_called()
    # The row should still insert with app=WeCom, title=None
    _, payloads = backend.save_activities.await_args[0]
    assert payloads[0].app_name == "WeCom"
    assert payloads[0].window_title is None


@pytest.mark.asyncio
async def test_sample_blocked_app_does_not_insert(tmp_path):
    adapter = _make_adapter(app="1Password", title="Vault")
    backend = _make_backend(next_ids=[])
    runtime = _make_runtime(tmp_path, adapter, backend, blocked_apps=["1Password"])

    result = await runtime.sample_once()

    assert result is None
    assert backend.save_activities.await_count == 0


@pytest.mark.asyncio
async def test_sample_idle_after_active_flushes_pending(tmp_path):
    adapter = _make_adapter(app="Visual Studio Code", title="main.py")
    backend = _make_backend(next_ids=[7, 99])
    runtime = _make_runtime(tmp_path, adapter, backend)

    await runtime.sample_once()       # insert row 7
    await runtime.sample_once()       # pending +30

    adapter.get_idle_seconds.return_value = 500.0
    await runtime.sample_once()       # transition to idle — flush + idle insert

    # Flush of pending extend happened
    assert backend.extend_duration.await_count == 1
    assert backend.extend_duration.await_args[0] == ("local", 7, 30)
    # Idle insert happened
    _, last_payloads = backend.save_activities.await_args[0]
    assert last_payloads[0].category == "idle"


@pytest.mark.asyncio
async def test_idle_resets_enricher_window_state(tmp_path):
    """After idle transition, enricher's same-window cache must be cleared.

    Regression: without this, returning from idle to the same app+title
    was treated as same_window=True and skipped screenshot + OCR, leaving
    post-idle rows with no screenshot (observed on 2026-04-15 17:26-17:27).
    """
    adapter = _make_adapter(app="iTerm2", title="Auto worklog tool")
    backend = _make_backend(next_ids=[1, 2, 3])
    runtime = _make_runtime(tmp_path, adapter, backend, idle_threshold_sec=60)

    await runtime.sample_once()  # active — enricher caches iTerm2/title
    enricher = runtime._enricher
    assert enricher._last_app == "iTerm2"
    assert enricher._last_title == "Auto worklog tool"

    adapter.get_idle_seconds.return_value = 500.0
    await runtime.sample_once()  # idle — should reset enricher

    assert enricher._last_app is None
    assert enricher._last_title is None
    assert enricher._last_phash is None
    assert enricher._last_ocr_text is None


@pytest.mark.asyncio
async def test_reset_window_state_method_on_enricher(tmp_path):
    """Direct test of ActivityEnricher.reset_window_state()."""
    enricher = ActivityEnricher(
        screenshot_dir=tmp_path / "ss",
        hostile_apps_applescript=[],
        hostile_apps_screenshot=[],
        phash_enabled=False,
    )
    enricher._last_app = "iTerm2"
    enricher._last_title = "foo"
    enricher._last_phash = "hash123"
    enricher._last_ocr_text = "cached ocr"

    enricher.reset_window_state()

    assert enricher._last_app is None
    assert enricher._last_title is None
    assert enricher._last_phash is None
    assert enricher._last_ocr_text is None


@pytest.mark.asyncio
async def test_ensure_registered_skip_http_requires_machine_id_and_backend(tmp_path):
    config = _make_config(tmp_path)
    enricher = ActivityEnricher(
        screenshot_dir=tmp_path / "ss",
        hostile_apps_applescript=[],
        hostile_apps_screenshot=[],
    )
    backend = _make_backend()

    # Missing machine_id
    runtime = CollectorRuntime(
        config=config, backend=backend, adapter=_make_adapter(),
        enricher=enricher, skip_http_register=True,
    )
    with pytest.raises(RuntimeError, match="machine_id"):
        await runtime.ensure_registered()

    # Missing backend
    runtime = CollectorRuntime(
        config=config, backend=None, adapter=_make_adapter(),
        enricher=enricher, machine_id="local", skip_http_register=True,
    )
    with pytest.raises(RuntimeError, match="backend"):
        await runtime.ensure_registered()


@pytest.mark.asyncio
async def test_ensure_registered_skip_http_happy_path(tmp_path):
    config = _make_config(tmp_path)
    enricher = ActivityEnricher(
        screenshot_dir=tmp_path / "ss",
        hostile_apps_applescript=[],
        hostile_apps_screenshot=[],
    )
    backend = _make_backend()

    runtime = CollectorRuntime(
        config=config, backend=backend, adapter=_make_adapter(),
        enricher=enricher, machine_id="local", skip_http_register=True,
    )
    mid = await runtime.ensure_registered()
    assert mid == "local"
    assert runtime.machine_id == "local"
