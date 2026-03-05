#\!/usr/bin/env bash
# FEHスキルテキスト抽出のショートカットスクリプト
#
# 使用例:
#   bash scripts/extract_from_video/run.sh <id> <jp-url> <en-url>
#   bash scripts/extract_from_video/run.sh --dry-run <id> <jp-url> <en-url>
#
# idがそのままoutputファイル名（<id>.txt）にも使われる

set -euo pipefail

DRY_RUN=""
while getopts ":-:" opt; do
  case $opt in
    -)
      case "$OPTARG" in
        dry-run) DRY_RUN="--dry-run" ;;
        *) echo "Unknown option: --$OPTARG" >&2; exit 1 ;;
      esac
      ;;
    *) echo "Unknown option: -$OPTARG" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))

if [ $# -ne 3 ]; then
  echo "Usage: $0 [--dry-run] <id> <jp-url> <en-url>" >&2
  exit 1
fi

ID="$1"
JP_URL="$2"
EN_URL="$3"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

uv run python "$SCRIPT_DIR/main.py" \
  --id "$ID" \
  -o "${ID}.txt" \
  --jp-url "$JP_URL" \
  --en-url "$EN_URL" \
  --min-duration 1.5 \
  --ocr gemini \
  --keep-frames \
  --local-ocr apple \
  $DRY_RUN
