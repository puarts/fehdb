#!/usr/bin/env bash
# Ollama セットアップスクリプト (macOS)
# FEH動画スキル抽出ツールのローカルOCR環境を構築する
#
# 使い方:
#   bash scripts/extract_from_video/setup-ollama.sh

set -euo pipefail

# デフォルトモデル（main.pyのデフォルトと一致）
DEFAULT_MODEL="qwen2.5vl"
# 追加モデル
EXTRA_MODEL="qwen3-vl:8b"

info()  { printf "\033[1;34m[INFO]\033[0m  %s\n" "$*"; }
ok()    { printf "\033[1;32m[OK]\033[0m    %s\n" "$*"; }
warn()  { printf "\033[1;33m[WARN]\033[0m  %s\n" "$*"; }
error() { printf "\033[1;31m[ERROR]\033[0m %s\n" "$*" >&2; }

# === 1. Homebrew 確認 ===
info "Homebrew を確認中..."
if ! command -v brew &>/dev/null; then
    error "Homebrew がインストールされていません"
    echo "  インストール: https://brew.sh/"
    exit 1
fi
ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"

# === 2. Ollama インストール ===
info "Ollama を確認中..."
if command -v ollama &>/dev/null; then
    ok "Ollama $(ollama --version | awk '{print $NF}') インストール済み"
else
    info "Ollama をインストール中..."
    brew install ollama
    ok "Ollama インストール完了"
fi

# === 3. Ollama サービス起動 ===
info "Ollama サービスを確認中..."
if brew services list | grep ollama | grep -q started; then
    ok "Ollama サービス起動中"
else
    info "Ollama サービスを起動中..."
    brew services start ollama
    # サービスが応答可能になるまで待機
    for i in $(seq 1 10); do
        if ollama list &>/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    ok "Ollama サービス起動完了（ログイン時に自動起動）"
fi

# === 4. モデルのダウンロード ===
pull_model() {
    local model="$1"
    if ollama list 2>/dev/null | grep -q "^${model}"; then
        ok "${model} ダウンロード済み"
    else
        info "${model} をダウンロード中（数分かかります）..."
        ollama pull "$model"
        ok "${model} ダウンロード完了"
    fi
}

pull_model "$DEFAULT_MODEL"
pull_model "$EXTRA_MODEL"

# === 5. 動作確認 ===
info "動作確認中..."
response=$(ollama run "$DEFAULT_MODEL" "Respond with only: OK" 2>/dev/null)
if echo "$response" | grep -qi "ok"; then
    ok "動作確認成功 (${DEFAULT_MODEL})"
else
    warn "動作確認: 予期しない応答: ${response}"
fi

# === 6. 完了 ===
echo ""
echo "=========================================="
echo " Ollama セットアップ完了"
echo "=========================================="
echo ""
echo "インストール済みモデル:"
ollama list 2>/dev/null | head -10
echo ""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "使い方は README.md を参照:"
echo "  ${SCRIPT_DIR}/README.md"
echo ""
echo "追加モデルの導入:"
echo "  ollama pull qwen3-vl:32b    # 高精度版 (20GB)"
