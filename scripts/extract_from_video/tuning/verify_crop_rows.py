"""スキル行クロップ検証スクリプト

card_crop.py のロジックを使用して、スキル一覧画面から個別のスキル行をクロップする検証ツール。
"""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from card_crop import (
    DETECT_PANEL_CROP,
    _crop_region,
    find_horizontal_borders,
    is_skill_frame,
    crop_skill_rows,
    save_cropped_rows,
)


def main() -> None:
    base = Path(__file__).parent.parent / ".work" / "gemini-test" / "frames"
    lang_dirs = {
        "jp": base / "jp",
        "en": base / "en",
    }

    found_any = False
    for lang, frames_dir in lang_dirs.items():
        if not frames_dir.exists():
            continue
        found_any = True

        output_dir = base / f"cropped_{lang}"
        print(f"\n{'=' * 70}")
        print(f" {lang.upper()} フレーム処理: {frames_dir}")
        print(f" 出力先: {output_dir}")
        print(f"{'=' * 70}")

        frame_files = sorted(frames_dir.glob("frame_*.png"))
        total_rows = 0

        for frame_path in frame_files:
            img = Image.open(frame_path)
            detect_panel = _crop_region(img, DETECT_PANEL_CROP)

            border_ys = find_horizontal_borders(detect_panel)

            if not is_skill_frame(detect_panel, len(border_ys)):
                print(f"  {frame_path.name}: スキップ（ボーダー数={len(border_ys)}）")
                continue

            output_panel = _crop_region(img, (0.03, 0.05, 0.98, 0.95))
            rows = crop_skill_rows(output_panel, border_ys)
            if not rows:
                print(f"  {frame_path.name}: ボーダー{len(border_ys)}本検出、クロップ行なし")
                continue

            save_cropped_rows(rows, frame_path, output_dir)
            sizes = [f"{r.size[0]}x{r.size[1]}" for r in rows]
            total_rows += len(rows)

            print(
                f"  {frame_path.name}: ボーダー{len(border_ys)}本 → "
                f"{len(rows)}行クロップ [{', '.join(sizes)}]"
            )

        print(f"\n  合計: {total_rows}行クロップ → {output_dir}")

    if not found_any:
        print("フレームが見つかりません: .work/gemini-test/frames/jp/ または en/")
        print("先に main.py --keep-frames で抽出してください")


if __name__ == "__main__":
    main()
