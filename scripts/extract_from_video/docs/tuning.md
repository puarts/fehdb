# ボーダー検出パラメータ最適化

`card_crop.py` のスキル画面判定パラメータをグリッドサーチで最適化した記録。

## 背景

`card_crop.py` は公式紹介動画のフレームから金色ボーダーを検出し、スキル一覧画面かどうかを判定する。判定には6つの制御パラメータがあり、初期値は手動で決めたものだった。

`.work/frames/` のラベル付きフレーム（JP 22枚 + EN 24枚、うちラベル有効 43枚）を使い、全パラメータ組み合わせ 9,000通りのグリッドサーチで最適値を探索した。

## アルゴリズム概要

```
フレーム画像
  → DETECT_PANEL_CROP でパネル領域をクロップ
  → グレースケール化 → 各行の平均輝度を計算
  → 隣接行の輝度差 ≥ ROW_GRADIENT_THRESHOLD の行をエッジとして検出
  → MIN_GAP_BETWEEN_EDGES 以内のエッジ行をグループ化
  → グループ幅 ≥ MIN_BORDER_SPAN かつ 最小輝度 < BORDER_MIN_BRIGHTNESS_THRESHOLD → 金色ボーダー
  → ボーダー数 ≥ MIN_GOLD_BORDERS かつ 明るいピクセル比率 ≥ MIN_BRIGHT_RATIO_FOR_SKILL → スキル画面
```

## 最適化結果

### パラメータ変更

| パラメータ | 初期値 | 最適値 | 意味 |
|---|---|---|---|
| `ROW_GRADIENT_THRESHOLD` | 15 | **10** | エッジ検出の輝度差閾値 |
| `MIN_GAP_BETWEEN_EDGES` | 10 | **5** | エッジグループ化の最大ギャップ |
| `BORDER_MIN_BRIGHTNESS_THRESHOLD` | 100 | **120** | 金色ボーダーの輝度上限 |
| `MIN_BORDER_SPAN` | 8 | **4** | ボーダーの最小幅（ピクセル行数） |
| `MIN_GOLD_BORDERS` | 3 | 3 | スキル画面の最低ボーダー数（変更なし） |
| `MIN_BRIGHT_RATIO_FOR_SKILL` | 0.30 | **0.20** | 明るいピクセルの最低比率 |

### 精度

- **初期値**: 35/43 (81.4%)
- **最適値**: 41/43 (95.3%)

### 誤判定の内訳

残り2件はいずれも**偽陽性**（非スキル画面をスキルと誤検出）:

| フレーム | 内容 | ボーダー数 | 明るさ比率 |
|---|---|---|---|
| JP frame_00010 | 英雄紹介（スプライト＋テキスト） | 4 | 68.8% |
| JP frame_00011 | 英雄能力説明（キャラ絵＋テキスト） | 5 | 38.6% |

**偽陰性（スキル画面の見逃し）は0件。**

### 非対称評価

スキル画面の見逃し（偽陰性）は後段のOCR処理に致命的だが、非スキル画面の誤検出（偽陽性）はLLMが処理時に弾ける。この非対称性を考慮した評価（FN=-3点, FP=-1点, 正答=+1点）でも最適パラメータは同一だった。

FN=0を制約条件とした探索でも同じパラメータが選出され、現在のパラメータが「見逃しゼロ」の条件下で最も高い正答率を達成している。

## スクリプト

スクリプトは `tuning/` ディレクトリに配置:

```bash
cd scripts/extract_from_video

# メイン: グリッドサーチ + 非対称評価
uv run python tuning/verify_card_crop.py

# 旧アルゴリズム（count_horizontal_edges）の検証用
uv run python tuning/verify_edge_detection.py

# クロップ結果の目視確認用
uv run python tuning/verify_crop_rows.py
```

## Ground Truth

`.work/frames/{jp,en}/` のフレームに対して手動でラベルを付与:

- **True** — スキル一覧画面（習得可能スキルリスト）
- **False** — 非スキル画面（英雄紹介、ストーリー、バナー、召喚等）
- **None** — 境界ケース（双界/スタイルスキル説明）。評価から除外

| データセット | フレーム数 | True | False | None |
|---|---|---|---|---|
| JP | 22 | 8 | 12 | 2 |
| EN | 24 | 13 | 10 | 1 |
| **合計** | **46** | **21** | **22** | **3** |

評価対象（None除外）: **43枚**

## パラメータ再調整の手順

新しい動画セットでフレームが追加された場合:

1. `.work/frames/{jp,en}/` に新フレームを配置
2. `tuning/verify_card_crop.py` の `JP_LABELS` / `EN_LABELS` に新フレームのラベルを追加
3. `uv run python tuning/verify_card_crop.py` でスイープ実行
4. 最良パラメータが変わった場合、`card_crop.py` の定数を更新
