"""スキルカード個別クロップモジュール

スキル一覧画面から金色ボーダーを検出し、個別のスキルカードをクロップする。
「！」マーク誤判定問題（docs/issues/exclamation-mark-detection.md）の解決策。

OpenCVではなくPIL+numpyで実装。
"""

from pathlib import Path

import numpy as np
from PIL import Image

from models import FrameGroup, SkillCard

# ボーダー検出用の狭い領域（テキストノイズが少ない）
DETECT_PANEL_CROP = (0.45, 0.05, 0.98, 0.95)
# クロップ出力用の広い領域（スキル名・アイコンを含む）
OUTPUT_PANEL_CROP = (0.03, 0.05, 0.98, 0.95)

# ボーダー検出パラメータ（tuning/verify_card_crop.py のグリッドサーチで最適化）
ROW_GRADIENT_THRESHOLD = 10
MIN_GAP_BETWEEN_EDGES = 5
BORDER_MIN_BRIGHTNESS_THRESHOLD = 120  # グループ内最小輝度がこれ未満→金色ボーダー
MIN_BORDER_SPAN = 4  # ボーダーと判定する最小エッジグループ幅（ピクセル行数）
BORDER_PADDING = 5  # クロップ時にボーダー線を除外するパディング
MIN_ROW_HEIGHT = 30  # クロップ行の最小高さ（これ未満は無視）

# スキル画面判定
BRIGHT_PIXEL_THRESHOLD = 200
MIN_BRIGHT_RATIO_FOR_SKILL = 0.20
MIN_GOLD_BORDERS = 3  # 最低3本（2スキル以上の一覧画面）


def find_horizontal_borders(panel: Image.Image) -> list[int]:
    """パネル画像から金色ボーダーのY座標（中心）を返す

    Returns:
        金色ボーダーの中心Y座標のリスト（上から順）
    """
    gray = panel.convert("L")
    pixels = np.array(gray)

    row_means = pixels.mean(axis=1)

    diffs = np.abs(np.diff(row_means))
    edge_rows = list(np.where(diffs >= ROW_GRADIENT_THRESHOLD)[0] + 1)

    if not edge_rows:
        return []

    # 連続するエッジ行をグルーピング
    groups: list[list[int]] = []
    current_group = [edge_rows[0]]
    for i in range(1, len(edge_rows)):
        if edge_rows[i] - edge_rows[i - 1] <= MIN_GAP_BETWEEN_EDGES:
            current_group.append(edge_rows[i])
        else:
            groups.append(current_group)
            current_group = [edge_rows[i]]
    groups.append(current_group)

    # 各グループを評価: min_brightness < 100 AND span >= 8 → 金色ボーダー
    border_ys = []
    for group in groups:
        y_min = group[0]
        y_max = group[-1]
        span = y_max - y_min + 1

        if span < MIN_BORDER_SPAN:
            continue

        min_brightness = float(row_means[y_min : y_max + 1].min())

        if min_brightness < BORDER_MIN_BRIGHTNESS_THRESHOLD:
            center_y = (y_min + y_max) // 2
            border_ys.append(center_y)

    return border_ys


def crop_skill_rows(
    panel: Image.Image,
    border_ys: list[int],
    padding: int = BORDER_PADDING,
) -> list[Image.Image]:
    """連続するボーダー間をクロップしてスキル行画像のリストを返す"""
    if len(border_ys) < 2:
        return []

    width, height = panel.size
    rows = []

    for i in range(len(border_ys) - 1):
        top = border_ys[i] + padding
        bottom = border_ys[i + 1] - padding

        row_height = bottom - top
        if row_height < MIN_ROW_HEIGHT:
            continue

        top = max(0, top)
        bottom = min(height, bottom)

        row_img = panel.crop((0, top, width, bottom))
        rows.append(row_img)

    return rows


def _crop_region(
    img: Image.Image,
    ratios: tuple[float, float, float, float],
) -> Image.Image:
    """比率指定で画像をクロップ"""
    w, h = img.size
    return img.crop((
        int(w * ratios[0]),
        int(h * ratios[1]),
        int(w * ratios[2]),
        int(h * ratios[3]),
    ))


def process_frame(
    frame_path: str | Path,
) -> tuple[list[Image.Image], list[int]]:
    """フレーム画像からスキル行をクロップ

    ボーダー検出は狭い領域（DETECT_PANEL_CROP）で行い、
    クロップ出力は広い領域（OUTPUT_PANEL_CROP）から切り出す。

    Returns:
        (クロップされた行画像のリスト, ボーダーY座標のリスト)
    """
    img = Image.open(frame_path)

    detect_panel = _crop_region(img, DETECT_PANEL_CROP)
    border_ys = find_horizontal_borders(detect_panel)

    output_panel = _crop_region(img, OUTPUT_PANEL_CROP)
    rows = crop_skill_rows(output_panel, border_ys)

    return rows, border_ys


def is_skill_frame(panel: Image.Image, border_count: int) -> bool:
    """パネルがスキル一覧画面かどうかを簡易判定

    金色ボーダー3本以上（2スキル以上）かつ明るいピクセル比率30%以上で判定。
    """
    if border_count < MIN_GOLD_BORDERS:
        return False

    pixels = np.array(panel)
    avg_brightness = pixels[:, :, :3].mean(axis=2)
    bright_ratio = float((avg_brightness >= BRIGHT_PIXEL_THRESHOLD).sum() / avg_brightness.size)
    return bright_ratio >= MIN_BRIGHT_RATIO_FOR_SKILL


def save_cropped_rows(
    rows: list[Image.Image],
    frame_path: str | Path,
    output_dir: str | Path,
) -> list[str]:
    """クロップされた行画像を保存

    Returns:
        保存されたファイルパスのリスト
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    stem = Path(frame_path).stem
    saved = []
    for i, row in enumerate(rows):
        filename = f"{stem}_{i:02d}.png"
        path = out / filename
        row.save(path)
        saved.append(str(path))

    return saved


def crop_frame_groups(
    frame_groups: list[FrameGroup],
    output_dir: str | Path,
) -> None:
    """FrameGroupリストの代表フレームからカードクロップを実行し、
    各グループの skill_cards を設定する（in-place変更）。

    一覧画面でない場合（比翼・響心等の単体画面）は skill_cards を空のままにする。
    """
    output_dir = Path(output_dir)
    cropped_count = 0
    skipped_count = 0

    for group in frame_groups:
        frame_path = group.representative
        img = Image.open(frame_path)

        detect_panel = _crop_region(img, DETECT_PANEL_CROP)
        border_ys = find_horizontal_borders(detect_panel)

        if not is_skill_frame(detect_panel, len(border_ys)):
            skipped_count += 1
            continue

        output_panel = _crop_region(img, OUTPUT_PANEL_CROP)
        rows = crop_skill_rows(output_panel, border_ys)

        if not rows:
            skipped_count += 1
            continue

        saved_paths = save_cropped_rows(rows, frame_path, output_dir)
        group.skill_cards = [
            SkillCard(
                image_path=path,
                card_index=i,
                source_frame=frame_path,
            )
            for i, path in enumerate(saved_paths)
        ]
        cropped_count += len(saved_paths)

    print(f"  カードクロップ: {cropped_count}枚生成、{skipped_count}フレームスキップ（単体画面等）")
