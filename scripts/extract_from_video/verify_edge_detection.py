"""水平エッジ検出の検証スクリプト

全サンプルフレーム（JP 15枚 + EN 18枚）に対して
色分析と水平エッジ検出を実行し、結果を比較する。
"""

from pathlib import Path

from PIL import Image

# frames.py と同じクロップ設定・色閾値
DEFAULT_SKILL_PANEL_CROP = (0.45, 0.05, 0.98, 0.95)
DARK_PIXEL_THRESHOLD = 80
BRIGHT_PIXEL_THRESHOLD = 200
MIN_DARK_RATIO = 0.12
MIN_BRIGHT_RATIO = 0.08

# 水平エッジ検出パラメータ（調整対象）
ROW_GRADIENT_THRESHOLD = 15
MIN_GAP_BETWEEN_EDGES = 5
MIN_HORIZONTAL_LINES = 4

# サンプルフレームの正解ラベル
# True = スキル画面, False = 非スキル画面, None = 境界（双界/スタイル、new_onlyでは[]を返すべき）
JP_LABELS: dict[str, bool | None] = {
    "frame_00000.png": True,   # 習得可能スキルリスト
    "frame_00001.png": True,   # 習得可能スキルリスト
    "frame_00002.png": False,  # 英雄紹介（キャラ説明テキスト）
    "frame_00003.png": None,   # 双界スキル説明
    "frame_00004.png": True,   # 習得可能スキルリスト
    "frame_00005.png": True,   # 習得可能スキルリスト
    "frame_00006.png": True,   # 習得可能スキルリスト
    "frame_00007.png": True,   # 習得可能スキルリスト
    "frame_00008.png": True,   # 習得可能スキルリスト
    "frame_00009.png": None,   # スタイルスキル説明
    "frame_00010.png": False,  # 英雄紹介（スプライト＋テキスト）
    "frame_00011.png": False,  # 英雄能力説明（キャラ絵＋テキスト）
    "frame_00012.png": False,  # ストーリー
    "frame_00013.png": False,  # バナー
    "frame_00014.png": False,  # 召喚
}

EN_LABELS: dict[str, bool | None] = {
    "frame_00000.png": True,   # Skills Learnable list
    "frame_00001.png": True,
    "frame_00002.png": True,
    "frame_00003.png": True,
    "frame_00004.png": True,
    "frame_00005.png": True,
    "frame_00006.png": True,
    "frame_00007.png": True,
    "frame_00008.png": True,
    "frame_00009.png": True,
    "frame_00010.png": True,
    "frame_00011.png": True,
    "frame_00012.png": True,
    "frame_00013.png": None,   # Style skill description
    "frame_00014.png": False,  # Hero introduction
    "frame_00015.png": False,  # Hero ability description
    "frame_00016.png": False,  # Story
    "frame_00017.png": False,  # Banner
}


def analyze_color(panel: Image.Image) -> tuple[float, float]:
    """色分析: (dark_ratio, bright_ratio) を返す"""
    pixels = list(panel.getdata())
    total = len(pixels)
    if total == 0:
        return 0.0, 0.0

    dark_count = 0
    bright_count = 0
    for pixel in pixels:
        r, g, b = pixel[0], pixel[1], pixel[2]
        avg = (r + g + b) / 3
        if avg <= DARK_PIXEL_THRESHOLD:
            dark_count += 1
        elif avg >= BRIGHT_PIXEL_THRESHOLD:
            bright_count += 1

    return dark_count / total, bright_count / total


def count_horizontal_edges(panel: Image.Image) -> int:
    """水平エッジ検出: パネル内の水平線数を返す"""
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


def crop_panel(img: Image.Image) -> Image.Image:
    """スキルパネル領域をクロップ"""
    w, h = img.size
    left = int(w * DEFAULT_SKILL_PANEL_CROP[0])
    top = int(h * DEFAULT_SKILL_PANEL_CROP[1])
    right = int(w * DEFAULT_SKILL_PANEL_CROP[2])
    bottom = int(h * DEFAULT_SKILL_PANEL_CROP[3])
    return img.crop((left, top, right, bottom))


def evaluate_frames(
    frames_dir: Path,
    labels: dict[str, bool | None],
    lang: str,
) -> None:
    """フレームを評価して結果を表示"""
    print(f"\n{'=' * 80}")
    print(f" {lang} フレーム検証")
    print(f"{'=' * 80}")
    print(f"{'Frame':<20} {'Label':>6} {'dark%':>6} {'bright%':>7} {'h_lines':>7} "
          f"{'color':>6} {'edge':>6} {'match':>6}")
    print("-" * 80)

    correct_color = 0
    correct_edge = 0
    total_labeled = 0

    for name in sorted(labels.keys()):
        path = frames_dir / name
        if not path.exists():
            print(f"  {name}: ファイルなし、スキップ")
            continue

        label = labels[name]
        img = Image.open(path)
        panel = crop_panel(img)

        dark_ratio, bright_ratio = analyze_color(panel)
        h_lines = count_horizontal_edges(panel)

        # 色分析の判定（旧ロジック）
        color_pass = dark_ratio >= MIN_DARK_RATIO and bright_ratio >= MIN_BRIGHT_RATIO
        # エッジ検出の判定（新ロジック）
        edge_pass = h_lines >= MIN_HORIZONTAL_LINES and bright_ratio >= MIN_BRIGHT_RATIO

        # ラベルとの比較（None=境界ケースは通過しても除外しても正解）
        label_str = {True: "skill", False: "other", None: "maybe"}[label]
        color_str = "○" if color_pass else "×"
        edge_str = "○" if edge_pass else "×"

        if label is not None:
            total_labeled += 1
            color_correct = (color_pass == label)
            edge_correct = (edge_pass == label)
            if color_correct:
                correct_color += 1
            if edge_correct:
                correct_edge += 1
            match_color = "✓" if color_correct else "✗"
            match_edge = "✓" if edge_correct else "✗"
        else:
            match_color = "-"
            match_edge = "-"

        print(f"{name:<20} {label_str:>6} {dark_ratio:>5.1%} {bright_ratio:>6.1%} "
              f"{h_lines:>7d} {color_str:>6} {edge_str:>6} "
              f"c={match_color} e={match_edge}")

    print("-" * 80)
    print(f"色分析の正答率: {correct_color}/{total_labeled}")
    print(f"エッジ検出の正答率: {correct_edge}/{total_labeled}")


def sweep_thresholds(
    frames_dir: Path,
    labels: dict[str, bool | None],
    lang: str,
) -> None:
    """複数の閾値でエッジ検出精度をスイープ"""
    global ROW_GRADIENT_THRESHOLD, MIN_GAP_BETWEEN_EDGES, MIN_HORIZONTAL_LINES

    # パネル画像を先に読み込み
    panels = {}
    colors = {}
    for name in sorted(labels.keys()):
        path = frames_dir / name
        if not path.exists():
            continue
        img = Image.open(path)
        panel = crop_panel(img)
        panels[name] = panel
        colors[name] = analyze_color(panel)

    print(f"\n{'=' * 90}")
    print(f" {lang} 閾値スイープ")
    print(f"{'=' * 90}")

    best_score = -1
    best_params = (15, 5, 4)

    for grad_thresh in [15, 20, 25, 30, 35, 40]:
        for min_gap in [3, 5, 8]:
            for min_lines in [4, 5, 6, 7, 8]:
                ROW_GRADIENT_THRESHOLD = grad_thresh
                MIN_GAP_BETWEEN_EDGES = min_gap
                MIN_HORIZONTAL_LINES = min_lines

                correct = 0
                total = 0
                for name, label in labels.items():
                    if label is None or name not in panels:
                        continue
                    total += 1
                    h_lines = count_horizontal_edges(panels[name])
                    _, bright_ratio = colors[name]
                    edge_pass = h_lines >= min_lines and bright_ratio >= MIN_BRIGHT_RATIO
                    if edge_pass == label:
                        correct += 1

                if correct > best_score:
                    best_score = correct
                    best_params = (grad_thresh, min_gap, min_lines)

    grad, gap, lines = best_params
    print(f"最良パラメータ: grad={grad}, gap={gap}, min_lines={lines} → 正答 {best_score}/{total}")

    # 最良パラメータで詳細表示
    ROW_GRADIENT_THRESHOLD = grad
    MIN_GAP_BETWEEN_EDGES = gap
    MIN_HORIZONTAL_LINES = lines

    print(f"\n{'Frame':<20} {'Label':>6} {'bright%':>7} {'h_lines':>7} {'pass':>5} {'match':>5}")
    print("-" * 60)
    for name in sorted(labels.keys()):
        if name not in panels:
            continue
        label = labels[name]
        _, bright_ratio = colors[name]
        h_lines = count_horizontal_edges(panels[name])
        edge_pass = h_lines >= lines and bright_ratio >= MIN_BRIGHT_RATIO
        label_str = {True: "skill", False: "other", None: "maybe"}[label]
        pass_str = "○" if edge_pass else "×"
        if label is not None:
            match_str = "✓" if (edge_pass == label) else "✗"
        else:
            match_str = "-"
        print(f"{name:<20} {label_str:>6} {bright_ratio:>6.1%} {h_lines:>7d} {pass_str:>5} {match_str:>5}")


def combined_sweep(
    datasets: list[tuple[Path, dict[str, bool | None], str]],
) -> None:
    """JP+EN合算で最良パラメータを探索"""
    global ROW_GRADIENT_THRESHOLD, MIN_GAP_BETWEEN_EDGES, MIN_HORIZONTAL_LINES

    # パネル画像を先に全部読み込み
    all_panels: list[tuple[Image.Image, float, bool]] = []  # (panel, bright_ratio, label)
    for frames_dir, labels, _ in datasets:
        for name in sorted(labels.keys()):
            label = labels[name]
            if label is None:
                continue
            path = frames_dir / name
            if not path.exists():
                continue
            img = Image.open(path)
            panel = crop_panel(img)
            _, bright_ratio = analyze_color(panel)
            all_panels.append((panel, bright_ratio, label))

    total = len(all_panels)
    print(f"\n{'=' * 90}")
    print(f" 合算閾値スイープ（{total} フレーム）")
    print(f"{'=' * 90}")

    best_score = -1
    best_params = (15, 5, 4)

    for grad_thresh in [10, 12, 15, 18, 20, 25, 30]:
        for min_gap in [3, 5, 8, 10, 12]:
            for min_lines in [4, 5, 6, 7, 8, 9, 10]:
                ROW_GRADIENT_THRESHOLD = grad_thresh
                MIN_GAP_BETWEEN_EDGES = min_gap
                MIN_HORIZONTAL_LINES = min_lines

                correct = 0
                for panel, bright_ratio, label in all_panels:
                    h_lines = count_horizontal_edges(panel)
                    edge_pass = h_lines >= min_lines and bright_ratio >= MIN_BRIGHT_RATIO
                    if edge_pass == label:
                        correct += 1

                if correct > best_score:
                    best_score = correct
                    best_params = (grad_thresh, min_gap, min_lines)

    grad, gap, lines = best_params
    print(f"最良パラメータ: grad={grad}, gap={gap}, min_lines={lines} → 正答 {best_score}/{total}")

    # 最良パラメータで各データセットの詳細表示
    ROW_GRADIENT_THRESHOLD = grad
    MIN_GAP_BETWEEN_EDGES = gap
    MIN_HORIZONTAL_LINES = lines

    for frames_dir, labels, lang in datasets:
        print(f"\n--- {lang} ---")
        print(f"{'Frame':<20} {'Label':>6} {'bright%':>7} {'h_lines':>7} {'pass':>5} {'match':>5}")
        print("-" * 60)
        for name in sorted(labels.keys()):
            path = frames_dir / name
            if not path.exists():
                continue
            label = labels[name]
            img = Image.open(path)
            panel = crop_panel(img)
            _, bright_ratio = analyze_color(panel)
            h_lines = count_horizontal_edges(panel)
            edge_pass = h_lines >= lines and bright_ratio >= MIN_BRIGHT_RATIO
            label_str = {True: "skill", False: "other", None: "maybe"}[label]
            pass_str = "○" if edge_pass else "×"
            if label is not None:
                match_str = "✓" if (edge_pass == label) else "✗"
            else:
                match_str = "-"
            print(f"{name:<20} {label_str:>6} {bright_ratio:>6.1%} {h_lines:>7d} {pass_str:>5} {match_str:>5}")


def main() -> None:
    base = Path(__file__).parent / ".work" / "frames"
    jp_dir = base / "jp"
    en_dir = base / "en"

    if not jp_dir.exists() and not en_dir.exists():
        print("サンプルフレームが見つかりません: .work/frames/jp/ または .work/frames/en/")
        print("先に main.py --frames-only --keep-frames で抽出してください")
        return

    if jp_dir.exists():
        evaluate_frames(jp_dir, JP_LABELS, "JP")
    if en_dir.exists():
        evaluate_frames(en_dir, EN_LABELS, "EN")

    # 合算スイープ
    datasets = []
    if jp_dir.exists():
        datasets.append((jp_dir, JP_LABELS, "JP"))
    if en_dir.exists():
        datasets.append((en_dir, EN_LABELS, "EN"))
    if datasets:
        combined_sweep(datasets)


if __name__ == "__main__":
    main()
