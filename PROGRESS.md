# Progress

### [2026-03-08 00:00] セッション概要

**完了**:
- 動画OCRテキスト抽出タスクの自動試行錯誤ループについて検討・回答
  - 正解ファイルとの比較によるループ実行が可能であることを確認
  - 調整ポイント（OCRプロンプト、freezedetect閾値、色分析パラメータ、正規化ルール）を整理

**保留/次回のタスク**:
- 実際の動画を使ったOCR試行錯誤ループの実装・実行（ユーザーが具体的な動画を指定次第）

**変更ファイル**:
- なし（議論のみ）

**メモ**:
- OCR部分だけを切り出してループさせるのが効率的（抽出済みフレーム画像を再利用）
- Claude Vision APIを使う場合はコストに注意

### [2026-03-10 xx:xx] card_crop.py パラメータ最適化 + ファイル整理

**完了**:
- `card_crop.py` のボーダー検出パラメータをグリッドサーチで最適化（81.4% → 95.3%）
- `verify_card_crop.py` に非対称評価（FN重ペナルティ）を追加、FN=0制約付き探索を実装
- 検証/チューニングスクリプトを `tuning/` ディレクトリに分離
  - `verify_card_crop.py`, `verify_crop_rows.py`, `verify_edge_detection.py`
  - インポートパス・`.work/` 参照パスを修正
- `issues/` を `docs/issues/` に移動、`card_crop.py` のパス参照を更新
- パラメータ最適化のドキュメントを `docs/tuning.md` に作成

**保留/次回のタスク**:
- なし

**変更ファイル**:
- `scripts/extract_from_video/card_crop.py` — パラメータ更新済み、コメントのパス修正
- `scripts/extract_from_video/tuning/verify_card_crop.py` — 新規（グリッドサーチ + 非対称評価）
- `scripts/extract_from_video/tuning/verify_crop_rows.py` — 移動 + パス修正
- `scripts/extract_from_video/tuning/verify_edge_detection.py` — 移動 + パス修正
- `scripts/extract_from_video/docs/tuning.md` — 新規（最適化ドキュメント）
- `scripts/extract_from_video/docs/issues/exclamation-mark-detection.md` — 移動

**メモ**:
- 最適パラメータ: ROW_GRADIENT=10, GAP=5, BRIGHTNESS=120, SPAN=4, GOLD=3, BRIGHT_RATIO=0.20
- 残り2件の誤判定は偽陽性のみ（JP frame_00010, 00011）。偽陰性は0件
- 対称/非対称どちらの評価でも同じ最適パラメータが選出された

### [2026-03-11 xx:xx] クロップ効果検証 + 採用決定

**完了**:
- `tuning/verify_ocr_crop.py` を作成（crop有/無の2モードでOCR実行し、正解ファイルと比較）
  - `--ocr` オプション追加（claude/gemini/ollama選択可能）
  - フォーマットバグ修正（int→str変換）
- Gemini OCRで `10-03-06` データを使い crop / nocrop 両方を検証実行
- **クロップ採用を決定**（main.py では既にデフォルト有効だった）

**検証結果サマリ** (Gemini, 10-03-06, 正解11スキル):

|  | Crop | NoCrop |
|---|---|---|
| 名前一致 | 10/10 | 10/10 |
| 説明類似度 | 99.2% | 99.0% |
| 既存スキル誤検出 | 0 | 3 |
| 全角文字混入 | 少ない | 多い |

- Cropの優位: 新スキルフィルタリング正確、全角文字混入少ない
- メタデータ（武器種・スキルタイプ）の不一致はcrop/nocrop共通の問題 → 別途プロンプト改善で対応すべき

**保留/次回のタスク**:
- `TEXT_REPLACEMENTS` に `％`→`%`、`－`→`-`、`ＨＰ`→`HP` 等を追加
- メタデータ精度改善: プロンプトにスキルタイプアイコン読み取り指示追加、武器種はスキル並び順から推定
- ブランチの変更をコミット/PR

**変更ファイル**:
- `scripts/extract_from_video/tuning/verify_ocr_crop.py` — 新規（クロップ効果検証スクリプト）

**メモ**:
- `#3585 影助・引き戻し3` はDBに未登録だが新規スキルではない → `is_new: false` が正しい判定（cropが正しく除外、nocropは誤検出）
- `#3586 魔器・春風の旋刃` は crop/nocrop 両方で93.5%（【追撃の鼓動】説明文が余分に含まれる）— OCRプロンプト側の問題
- nocropは全角 `－`/`％`/`ＨＰ` の混入が多い（`TEXT_REPLACEMENTS` に未登録）

### [2026-03-11 xx:xx] TEXT_REPLACEMENTS 全角文字追加

**完了**:
- `formatter.py` の `TEXT_REPLACEMENTS` に全角→半角の正規化エントリ3件を追加
  - `％` → `%`、`－` → `-`、`ＨＰ` → `HP`
- 動作確認済み（`ＨＰ＋５％` → `HP+５%` — 全角英字・記号が正しく変換）

**保留/次回のタスク**:
- メタデータ精度改善: プロンプトにスキルタイプアイコン読み取り指示追加、武器種はスキル並び順から推定
- ブランチの変更をコミット/PR

**変更ファイル**:
- `scripts/extract_from_video/formatter.py` — `TEXT_REPLACEMENTS` に3エントリ追加

**メモ**:
- 前回のcrop有/無検証でnocropモード時に全角文字混入が判明した問題への対処
- `replace.py` L17 にも `－` → `-` の同等エントリあり（整合性OK）

### [2026-03-15 xx:xx] 英雄紹介フレーム検出: freezedetect グリッドサーチ

**完了**:
- `tuning/extract_all_frames.py` 新規作成 — 緩いパラメータ（freezedetect + scene detection）でフレーム大量抽出
- `tuning/verify_hero_detection.py` 新規作成 — 複数動画対応のfreezedetectグリッドサーチスクリプト
- 7本の紹介動画（春英雄〜通常新英雄）から計24の英雄紹介フレームを手動ラベル付け
- 5本の動画をYouTubeからダウンロード（09-01-06, 09-05-07, 09-09-16, 09-10-17, 10-02-16）
- noise×d = 7×4 = 28通りのグリッドサーチを全7動画で実行（計196回のffmpeg実行）
- **最良パラメータ `noise=0.08, d=1.5`** を決定（FN=0, FP=427）
- 結果を `docs/hero_detection_grid_search.md` にドキュメント化

**保留/次回のタスク**:
- Step 3: パイプライン統合 — `frames.py` に `extract_hero_intro_frames()` を追加
- `main.py` に「Step 2.5: 英雄紹介フレーム検出」を追加
- 英雄紹介フレームから武器種アイコンの画像処理検出（別タスク）

**変更ファイル**:
- `scripts/extract_from_video/tuning/extract_all_frames.py` — 新規
- `scripts/extract_from_video/tuning/verify_hero_detection.py` — 新規
- `scripts/extract_from_video/docs/hero_detection_grid_search.md` — 新規（グリッドサーチ結果）
- `scripts/extract_from_video/data/*/annotations/hero_frame_labels.json` — 7動画分の正解ラベル
- `scripts/extract_from_video/data/*/all_frames/` — 抽出フレーム画像+メタデータ

**メモ**:
- 最良: `noise=0.08, d=1.5` — 全7動画・24英雄紹介でFN=0達成
- `noise=0.05`以下だと春英雄（花びらパーティクル）のサザ(@136s)で見逃し発生
- scene detectionは単独ではFN=0を達成不可（春英雄のシーン変化が小さい）
- FPは平均61/動画と多いが、後段の画像分類で除去する前提
