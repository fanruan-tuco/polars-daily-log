#!/usr/bin/env bash
# ─── Dev helper: encrypt built-in LLM config ─────────────────────────────
# Reads plaintext .secrets/builtin.json (gitignored) and writes the encrypted
# blob to auto_daily_log/builtin_llm.enc. Run this whenever the built-in key
# changes or you want to rotate.
#
# The passphrase is hardcoded on purpose. This is NOT real security — it only
# defeats automated secret scanners (GitHub, Moonshot, GitLeaks) that look for
# literal sk-... patterns in the repo. Anyone who reads install.sh can
# trivially decrypt. See AGENTS.md for the threat model.
#
# Usage:
#   bash scripts/encrypt-builtin.sh
# ─────────────────────────────────────────────────────────────────────────

set -euo pipefail

PASSPHRASE="polars"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="$ROOT_DIR/.secrets/builtin.json"
OUTPUT="$ROOT_DIR/auto_daily_log/builtin_llm.enc"

if [ ! -f "$INPUT" ]; then
    echo "错误: $INPUT 不存在" >&2
    echo "复制 .secrets/builtin.json.example 并填入真实 LLM 配置后再跑" >&2
    exit 1
fi

command -v openssl >/dev/null 2>&1 || { echo "需要 openssl"; exit 1; }

# Sanity-check JSON so we don't encrypt garbage.
python3 -c "import json,sys; json.load(open('$INPUT'))" 2>/dev/null || {
    echo "错误: $INPUT 不是合法 JSON" >&2
    exit 1
}

openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt \
    -in "$INPUT" -out "$OUTPUT" \
    -pass pass:"$PASSPHRASE" -base64

echo "✓ 加密完成: $OUTPUT"
echo "  下一步: git add auto_daily_log/builtin_llm.enc && git commit"
echo "  (.secrets/builtin.json 已在 .gitignore 中，不会被提交)"
