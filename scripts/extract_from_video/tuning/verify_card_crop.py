"""card_crop.py のボーダー検出パラメータ最適化スクリプト

全サンプルフレームに対して find_horizontal_borders() → is_skill_frame() の
パラメータをグリッドサーチし、正答率を最大化するパラメータ組み合わせを探索する。
ラベルは data/{session}/annotations/frame_labels.json から読み込む。
"""

import itertools
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from card_crop import BRIGHT_PIXEL_THRESHOLD, DETECT_PANEL_CROP

# ラベル文字列 → Python値の変換
LABEL_MAP: dict[str, bool | None] = {
    "skill_screen": True,
    "non_skill_screen": False,
    "ambiguous": None,
}


def load_labels_from_json(
    labels_path: Path,
) -> tuple[dict[str, bool | None], dict[str, bool | None]]:
    """frame_labels.json からJP/ENラベルを読み込む"""
    with open(labels_path) as f:
        data = json.load(f)
    annotations = data["annotations"]
    jp = {name: LABEL_MAP[label] for name, label in annotations.get("jp", {}).items()}
    en = {name: LABEL_MAP[label] for name, label in annotations.get("en", {}).items()}
    return jp, en


@dataclass
class Params:
    row_gradient_threshold: int
    min_gap_between_edges: int
    border_min_brightness_threshold: int
    min_border_span: int
    min_gold_borders: int
    min_bright_ratio_for_skill: float


# 現在の card_crop.py の値
CURRENT_PARAMS = Params(
    row_gradient_threshold=10,
    min_gap_between_edges=5,
    border_min_brightness_threshold=120,
    min_border_span=4,
    min_gold_borders=3,
    min_bright_ratio_for_skill=0.20,
)

# スイープ探索範囲
SWEEP_RANGES = {
    "row_gradient_threshold": [8, 10, 12, 15, 18, 20],
    "min_gap_between_edges": [5, 8, 10, 12, 15],
    "border_min_brightness_threshold": [80, 90, 100, 110, 120],
    "min_border_span": [4, 6, 8, 10, 12],
    "min_gold_borders": [2, 3, 4],
    "min_bright_ratio_for_skill": [0.20, 0.25, 0.30, 0.35],
}


def crop_detect_panel(img: Image.Image) -> Image.Image:
    """DETECT_PANEL_CROP でクロップ"""
    w, h = img.size
    return img.crop((
        int(w * DETECT_PANEL_CROP[0]),
        int(h * DETECT_PANEL_CROP[1]),
        int(w * DETECT_PANEL_CROP[2]),
        int(h * DETECT_PANEL_CROP[3]),
    ))


def find_horizontal_borders_param(
    row_means: np.ndarray,
    p: Params,
) -> int:
    """パラメータ指定版 find_horizontal_borders（ボーダー数のみ返す）

    事前計算済みの row_means を受け取る。
    """
    diffs = np.abs(np.diff(row_means))
    edge_rows = list(np.where(diffs >= p.row_gradient_threshold)[0] + 1)

    if not edge_rows:
        return 0

    # 連続するエッジ行をグルーピング
    groups: list[list[int]] = []
    current_group = [edge_rows[0]]
    for i in range(1, len(edge_rows)):
        if edge_rows[i] - edge_rows[i - 1] <= p.min_gap_between_edges:
            current_group.append(edge_rows[i])
        else:
            groups.append(current_group)
            current_group = [edge_rows[i]]
    groups.append(current_group)

    # 各グループを評価
    border_count = 0
    for group in groups:
        y_min = group[0]
        y_max = group[-1]
        span = y_max - y_min + 1

        if span < p.min_border_span:
            continue

        min_brightness = float(row_means[y_min : y_max + 1].min())
        if min_brightness < p.border_min_brightness_threshold:
            border_count += 1

    return border_count


def is_skill_frame_param(
    bright_ratio: float,
    border_count: int,
    p: Params,
) -> bool:
    """パラメータ指定版 is_skill_frame"""
    if border_count < p.min_gold_borders:
        return False
    return bright_ratio >= p.min_bright_ratio_for_skill


@dataclass
class FrameData:
    name: str
    lang: str
    label: bool  # None は除外済み
    row_means: np.ndarray
    bright_ratio: float


def load_frames(
    frames_dir: Path,
    labels: dict[str, bool | None],
    lang: str,
) -> list[FrameData]:
    """フレームを読み込み、事前計算データを返す"""
    result = []
    for name, label in sorted(labels.items()):
        if label is None:
            continue
        path = frames_dir / name
        if not path.exists():
            print(f"  {lang}/{name}: ファイルなし、スキップ")
            continue

        img = Image.open(path)
        panel = crop_detect_panel(img)

        gray = panel.convert("L")
        pixels = np.array(gray)
        row_means = pixels.mean(axis=1)

        panel_pixels = np.array(panel)
        avg_brightness = panel_pixels[:, :, :3].mean(axis=2)
        bright_ratio = float(
            (avg_brightness >= BRIGHT_PIXEL_THRESHOLD).sum() / avg_brightness.size
        )

        result.append(FrameData(
            name=name,
            lang=lang,
            label=label,
            row_means=row_means,
            bright_ratio=bright_ratio,
        ))
    return result


def evaluate(frames: list[FrameData], p: Params) -> tuple[int, int]:
    """パラメータでの正答数と総数を返す"""
    correct = 0
    total = len(frames)
    for f in frames:
        border_count = find_horizontal_borders_param(f.row_means, p)
        predicted = is_skill_frame_param(f.bright_ratio, border_count, p)
        if predicted == f.label:
            correct += 1
    return correct, total


def evaluate_asymmetric(
    frames: list[FrameData],
    p: Params,
    fn_penalty: int = 3,
    fp_penalty: int = 1,
    correct_bonus: int = 1,
) -> tuple[int, int, int]:
    """非対称スコアリングで評価

    偽陰性（スキル画面の見逃し）は重いペナルティ、
    偽陽性（非スキル画面の誤検出）は軽いペナルティ。

    Returns:
        (score, false_negatives, false_positives)
    """
    score = 0
    fn_count = 0
    fp_count = 0
    for f in frames:
        border_count = find_horizontal_borders_param(f.row_means, p)
        predicted = is_skill_frame_param(f.bright_ratio, border_count, p)
        if predicted == f.label:
            score += correct_bonus
        elif f.label and not predicted:
            # 偽陰性: スキル画面を見逃し
            score -= fn_penalty
            fn_count += 1
        else:
            # 偽陽性: 非スキル画面を誤検出
            score -= fp_penalty
            fp_count += 1
    return score, fn_count, fp_count


def print_detail(frames: list[FrameData], p: Params, title: str) -> None:
    """パラメータでのフレームごと詳細を表示"""
    print(f"\n--- {title} ---")
    print(
        f"{'Lang':<5} {'Frame':<20} {'Label':>6} {'Borders':>8} "
        f"{'BrightR':>8} {'Pred':>6} {'Match':>6}"
    )
    print("-" * 70)
    for f in frames:
        border_count = find_horizontal_borders_param(f.row_means, p)
        predicted = is_skill_frame_param(f.bright_ratio, border_count, p)
        label_str = "skill" if f.label else "other"
        pred_str = "○" if predicted else "×"
        match_str = "✓" if predicted == f.label else "✗"
        print(
            f"{f.lang:<5} {f.name:<20} {label_str:>6} {border_count:>8} "
            f"{f.bright_ratio:>7.1%} {pred_str:>6} {match_str:>6}"
        )


def main() -> None:
    data_dir = Path(__file__).parent.parent / "data" / "10-03-06"
    labels_path = data_dir / "annotations" / "frame_labels.json"
    jp_dir = data_dir / "images" / "jp"
    en_dir = data_dir / "images" / "en"

    if not labels_path.exists():
        print(f"ラベルファイルが見つかりません: {labels_path}")
        return
    if not jp_dir.exists() and not en_dir.exists():
        print(f"フレーム画像が見つかりません: {data_dir / 'images'}")
        return

    jp_labels, en_labels = load_labels_from_json(labels_path)

    # フレーム読み込み
    print("フレーム読み込み中...")
    frames: list[FrameData] = []
    if jp_dir.exists():
        frames.extend(load_frames(jp_dir, jp_labels, "JP"))
    if en_dir.exists():
        frames.extend(load_frames(en_dir, en_labels, "EN"))

    total = len(frames)
    print(f"  {total} フレーム読み込み完了")

    # 現在のパラメータで評価
    current_correct, _ = evaluate(frames, CURRENT_PARAMS)
    print(f"\n現在のパラメータ: 正答 {current_correct}/{total} ({current_correct/total:.1%})")
    print_detail(frames, CURRENT_PARAMS, "現在のパラメータでの詳細")

    # グリッドサーチ
    keys = list(SWEEP_RANGES.keys())
    values = [SWEEP_RANGES[k] for k in keys]
    combos = list(itertools.product(*values))
    print(f"\nグリッドサーチ開始: {len(combos)} 組み合わせ")

    start = time.time()
    results: list[tuple[int, Params]] = []

    for combo in combos:
        p = Params(**dict(zip(keys, combo)))
        correct, _ = evaluate(frames, p)
        results.append((correct, p))

    elapsed = time.time() - start
    print(f"  完了: {elapsed:.1f}秒")

    # Top 5
    results.sort(key=lambda x: x[0], reverse=True)
    print(f"\n{'=' * 90}")
    print(" Top 5 パラメータ組み合わせ")
    print(f"{'=' * 90}")
    print(
        f"{'Rank':>4} {'Score':>7} {'Grad':>5} {'Gap':>5} {'BrThr':>6} "
        f"{'Span':>5} {'Gold':>5} {'BrRat':>6}"
    )
    print("-" * 50)

    for rank, (score, p) in enumerate(results[:5], 1):
        print(
            f"{rank:>4} {score:>4}/{total:<2} "
            f"{p.row_gradient_threshold:>5} {p.min_gap_between_edges:>5} "
            f"{p.border_min_brightness_threshold:>6} {p.min_border_span:>5} "
            f"{p.min_gold_borders:>5} {p.min_bright_ratio_for_skill:>5.2f}"
        )

    best_score, best_params = results[0]
    print(f"\n最良パラメータ: 正答 {best_score}/{total} ({best_score/total:.1%})")
    print(f"  ROW_GRADIENT_THRESHOLD      = {best_params.row_gradient_threshold}")
    print(f"  MIN_GAP_BETWEEN_EDGES       = {best_params.min_gap_between_edges}")
    print(f"  BORDER_MIN_BRIGHTNESS_THRESHOLD = {best_params.border_min_brightness_threshold}")
    print(f"  MIN_BORDER_SPAN             = {best_params.min_border_span}")
    print(f"  MIN_GOLD_BORDERS            = {best_params.min_gold_borders}")
    print(f"  MIN_BRIGHT_RATIO_FOR_SKILL  = {best_params.min_bright_ratio_for_skill}")

    # 改善があれば詳細表示
    if best_score > current_correct:
        print(f"\n改善: {current_correct}/{total} → {best_score}/{total} (+{best_score - current_correct})")
        print_detail(frames, best_params, "最良パラメータでの詳細")
    elif best_score == current_correct:
        print("\n現在のパラメータと同等（改善なし）")
        # 現在のパラメータと異なる場合は詳細表示
        if best_params != CURRENT_PARAMS:
            print_detail(frames, best_params, "最良パラメータでの詳細")
    else:
        print("\n注意: 現在のパラメータが最良")

    # --- 非対称評価 ---
    print(f"\n{'=' * 90}")
    print(" 非対称評価（偽陰性ペナルティ=3, 偽陽性ペナルティ=1, 正答ボーナス=1）")
    print(f"{'=' * 90}")

    # 現在のパラメータで非対称スコア
    cur_asym_score, cur_fn, cur_fp = evaluate_asymmetric(frames, CURRENT_PARAMS)
    print(f"現在のパラメータ: スコア={cur_asym_score}, FN={cur_fn}, FP={cur_fp}")

    # グリッドサーチ（非対称）
    asym_results: list[tuple[int, int, int, int, Params]] = []
    for combo in combos:
        p = Params(**dict(zip(keys, combo)))
        correct, _ = evaluate(frames, p)
        asym_score, fn, fp = evaluate_asymmetric(frames, p)
        asym_results.append((asym_score, correct, fn, fp, p))

    # FN=0 制約で正答率が最も高いパラメータを探索
    zero_fn_results = [(correct, asym, fn, fp, p) for asym, correct, fn, fp, p in asym_results if fn == 0]

    if zero_fn_results:
        zero_fn_results.sort(key=lambda x: x[0], reverse=True)
        print(f"\nFN=0 制約付き Top 5（{len(zero_fn_results)}件中）:")
        print(
            f"{'Rank':>4} {'Score':>7} {'AsymS':>6} {'FN':>3} {'FP':>3} "
            f"{'Grad':>5} {'Gap':>5} {'BrThr':>6} {'Span':>5} {'Gold':>5} {'BrRat':>6}"
        )
        print("-" * 70)
        for rank, (correct, asym, fn, fp, p) in enumerate(zero_fn_results[:5], 1):
            print(
                f"{rank:>4} {correct:>4}/{total:<2} {asym:>6} {fn:>3} {fp:>3} "
                f"{p.row_gradient_threshold:>5} {p.min_gap_between_edges:>5} "
                f"{p.border_min_brightness_threshold:>6} {p.min_border_span:>5} "
                f"{p.min_gold_borders:>5} {p.min_bright_ratio_for_skill:>5.2f}"
            )

        best_zfn_correct, _, _, best_zfn_fp, best_zfn_params = zero_fn_results[0]
        print(f"\nFN=0最良: 正答 {best_zfn_correct}/{total} ({best_zfn_correct/total:.1%}), FP={best_zfn_fp}")
        print(f"  ROW_GRADIENT_THRESHOLD      = {best_zfn_params.row_gradient_threshold}")
        print(f"  MIN_GAP_BETWEEN_EDGES       = {best_zfn_params.min_gap_between_edges}")
        print(f"  BORDER_MIN_BRIGHTNESS_THRESHOLD = {best_zfn_params.border_min_brightness_threshold}")
        print(f"  MIN_BORDER_SPAN             = {best_zfn_params.min_border_span}")
        print(f"  MIN_GOLD_BORDERS            = {best_zfn_params.min_gold_borders}")
        print(f"  MIN_BRIGHT_RATIO_FOR_SKILL  = {best_zfn_params.min_bright_ratio_for_skill}")

        # 対称最良と比較
        if best_zfn_params == best_params:
            print("\n→ 対称評価の最良パラメータと同一")
        else:
            print(f"\n→ 対称最良との差分:")
            for field in ["row_gradient_threshold", "min_gap_between_edges",
                          "border_min_brightness_threshold", "min_border_span",
                          "min_gold_borders", "min_bright_ratio_for_skill"]:
                v_sym = getattr(best_params, field)
                v_asym = getattr(best_zfn_params, field)
                if v_sym != v_asym:
                    print(f"    {field}: {v_sym} → {v_asym}")

        print_detail(frames, best_zfn_params, "FN=0最良パラメータでの詳細")
    else:
        print("\nFN=0 を達成するパラメータが見つかりません")

    # 非対称スコア最大のパラメータ
    asym_results.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_asym_score, best_asym_correct, best_asym_fn, best_asym_fp, _ = asym_results[0]
    print(f"\n非対称スコア最良: スコア={best_asym_score}, 正答={best_asym_correct}/{total}, FN={best_asym_fn}, FP={best_asym_fp}")


if __name__ == "__main__":
    main()
