import re
import subprocess
import sys
from pathlib import Path

import imagehash
from PIL import Image, ImageFilter

from models import FrameGroup

# スキルパネル領域のクロップ比率（右側のスキル説明パネル）
# (left_ratio, top_ratio, right_ratio, bottom_ratio)
DEFAULT_SKILL_PANEL_CROP = (0.45, 0.05, 0.98, 0.95)

# スキル名領域（パネル上部）
DEFAULT_SKILL_NAME_CROP = (0.45, 0.05, 0.98, 0.20)

# スキル説明文領域（パネル下部）
DEFAULT_SKILL_DESC_CROP = (0.45, 0.20, 0.98, 0.95)

# 色分析の閾値
DARK_PIXEL_THRESHOLD = 80  # これ以下のRGB平均値を「暗い」とする
BRIGHT_PIXEL_THRESHOLD = 200  # これ以上のRGB平均値を「明るい」とする
MIN_DARK_RATIO = 0.12  # 暗色ピクセルの最低比率（参考値）
MIN_BRIGHT_RATIO = 0.08  # 明色ピクセルの最低比率（テキスト）

# 水平エッジ検出の閾値
ROW_GRADIENT_THRESHOLD = 15  # 隣接行の輝度差がこれ以上でエッジとみなす
MIN_GAP_BETWEEN_EDGES = 10  # エッジ行のグルーピング間隔
MIN_HORIZONTAL_LINES = 7  # スキル画面と判定する最小水平線数

# 重複除去の閾値
HASH_THRESHOLD = 8  # パーセプチュアルハッシュのハミング距離しきい値
SCROLL_NAME_THRESHOLD = 5  # スキル名一致の閾値（低い=一致）
SCROLL_DESC_THRESHOLD = 10  # 説明文差異の閾値（高い=異なる）


def extract_static_frames(
    video_path: str,
    output_dir: str,
    min_duration: float = 1.5,
    noise: float = 0.003,
) -> list[str]:
    """ffmpegのfreezedetectで静止区間を検出し、各区間の中間フレームを抽出

    Args:
        video_path: 動画ファイルのパス
        output_dir: フレーム出力ディレクトリ
        min_duration: 最低静止秒数（これより短い静止区間は無視）
        noise: ノイズ許容値（0〜1、低いほど厳密な静止判定）
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Step 1: freezedetect で静止区間を検出
    print(f"静止区間検出中（{min_duration}秒以上）: {video_path}")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"freezedetect=n={noise}:d={min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    intervals = _parse_freezedetect(result.stderr)
    print(f"静止区間数: {len(intervals)}")

    if not intervals:
        return []

    # Step 2: 各区間の中間時点でフレームを抽出
    frames = []
    for i, (start, end) in enumerate(intervals):
        mid = (start + end) / 2
        output_path = out / f"frame_{i:05d}.png"
        cmd = [
            "ffmpeg", "-ss", str(mid), "-i", video_path,
            "-frames:v", "1", "-q:v", "2",
            str(output_path), "-y",
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        if output_path.exists():
            frames.append(str(output_path))

    print(f"抽出フレーム数: {len(frames)}")
    return frames


def _parse_freezedetect(stderr: str) -> list[tuple[float, float]]:
    """freezedetectの出力から静止区間の(start, end)リストをパース"""
    intervals = []
    current_start = None

    for line in stderr.split("\n"):
        if "freeze_start" in line:
            m = re.search(r"freeze_start:\s*([\d.]+)", line)
            if m:
                current_start = float(m.group(1))
        elif "freeze_end" in line and current_start is not None:
            m = re.search(r"freeze_end:\s*([\d.]+)", line)
            if m:
                intervals.append((current_start, float(m.group(1))))
                current_start = None

    return intervals


def detect_skill_frames(
    frame_paths: list[str],
    crop_ratios: tuple[float, float, float, float] = DEFAULT_SKILL_PANEL_CROP,
) -> list[str]:
    """水平エッジ検出＋色分析でスキル説明画面のフレームを検出"""
    skill_frames = []

    for path in frame_paths:
        img = Image.open(path)
        w, h = img.size

        # スキルパネル領域をクロップ
        left = int(w * crop_ratios[0])
        top = int(h * crop_ratios[1])
        right = int(w * crop_ratios[2])
        bottom = int(h * crop_ratios[3])
        panel = img.crop((left, top, right, bottom))

        _, dark_ratio, bright_ratio = _analyze_skill_panel(panel)
        h_lines = _count_horizontal_edges(panel)
        is_skill = h_lines >= MIN_HORIZONTAL_LINES and bright_ratio >= MIN_BRIGHT_RATIO

        name = Path(path).name
        if is_skill:
            skill_frames.append(path)
            print(f"  {name}: ○ (h_lines={h_lines}, bright={bright_ratio:.1%}, dark={dark_ratio:.1%})")
        else:
            reasons = []
            if h_lines < MIN_HORIZONTAL_LINES:
                reasons.append(f"h_lines={h_lines} < {MIN_HORIZONTAL_LINES}")
            if bright_ratio < MIN_BRIGHT_RATIO:
                reasons.append(f"bright={bright_ratio:.1%} < {MIN_BRIGHT_RATIO:.0%}")
            print(f"  {name}: × スキップ ({', '.join(reasons)})")

    print(f"スキル画面候補（エッジ＋色分析）: {len(skill_frames)}/{len(frame_paths)} フレーム")
    return skill_frames


def _count_horizontal_edges(panel: Image.Image) -> int:
    """パネル画像の水平エッジ（輝度急変行）をカウント

    スキルカードの金色ボーダーはパネル幅全体に渡る強い水平エッジを生成する。
    行ごとの平均輝度の急変をカウントすることでカード数を推定する。
    """
    gray = panel.convert("L")
    width, height = gray.size
    pixels = list(gray.getdata())

    # 各行の平均輝度を計算
    row_means = []
    for y in range(height):
        row = pixels[y * width : (y + 1) * width]
        row_means.append(sum(row) / width)

    # 隣接行との輝度差がしきい値以上の行を「エッジ行」として検出
    edge_rows = [
        y for y in range(1, height)
        if abs(row_means[y] - row_means[y - 1]) >= ROW_GRADIENT_THRESHOLD
    ]

    if not edge_rows:
        return 0

    # 連続するエッジ行をグルーピングして1本の水平線としてカウント
    line_count = 1
    for i in range(1, len(edge_rows)):
        if edge_rows[i] - edge_rows[i - 1] > MIN_GAP_BETWEEN_EDGES:
            line_count += 1

    return line_count


def _analyze_skill_panel(panel: Image.Image) -> tuple[bool, float, float]:
    """クロップされたパネル画像がスキル説明画面かどうかを色分析で判定

    Returns:
        (is_skill, dark_ratio, bright_ratio) のタプル
    """
    pixels = list(panel.getdata())
    total = len(pixels)
    if total == 0:
        return False, 0.0, 0.0

    dark_count = 0
    bright_count = 0

    for pixel in pixels:
        # RGBの場合（アルファチャネルがある場合も対応）
        r, g, b = pixel[0], pixel[1], pixel[2]
        avg = (r + g + b) / 3

        if avg <= DARK_PIXEL_THRESHOLD:
            dark_count += 1
        elif avg >= BRIGHT_PIXEL_THRESHOLD:
            bright_count += 1

    dark_ratio = dark_count / total
    bright_ratio = bright_count / total

    is_skill = dark_ratio >= MIN_DARK_RATIO and bright_ratio >= MIN_BRIGHT_RATIO
    return is_skill, dark_ratio, bright_ratio


def deduplicate_frames(
    frame_paths: list[str],
    crop_ratios: tuple[float, float, float, float] = DEFAULT_SKILL_PANEL_CROP,
    name_crop: tuple[float, float, float, float] = DEFAULT_SKILL_NAME_CROP,
    desc_crop: tuple[float, float, float, float] = DEFAULT_SKILL_DESC_CROP,
) -> list[FrameGroup]:
    """パーセプチュアルハッシュでフレームを重複除去し、FrameGroupのリストを返す"""
    if not frame_paths:
        return []

    # 各フレームのハッシュを計算
    frame_data = []
    for path in frame_paths:
        img = Image.open(path)
        w, h = img.size

        # パネル全体のハッシュ
        panel = img.crop((
            int(w * crop_ratios[0]), int(h * crop_ratios[1]),
            int(w * crop_ratios[2]), int(h * crop_ratios[3]),
        ))
        panel_hash = imagehash.phash(panel)

        # スキル名領域のハッシュ
        name_region = img.crop((
            int(w * name_crop[0]), int(h * name_crop[1]),
            int(w * name_crop[2]), int(h * name_crop[3]),
        ))
        name_hash = imagehash.phash(name_region)

        # 説明文領域のハッシュ
        desc_region = img.crop((
            int(w * desc_crop[0]), int(h * desc_crop[1]),
            int(w * desc_crop[2]), int(h * desc_crop[3]),
        ))
        desc_hash = imagehash.phash(desc_region)

        frame_data.append({
            "path": path,
            "panel_hash": panel_hash,
            "name_hash": name_hash,
            "desc_hash": desc_hash,
        })

    # グループ化
    groups: list[list[dict]] = []
    current_group: list[dict] = [frame_data[0]]

    for i in range(1, len(frame_data)):
        prev = frame_data[i - 1]
        curr = frame_data[i]

        panel_dist = prev["panel_hash"] - curr["panel_hash"]
        name_dist = prev["name_hash"] - curr["name_hash"]

        if panel_dist <= HASH_THRESHOLD:
            # ほぼ同一フレーム → 同グループ
            current_group.append(curr)
        elif name_dist <= SCROLL_NAME_THRESHOLD:
            # スキル名は同じだが内容が違う → スクロール → 同グループに追加
            current_group.append(curr)
        else:
            # 異なるスキル → 新グループ
            groups.append(current_group)
            current_group = [curr]

    groups.append(current_group)

    # 各グループから代表フレームを選択
    result = []
    for idx, group in enumerate(groups):
        # 最もシャープなフレームを代表とする
        best_frame = _select_sharpest(group)

        # スクロール検出：名前一致+説明文異なるフレームを収集
        all_frames = _collect_scroll_frames(group)

        result.append(FrameGroup(
            representative=best_frame,
            all_frames=all_frames,
            frame_index=idx,
        ))

    print(f"重複除去後: {len(result)} グループ（元: {len(frame_paths)} フレーム）")
    return result


def _select_sharpest(group: list[dict]) -> str:
    """グループ内で最もシャープなフレームを返す"""
    best_path = group[0]["path"]
    best_sharpness = -1.0

    for item in group:
        img = Image.open(item["path"]).convert("L")
        # ラプラシアンフィルタの分散でシャープネスを推定
        edges = img.filter(ImageFilter.FIND_EDGES)
        pixels = list(edges.getdata())
        if not pixels:
            continue
        mean = sum(pixels) / len(pixels)
        variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        if variance > best_sharpness:
            best_sharpness = variance
            best_path = item["path"]

    return best_path


def _collect_scroll_frames(group: list[dict]) -> list[str]:
    """グループ内のスクロールフレーム（異なる説明文領域）を収集"""
    if len(group) <= 1:
        return [group[0]["path"]]

    # 説明文ハッシュが異なるフレームを検出
    unique_descs: list[dict] = [group[0]]
    for item in group[1:]:
        is_unique = True
        for existing in unique_descs:
            if existing["desc_hash"] - item["desc_hash"] <= HASH_THRESHOLD:
                is_unique = False
                break
        if is_unique:
            unique_descs.append(item)

    if len(unique_descs) > 1:
        # スクロールがある場合、各ユニークな説明文から最もシャープなフレームを選択
        return [_select_sharpest([d]) for d in unique_descs]
    else:
        return [_select_sharpest(group)]
