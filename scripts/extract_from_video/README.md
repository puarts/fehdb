# FEH公式動画スキルテキスト自動抽出

FEH（ファイアーエムブレム ヒーローズ）の公式紹介動画からスキル説明文を自動抽出し、既存パイプライン（`query.py`）互換の `.txt` ファイルを出力するツール。

## 処理フロー

```
YouTube動画 (JP/EN)
  ↓ yt-dlp (1080p)
ダウンロード済み動画
  ↓ ffmpeg freezedetect（静止区間を検出）
静止区間リスト
  ↓ ffmpeg -ss（各区間の中間フレームを1枚抽出）
静止フレーム画像
  ↓ 色分析ヒューリスティック
スキル画面候補フレーム
  ↓ パーセプチュアルハッシュで重複除去 + スクロール検出
代表フレーム (20〜35枚)
  ↓ （オプション）ローカルOCRヒント（Apple Vision / Tesseract）
OCRヒント付きフレーム
  ↓ OCR（Claude Vision API / Gemini Vision API / Ollama VLM）
構造化JSONデータ
  ↓ 過剰分割行のマージ + JP/ENマッチング + テキスト正規化
sources/skill-desc/{date}.txt
```

## 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- `yt-dlp` — YouTube動画ダウンロード
- `ffmpeg` — 静止区間検出・フレーム抽出
- `ANTHROPIC_API_KEY` 環境変数 — Claude Vision API用（`--ocr claude` 時）
- `GOOGLE_GENAI_API_KEY` 環境変数 — Gemini Vision API用（`--ocr gemini` 時）
- [Ollama](https://ollama.com/) — ローカルVLM用（`--ocr ollama` 時、オプション）

```bash
# macOSの場合
brew install yt-dlp ffmpeg
```

## セットアップ

プロジェクトルートで依存関係をインストール:

```bash
uv sync --all-packages
```

### Ollama セットアップ（オプション）

ローカルVLMでOCRを行う場合、セットアップスクリプトでOllamaのインストールからモデルのダウンロードまで一括で実行できる:

```bash
bash scripts/extract_from_video/setup-ollama.sh
```

スクリプトが行う処理:
1. Homebrew経由でOllamaをインストール
2. Ollamaサービスを起動（ログイン時に自動起動）
3. デフォルトモデル `qwen2.5vl` と追加モデル `qwen3-vl:8b` をダウンロード
4. 動作確認

## 使い方

`scripts/extract_from_video/` ディレクトリから実行する。

### 基本: JP + EN動画から抽出

```bash
uv run python main.py \
  --jp-url "https://youtube.com/watch?v=xxx" \
  --en-url "https://youtube.com/watch?v=yyy" \
  -o "10-02-17.txt"
```

### JPのみ（英語名なし）

```bash
uv run python main.py --jp-url "https://youtube.com/watch?v=xxx"
```

### ローカル動画ファイルを使用

```bash
uv run python main.py \
  --jp-video /path/to/jp.mp4 \
  --en-video /path/to/en.mp4
```

### ドライラン（プレビューのみ、ファイル出力なし）

```bash
uv run python main.py --jp-url "..." --dry-run
```

### Gemini Vision APIでOCR

```bash
# デフォルトモデル（gemini-3-flash-preview）
uv run python main.py --jp-video /path/to/jp.mp4 --ocr gemini

# モデル指定
uv run python main.py --jp-video /path/to/jp.mp4 --ocr gemini --gemini-model gemini-2.5-flash
```

### Ollama（ローカルVLM）でOCR

```bash
# デフォルトモデル（qwen2.5vl）
uv run python main.py --jp-video /path/to/jp.mp4 --ocr ollama

# モデル指定
uv run python main.py --jp-video /path/to/jp.mp4 --ocr ollama --ollama-model qwen3-vl
```

Ollamaの事前準備:

```bash
brew install ollama
ollama serve &
ollama pull qwen2.5vl
```

#### 推奨モデル

日本語OCRに対応したVision Language Modelを使用する。`--ollama-model` にはOllamaのモデル名（タグ含む）をそのまま指定する。

| モデル | サイズ | 日本語OCR | 備考 |
|---|---|---|---|
| `qwen2.5vl`（デフォルト） | 6.0GB (7B) | 良好 | 日本語を含む多言語OCR対応。安定性が高い |
| `qwen2.5vl:3b` | 3.2GB (3B) | やや劣る | 軽量・高速だがOCR精度は7Bより低い |
| `qwen2.5vl:32b` | 21GB (32B) | 高精度 | VRAM/メモリに余裕がある場合に推奨 |
| `qwen3-vl` | 6.1GB (8B) | 良好 | 32言語OCR対応。qwen2.5vlの後継。コンテキスト256K |
| `qwen3-vl:4b` | 3.3GB (4B) | やや劣る | 軽量版。簡易確認用 |
| `qwen3-vl:32b` | 21GB (32B) | 高精度 | 最高精度が必要な場合。GPT-4o超の総合ベンチマーク |

> **メモリ目安**: 7B/8Bモデルは8GB以上、32Bモデルは32GB以上のメモリ（またはVRAM）を推奨。

### ローカルOCRヒント付きで実行

VLMの精度向上のため、ローカルOCRエンジンの結果をヒントとして渡せる:

```bash
# Apple Vision（macOSのみ）
uv run python main.py --jp-video /path/to/jp.mp4 --ocr gemini --local-ocr apple

# 自動検出（利用可能なエンジンを自動選択）
uv run python main.py --jp-video /path/to/jp.mp4 --ocr ollama --local-ocr auto
```

### フレーム抽出のみ（OCRなし）

```bash
uv run python main.py --jp-video /path/to/jp.mp4 --frames-only
```

フレーム画像は `.work/frames/` に保存される。スキル画面の検出精度を目視確認する際に使う。

## CLI引数

| 引数 | 説明 | デフォルト |
|---|---|---|
| `--jp-url` | 日本語版動画のURL | — |
| `--jp-video` | 日本語版動画のローカルパス | — |
| `--en-url` | 英語版動画のURL（省略可） | — |
| `--en-video` | 英語版動画のローカルパス（省略可） | — |
| `-o`, `--output` | 出力ファイル名（`sources/skill-desc/` に配置） | 自動生成 |
| `--start-id` | スキルID開始番号 | DB最大値+1 |
| `--all` | 全スキルをOCR（デフォルト: 新スキル「！」付きのみ） | — |
| `--dry-run` | プレビューのみ（ファイル出力しない） | — |
| `--frames-only` | フレーム抽出・スキル画面検出まで実行（OCRは行わない） | — |
| `--keep-frames` | 処理後にフレーム画像を残す | — |
| `--min-duration` | 静止区間の最低秒数（短い静止を無視） | 1.5秒 |
| `--ocr` | OCRバックエンド（`claude`, `gemini`, `ollama`） | `claude` |
| `--gemini-model` | Geminiモデル名 | `gemini-3-flash-preview` |
| `--ollama-model` | Ollamaモデル名 | `qwen2.5vl` |
| `--local-ocr` | ローカルOCRでVLMにヒント提供（`auto`, `apple`, `tesseract`, `none`） | `none` |
| `--id` | キャッシュ識別子（動画ごとにキャッシュを分離） | — |

`--jp-url` と `--jp-video` はどちらか一方が必須。EN側は省略可（英語名なしで出力される）。

## 出力フォーマット

`sources/skill-desc/*.txt` と同じ形式で出力される。そのまま `query.py` に渡せる。

```
3567-n-スキル名-English Name
## w-rs
## 威力：16 射程：1
説明文1行目<br>説明文2行目

3568-n-奥義名-Special Name
## s
## @3
奥義の説明文
```

## モジュール構成

| ファイル | 役割 |
|---|---|
| `main.py` | CLIエントリポイント、パイプラインのオーケストレーション |
| `download.py` | yt-dlpによる動画ダウンロード（1080p）、タイトルからの言語自動判定 |
| `frames.py` | ffmpeg freezedetectによる静止区間検出、色分析によるスキル画面検出、パーセプチュアルハッシュで重複除去 |
| `ocr.py` | OCRバックエンド共通インターフェース（Protocol）、ファクトリ、共有ユーティリティ |
| `ocr_claude.py` | Claude Vision APIバックエンド（JP: 個別リクエスト、EN: バッチ処理） |
| `ocr_gemini.py` | Gemini Vision APIバックエンド |
| `ocr_ollama.py` | Ollama VLMバックエンド（ローカル実行） |
| `local_ocr.py` | ローカルOCRエンジン（Apple Vision / Tesseract）によるVLMヒント生成 |
| `line_merger.py` | VLMが過剰分割した行のマージ後処理（行頭パターンのホワイトリストで判定） |
| `formatter.py` | OCR結果を `.txt` フォーマットに変換、JP/ENマッチング、テキスト正規化 |
| `models.py` | データクラス定義（`ExtractedSkill`, `FrameGroup`, `VideoInfo`） |
| `run.sh` | ショートカットスクリプト（`<id> <jp-url> <en-url>` で実行） |

## キャリブレーション

### 静止区間検出

`--min-duration` で静止区間の最低秒数を調整できる。スキル画面は通常2〜3秒静止するため、デフォルト1.5秒で十分。誤検出が多い場合は2.0秒に引き上げる。

### スキル画面検出

`frames.py` 内の色分析閾値は動画の画質や構成によって調整が必要な場合がある。

```python
# 色分析の閾値
DARK_PIXEL_THRESHOLD = 80     # 暗色判定のRGB平均値
BRIGHT_PIXEL_THRESHOLD = 200   # 明色判定のRGB平均値
MIN_DARK_RATIO = 0.12          # 暗色ピクセルの最低比率
MIN_BRIGHT_RATIO = 0.08        # 明色ピクセルの最低比率

# 水平エッジ検出の閾値
ROW_GRADIENT_THRESHOLD = 15    # 隣接行の輝度差がこれ以上でエッジとみなす
MIN_GAP_BETWEEN_EDGES = 10     # エッジ行のグルーピング間隔
MIN_HORIZONTAL_LINES = 7       # スキル画面と判定する最小水平線数

# 重複除去・スクロール検出の閾値
HASH_THRESHOLD = 8             # ハミング距離しきい値
SCROLL_NAME_THRESHOLD = 5      # スキル名一致の閾値（低い=一致）
SCROLL_DESC_THRESHOLD = 10     # 説明文差異の閾値（高い=異なる）
```

`--frames-only` または `--keep-frames` で抽出フレームを残し、検出精度を目視確認できる。

## API コスト目安

### Claude（`--ocr claude`）

- JP（1スキル1リクエスト × 約30スキル）: 約$0.30〜$1.00
- EN（バッチ処理）: 約$0.05〜$0.10
- 合計: 1回の新英雄動画処理で約$0.35〜$1.10

### Gemini（`--ocr gemini`）

Gemini Flash系モデルは低コスト。詳細は [Gemini API pricing](https://ai.google.dev/pricing) を参照。

### Ollama（`--ocr ollama`）

ローカル実行のため API コストなし。ただし処理速度はハードウェア性能に依存する。

## 出力の検証

```bash
cd scripts/update_skill_description
uv run python query.py --dry-run --check-id ../../sources/skill-desc/<出力ファイル>
```
