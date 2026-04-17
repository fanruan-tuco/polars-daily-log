"""Runtime reader for the install-time built-in LLM config.

At install time, `install.sh` prompts the user for the passphrase the author
shared verbally, decrypts `builtin_llm.enc`, and writes the plaintext JSON to
`~/.auto_daily_log/builtin.key` (0600). This module loads that file on demand.

For dev convenience, a plaintext `REPO_ROOT/.secrets/builtin.json` is also
accepted — that path is gitignored and lets the author run from a source
checkout without re-running the install step.

Falls through to None if no config is available; callers should degrade
gracefully (e.g., tell the user to configure LLM in Settings).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _candidate_paths() -> list[Path]:
    paths: list[Path] = [Path.home() / ".auto_daily_log" / "builtin.key"]
    # Dev fallback — only meaningful when running from a source checkout.
    try:
        repo_root = Path(__file__).resolve().parent.parent
        paths.append(repo_root / ".secrets" / "builtin.json")
    except Exception:
        pass
    return paths


def load_builtin_llm_config() -> Optional[dict]:
    """Return the built-in LLM config dict, or None if not set up.

    Expected JSON keys: engine, api_key, base_url, model.
    """
    for path in _candidate_paths():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("api_key"):
            return data
    return None
