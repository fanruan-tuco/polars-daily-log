# Collector Data Path Unification — Execution SUMMARY

**Plan**: `docs/plans/2026-04-15-collector-unify-data-path.md`
**Branch**: `feat/implement-auto-daily-log`
**Baseline commit**: `31d5fcf` (plan doc)

## Commits

```
45ad308 refactor: unify data path — phase 4 — delete LocalSQLiteBackend
3ebc30b refactor: unify data path — phase 3 — built-in collector uses HTTPBackend
7594179 refactor: unify data path — phase 2 — built-in token self-distribution
```

Phase 1 (read-only exploration) and phase 5 (test regression) produced no
code changes — folded into phases 2 and 4 respectively. Phase 6 is this
SUMMARY commit.

## Test suite

Baseline (plan doc): **230 passed**
After phase 4: **233 passed** (+3)

New / rewritten test files:
- `tests/test_builtin_token.py` — NEW (3 tests)
  - `test_register_builtin_collector_mints_token_first_time`
  - `test_register_builtin_collector_is_idempotent`
  - `test_register_builtin_collector_token_hash_matches_plaintext`
- `tests/test_builtin_collector.py` — REWRITTEN (same 6 test names, now
  driving `CollectorRuntime + HTTPBackend` against the real FastAPI app
  via `httpx.ASGITransport` instead of the in-process `LocalSQLiteBackend`).
- `tests/test_phase_b_backends.py` — REWRITTEN (schema tests kept;
  old `LocalSQLiteBackend` unit tests reworked as HTTP integration
  tests over the same ASGI transport; HTTPBackend offline-queue/retry
  tests kept; 13 tests total, same semantic coverage).

`tests/test_database_async_backend.py` — preserved untouched; despite
its name it tests `Database`'s async init, not any backend.

## What changed

### Phase 2 — Token self-distribution
- `Application.__init__`: new `_builtin_token` attribute.
- `Application._register_builtin_collector`:
  - Reads or mints `tk-builtin-<base64>` into
    `settings.builtin_collector_token` (idempotent across restarts).
  - Writes sha256 hash onto `collectors.token_hash WHERE machine_id='local'`.

### Phase 3 — Built-in collector via loopback HTTP
- `Application._make_builtin_collector()`: builds `CollectorRuntime`
  with `HTTPBackend(server_url="http://127.0.0.1:<server.port>",
  token=self._builtin_token)`. Deleted the old `_init_monitor`.
- `Application._wait_for_server_ready(port, timeout=10)`:
  `asyncio.open_connection` polled every 200ms until uvicorn binds, then
  the collector task starts — no more bind-vs-POST race.
- `Application.run()` sequence: init_db → register_builtin_collector →
  scheduler → uvicorn task → wait_for_server_ready → collector task +
  watchdog.
- `/api/collectors/local/heartbeat` now surfaces `settings.monitor_*`
  runtime knobs (ocr_enabled / ocr_engine / interval_sec) so UI edits
  still take effect on the next tick — matching the behaviour the old
  `LocalSQLiteBackend.heartbeat()` exposed in-process.

### Phase 4 — Delete LocalSQLiteBackend
- Removed `auto_daily_log/models/backends/local.py` and its export from
  `models/backends/__init__.py`.
- Updated `base.py` and `auto_daily_log_collector/runner.py` docstrings
  (HTTPBackend is the only backend).
- Fixed `HTTPBackend.save_commits` / `_post_batch` to return the server's
  `accepted` count — previously always returned `0` because the commits
  response has no `first_id`/`last_id` fields (existing bug masked by the
  old LocalSQLiteBackend path).

## Phase 6 — End-to-end verification

Executed against a restarted server on port 8888. Raw output:

```
=== Check 1: pdl server restart ===
→ Stopping server (PID 6045) ...
! Killing port stragglers: 6048
✓ Server stopped
→ Starting server on port 8888 ...
✓ Server started (PID 9368) — http://127.0.0.1:8888
→ Logs: /Users/conner/.auto_daily_log/logs/server.log

=== Check 2: collectors.local row ===
local|Built-in (this machine)|2026-04-15 08:52:29|21294752c648b76b...

=== Check 3: recent activities from local (last 2 minutes) ===
262
Latest 3 rows:
id    timestamp            app_name  duration_sec
----  -------------------  --------  ------------
1421  2026-04-15T16:52:29  企业微信      30
1420  2026-04-15T16:59:00  CurlTest  1
1419  2026-04-15T16:51:58  iTerm2    30

=== Check 4: server log POST /api/ingest (last 6) ===
INFO:     127.0.0.1:64677 - "POST /api/ingest/activities HTTP/1.1" 200 OK
INFO:     127.0.0.1:64962 - "POST /api/ingest/screenshot?timestamp=2026-04-15T16%3A51%3A57 HTTP/1.1" 200 OK
INFO:     127.0.0.1:64964 - "POST /api/ingest/activities HTTP/1.1" 200 OK
INFO:     127.0.0.1:65177 - "POST /api/ingest/activities HTTP/1.1" 200 OK
INFO:     127.0.0.1:65286 - "POST /api/ingest/screenshot?timestamp=2026-04-15T16%3A52%3A28 HTTP/1.1" 200 OK
INFO:     127.0.0.1:65290 - "POST /api/ingest/activities HTTP/1.1" 200 OK

=== Check 5: manual curl with built-in token ===
Token prefix: tk-builtin-aYWB6kN66Yqke...
{"accepted":1,"rejected":0,"first_id":1422,"last_id":1422}
Verify curl row inserted:
id    app_name        window_title  timestamp            machine_id
----  --------------  ------------  -------------------  ----------
1422  CurlTestPhase6  Manual        2026-04-15T17:00:00  local
```

All 5 checks pass:
1. Server restart clean.
2. `collectors.machine_id='local'` row has non-empty `token_hash`, fresh
   `last_seen`.
3. New activities (id 1419, 1421) flowed in after restart — the
   in-process collector is writing via HTTP.
4. Server access log shows `127.0.0.1:*` POSTing to `/api/ingest/activities`
   + `/api/ingest/screenshot` with 200 OK (proves loopback path).
5. Manual `curl` using the same token the built-in collector uses
   accepts the write — token-based auth works interchangeably for
   in-process and external callers.

## Completion checklist (plan §7)

- [x] Full test suite passes (233 ≥ 230 + 3 new/rewritten).
- [x] `auto_daily_log/models/backends/local.py` deleted.
- [x] Server log shows `local` collector's POSTs to `/api/ingest/activities`.
- [x] `collectors.token_hash WHERE machine_id='local'` non-empty
      (`21294752c648b76b...`).
- [x] `settings.builtin_collector_token` exists
      (prefix `tk-builtin-aYWB6kN66Yqke...`).
- [x] Manual curl with the same token ingests a row.
- [x] This SUMMARY document.

## Trade-offs / notes

1. **`save_commits` return value** — fixed a pre-existing bug where
   `HTTPBackend.save_commits` always returned 0 because the
   `/api/ingest/commits` response has no `first_id`/`last_id`. Now
   returns the server's `accepted` count. No test previously exercised
   this round-trip end-to-end (only `LocalSQLiteBackend` did) — which is
   precisely the problem the unification is meant to fix.

2. **Settings-table override merge order** — in the new HTTP heartbeat
   path for `machine_id='local'`, if both `collectors.config_override`
   and `settings.monitor_*` are set, the collector-row override wins per
   field (merge order `{**settings, **collectors_override}`). That
   matches intent: explicit per-collector override from the UI "Pause /
   push config" path should take precedence over the generic monitor
   settings.

3. **Screenshot double-I/O** — flagged in plan §5 as acceptable. The
   in-process collector writes the PNG to disk, then multipart-uploads
   it to its own server which writes it back to the same directory tree.
   Wasteful but correct; defer optimisation until it matters.

4. **`tests/test_database_async_backend.py`** — plan §4.4 listed this
   for deletion but the file actually tests `Database`'s async
   initialization, not any backend. Preserved intact.

5. **No changes to `/api/ingest/*` schema or auth** — honoured the
   plan's §6 constraint. Both external and built-in collectors use the
   identical Bearer + X-Machine-ID protocol.

## Remaining TODOs

None. Plan fully executed. The follow-up `llm_summary` feature (plan
§8) now has the "single data entry point" invariant it depends on:
any worker watching DB inserts sees all activities regardless of
collector origin.
