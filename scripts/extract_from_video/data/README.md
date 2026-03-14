# 教師データ (Ground Truth Dataset)

OCR精度向上・フレーム分類の検証に使用する教師データ。
ML慣習（COCO形式、HuggingFace Datasets）に倣い、`images/` と `annotations/` を分離。

## ディレクトリ構成

```
data/
├── README.md
└── {session-id}/              # 日付ID（例: 10-03-06）
    ├── metadata.json          # データセットメタデータ（動画URL等）
    ├── images/
    │   ├── jp/                # JP版フレーム画像
    │   │   ├── frame_00000.png
    │   │   └── ...
    │   └── en/                # EN版フレーム画像
    │       ├── frame_00000.png
    │       └── ...
    └── annotations/
        ├── frame_labels.json  # フレーム分類ラベル
        └── ocr_ground_truth.txt  # OCR正解テキスト
```

## 各ファイルの説明

### metadata.json

動画URL・フレーム数等のメタデータ。再ダウンロード・再抽出に必要。

### annotations/frame_labels.json

フレーム分類の正解ラベル。`tuning/verify_card_crop.py` 等が使用。

| ラベル | 意味 |
|--------|------|
| `skill_screen` | スキル画面（習得可能スキルリスト） |
| `non_skill_screen` | 非スキル画面（英雄紹介、ストーリー等） |
| `ambiguous` | 境界ケース（双界/スタイルスキル説明） |

### annotations/ocr_ground_truth.txt

OCR正解テキスト。`sources/skill-desc/{date}.txt` と同一形式。

## 新規セッションの追加手順

1. `data/{session-id}/` ディレクトリを作成
2. `metadata.json` を作成（動画URL、説明を記入）
3. `.work/{session-id}/frames/` から代表フレームを `images/jp/`, `images/en/` にコピー
4. `frame_labels.json` を作成（各フレームに分類ラベルを付与）
5. `sources/skill-desc/{date}.txt` を `ocr_ground_truth.txt` としてコピー

## git管理の方針

| データ | git管理 | 理由 |
|--------|---------|------|
| metadata.json | する | 再現性の鍵 |
| frame_labels.json | する | 教師データ本体 |
| ocr_ground_truth.txt | する | 教師データ本体 |
| フレーム画像（PNG） | する | 検証の再現に必須 |
| 動画MP4 | しない | URLから再取得可能 |
| 全フレームPNG | しない | 動画から再生成可能 |
| クロップ済み画像 | しない | 再生成可能 |
