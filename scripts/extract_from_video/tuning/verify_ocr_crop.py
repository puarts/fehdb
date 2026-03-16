"""クロップ効果検証スクリプト

card_crop.py によるスキルカード個別クロップがOCR精度を改善しているか検証する。
.work/10-03-06/ の既存フレーム画像を使い、「クロップあり」と「クロップなし」の
2モードでOCRを実行し、正解ファイルとの一致率を比較する。
"""

import argparse
import copy
import difflib
import re
import sys
from pathlib import Path

# scripts/extract_from_video をモジュール検索パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from card_crop import crop_frame_groups
from formatter import TEXT_REPLACEMENTS, format_output
from frames import deduplicate_frames, detect_skill_frames
from models import FrameGroup
from ocr import create_backend


# === 正解ファイルパーサ ===


def parse_ground_truth(path: Path) -> list[dict]:
    """正解ファイルをパースしてスキルブロックのリストを返す

    Returns:
        list of dict with keys: id, name, metadata_lines, description
    """
    text = path.read_text(encoding="utf-8")
    blocks = text.strip().split("\n\n")
    skills = []
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        # 1行目: ID-錬成タイプ-JP名[-EN名]
        header = lines[0]
        parts = header.split("-", 3)
        skill_id = int(parts[0])
        jp_name = parts[2] if len(parts) >= 3 else ""

        # メタデータ行と説明文を分離
        metadata_lines = []
        desc_lines = []
        for line in lines[1:]:
            if line.startswith("##"):
                metadata_lines.append(line)
            else:
                desc_lines.append(line)

        description = "\n".join(desc_lines)

        skills.append({
            "id": skill_id,
            "name": jp_name,
            "metadata_lines": metadata_lines,
            "description": description,
        })

    return skills


def normalize_text(text: str) -> str:
    """比較用にテキストを正規化"""
    for search, replace in TEXT_REPLACEMENTS:
        text = text.replace(search, replace)
    # 空白除去
    text = re.sub(r'\s+', '', text)
    return text


# === OCR結果パーサ ===


def parse_ocr_result(path: Path) -> list[dict]:
    """format_output() の出力をパースしてスキルブロックのリストを返す"""
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    blocks = text.strip().split("\n\n")
    skills = []
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        header = lines[0]
        # "# TODO" コメントを除去
        header = re.sub(r'\s*#\s*TODO.*$', '', header)
        parts = header.split("-", 3)
        jp_name = parts[2] if len(parts) >= 3 else ""

        metadata_lines = []
        desc_lines = []
        for line in lines[1:]:
            if line.startswith("##"):
                metadata_lines.append(line)
            else:
                desc_lines.append(line)

        description = "\n".join(desc_lines)

        skills.append({
            "name": jp_name,
            "metadata_lines": metadata_lines,
            "description": description,
        })

    return skills


# === 比較 ===


def compare_skills(gt_skills: list[dict], ocr_skills: list[dict], label: str) -> dict:
    """正解とOCR結果を比較してレポートデータを返す"""
    results = {
        "label": label,
        "gt_count": len(gt_skills),
        "ocr_count": len(ocr_skills),
        "name_matches": 0,
        "meta_matches": 0,
        "desc_similarities": [],
        "details": [],
    }

    # 名前ベースでマッチング（順序も考慮）
    matched_pairs = _match_skills(gt_skills, ocr_skills)

    for gt, ocr in matched_pairs:
        detail = {"id": gt["id"], "name": gt["name"]}

        # 名前比較
        name_match = normalize_text(gt["name"]) == normalize_text(ocr["name"])
        detail["name_match"] = name_match
        if name_match:
            results["name_matches"] += 1

        # メタデータ比較
        gt_meta = "\n".join(gt["metadata_lines"])
        ocr_meta = "\n".join(ocr["metadata_lines"])
        # 正規化: スペースの揺れを吸収 (": " vs "：")
        meta_match = normalize_text(gt_meta) == normalize_text(ocr_meta)
        detail["meta_match"] = meta_match
        if meta_match:
            results["meta_matches"] += 1

        # 説明文類似度
        gt_desc = normalize_text(gt["description"])
        ocr_desc = normalize_text(ocr["description"])
        similarity = difflib.SequenceMatcher(None, gt_desc, ocr_desc).ratio() * 100
        detail["desc_similarity"] = similarity
        results["desc_similarities"].append(similarity)

        # 差分（不一致時のみ）
        if similarity < 100.0:
            diff = list(difflib.unified_diff(
                gt["description"].split("\n"),
                ocr["description"].split("\n"),
                fromfile="正解",
                tofile=label,
                lineterm="",
            ))
            detail["diff"] = diff
        else:
            detail["diff"] = []

        results["details"].append(detail)

    # マッチしなかったOCRスキル
    matched_ocr_indices = {id(ocr) for _, ocr in matched_pairs}
    unmatched = [s for s in ocr_skills if id(s) not in matched_ocr_indices]
    results["unmatched_ocr"] = [s["name"] for s in unmatched]

    return results


def _match_skills(gt_skills: list[dict], ocr_skills: list[dict]) -> list[tuple[dict, dict]]:
    """正解とOCR結果を名前ベースでマッチング"""
    pairs = []
    used_ocr = set()

    for gt in gt_skills:
        gt_norm = normalize_text(gt["name"])
        best_idx = None
        best_sim = 0.0

        for i, ocr in enumerate(ocr_skills):
            if i in used_ocr:
                continue
            ocr_norm = normalize_text(ocr["name"])
            sim = difflib.SequenceMatcher(None, gt_norm, ocr_norm).ratio()
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_idx is not None and best_sim > 0.3:
            pairs.append((gt, ocr_skills[best_idx]))
            used_ocr.add(best_idx)

    return pairs


# === レポート出力 ===


def print_report(gt_skills: list[dict], crop_result: dict | None, nocrop_result: dict | None):
    """比較レポートを出力"""
    print("=== クロップ効果検証レポート ===")
    gt_count = len(gt_skills)
    id_range = f"{gt_skills[0]['id']}-{gt_skills[-1]['id']}" if gt_skills else "N/A"
    print(f"正解: {gt_count}スキル (ID {id_range})")
    print()

    # 検出数
    print("--- 検出数 ---")
    header = f"{'':14s}{'正解':>8s}"
    if crop_result:
        header += f"{'Crop':>10s}"
    if nocrop_result:
        header += f"{'NoCrop':>10s}"
    print(header)

    row = f"{'スキル数:':14s}{gt_count:>8d}"
    if crop_result:
        row += f"{crop_result['ocr_count']:>10d}"
    if nocrop_result:
        row += f"{nocrop_result['ocr_count']:>10d}"
    print(row)
    print()

    # スキル別比較
    print("--- スキル別比較 ---")
    for gt in gt_skills:
        sid = gt["id"]
        print(f"#{sid} {gt['name']}")

        crop_detail = _find_detail(crop_result, sid) if crop_result else None
        nocrop_detail = _find_detail(nocrop_result, sid) if nocrop_result else None

        # 名前
        parts = ["  名前: "]
        if crop_detail:
            mark = "✓" if crop_detail["name_match"] else "✗"
            parts.append(f"crop={mark}")
        if nocrop_detail:
            mark = "✓" if nocrop_detail["name_match"] else "✗"
            parts.append(f"  nocrop={mark}")
        print("".join(parts))

        # メタ
        parts = ["  メタ: "]
        if crop_detail:
            mark = "✓" if crop_detail["meta_match"] else "✗"
            parts.append(f"crop={mark}")
        if nocrop_detail:
            mark = "✓" if nocrop_detail["meta_match"] else "✗"
            parts.append(f"  nocrop={mark}")
        print("".join(parts))

        # 説明文
        parts = ["  説明: "]
        if crop_detail:
            parts.append(f"crop={crop_detail['desc_similarity']:.1f}%")
        if nocrop_detail:
            parts.append(f"  nocrop={nocrop_detail['desc_similarity']:.1f}%")
        print("".join(parts))

        # 差分表示（類似度100%未満のもの）
        for label, detail in [("crop", crop_detail), ("nocrop", nocrop_detail)]:
            if detail and detail["diff"]:
                print(f"  [{label} diff]:")
                for line in detail["diff"]:
                    print(f"    {line}")

        print()

    # 集計
    print("--- 集計 ---")
    header = f"{'':14s}"
    if crop_result:
        header += f"{'Crop':>14s}"
    if nocrop_result:
        header += f"{'NoCrop':>14s}"
    print(header)

    # 名前一致
    row = f"{'名前一致:':14s}"
    if crop_result:
        s = f"{crop_result['name_matches']}/{len(crop_result['details'])}"
        row += f"{s:>14s}"
    if nocrop_result:
        s = f"{nocrop_result['name_matches']}/{len(nocrop_result['details'])}"
        row += f"{s:>14s}"
    print(row)

    # メタ一致
    row = f"{'メタ一致:':14s}"
    if crop_result:
        s = f"{crop_result['meta_matches']}/{len(crop_result['details'])}"
        row += f"{s:>14s}"
    if nocrop_result:
        s = f"{nocrop_result['meta_matches']}/{len(nocrop_result['details'])}"
        row += f"{s:>14s}"
    print(row)

    # 説明文類似度
    row = f"{'説明類似度:':14s}"
    if crop_result and crop_result["desc_similarities"]:
        avg = sum(crop_result["desc_similarities"]) / len(crop_result["desc_similarities"])
        row += f"{avg:>13.1f}%"
    if nocrop_result and nocrop_result["desc_similarities"]:
        avg = sum(nocrop_result["desc_similarities"]) / len(nocrop_result["desc_similarities"])
        row += f"{avg:>13.1f}%"
    print(row)

    # マッチなしスキル
    for result in [crop_result, nocrop_result]:
        if result and result["unmatched_ocr"]:
            print(f"\n  [{result['label']}] マッチなし: {', '.join(result['unmatched_ocr'])}")


def _find_detail(result: dict | None, skill_id: int) -> dict | None:
    if result is None:
        return None
    for d in result["details"]:
        if d["id"] == skill_id:
            return d
    return None


# === メイン処理 ===


def run_ocr_mode(
    frame_groups: list[FrameGroup],
    output_dir: Path,
    start_id: int,
    use_crop: bool,
    label: str,
    ocr_backend: str = "claude",
) -> Path:
    """OCRを実行して結果ファイルを保存"""
    if use_crop:
        crop_output = output_dir / "cards"
        crop_output.mkdir(parents=True, exist_ok=True)
        crop_frame_groups(frame_groups, str(crop_output))

    backend = create_backend(ocr_backend)
    jp_skills = backend.ocr_jp_skills(frame_groups, new_only=True)
    print(f"[{label}] OCR結果: {len(jp_skills)}スキル検出")

    content = format_output(jp_skills, None, start_id=start_id)

    result_path = output_dir / "ocr_result.txt"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(content, encoding="utf-8")
    print(f"[{label}] 保存: {result_path}")

    return result_path


def main():
    parser = argparse.ArgumentParser(description="クロップ効果検証")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".work/10-03-06"),
        help="テストデータパス (default: .work/10-03-06)",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=None,
        help="正解ファイルパス (default: data/10-03-06/annotations/ocr_ground_truth.txt)",
    )
    parser.add_argument("--start-id", type=int, default=3581, help="開始ID (default: 3581)")
    parser.add_argument("--crop-only", action="store_true", help="クロップありのみ実行")
    parser.add_argument("--nocrop-only", action="store_true", help="クロップなしのみ実行")
    parser.add_argument("--skip-ocr", action="store_true", help="OCRスキップ、保存済み結果で再比較")
    parser.add_argument("--ocr", default="claude", choices=["claude", "gemini", "ollama"], help="OCRバックエンド (default: claude)")
    args = parser.parse_args()

    # パス解決
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = args.data_dir if args.data_dir.is_absolute() else base_dir / args.data_dir
    if args.ground_truth:
        gt_path = args.ground_truth
    else:
        # data/ 内の正解データを優先、なければ sources/skill-desc/ にフォールバック
        gt_path = base_dir / "data" / "10-03-06" / "annotations" / "ocr_ground_truth.txt"
        if not gt_path.exists():
            gt_path = base_dir.parent.parent / "sources" / "skill-desc" / "10-03-06.txt"

    if not gt_path.exists():
        print(f"エラー: 正解ファイルが見つかりません: {gt_path}", file=sys.stderr)
        sys.exit(1)

    # 正解パース
    gt_skills = parse_ground_truth(gt_path)
    print(f"正解ファイル: {gt_path} ({len(gt_skills)}スキル)")

    run_crop = not args.nocrop_only
    run_nocrop = not args.crop_only

    crop_dir = data_dir / "verify_crop"
    nocrop_dir = data_dir / "verify_nocrop"

    if not args.skip_ocr:
        # フレーム読み込み + FrameGroup構築
        frames_dir = data_dir / "frames" / "jp"
        frame_paths = sorted(str(p) for p in frames_dir.glob("frame_*.png"))
        if not frame_paths:
            print(f"エラー: フレームが見つかりません: {frames_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"フレーム数: {len(frame_paths)}")

        skill_frames = detect_skill_frames(frame_paths)
        print(f"スキル画面: {len(skill_frames)}")

        base_groups = deduplicate_frames(skill_frames)
        print(f"FrameGroup数: {len(base_groups)}")

        # OCR実行
        if run_crop:
            print("\n--- Run A: クロップあり ---")
            groups_crop = copy.deepcopy(base_groups)
            run_ocr_mode(groups_crop, crop_dir, args.start_id, use_crop=True, label="crop", ocr_backend=args.ocr)

        if run_nocrop:
            print("\n--- Run B: クロップなし ---")
            groups_nocrop = copy.deepcopy(base_groups)
            run_ocr_mode(groups_nocrop, nocrop_dir, args.start_id, use_crop=False, label="nocrop", ocr_backend=args.ocr)
    else:
        print("OCRスキップ: 保存済み結果を使用")

    # 比較
    print("\n")
    crop_result = None
    nocrop_result = None

    if run_crop:
        crop_ocr_path = crop_dir / "ocr_result.txt"
        if crop_ocr_path.exists():
            crop_ocr = parse_ocr_result(crop_ocr_path)
            crop_result = compare_skills(gt_skills, crop_ocr, "Crop")
        else:
            print(f"警告: crop結果が見つかりません: {crop_ocr_path}", file=sys.stderr)

    if run_nocrop:
        nocrop_ocr_path = nocrop_dir / "ocr_result.txt"
        if nocrop_ocr_path.exists():
            nocrop_ocr = parse_ocr_result(nocrop_ocr_path)
            nocrop_result = compare_skills(gt_skills, nocrop_ocr, "NoCrop")
        else:
            print(f"警告: nocrop結果が見つかりません: {nocrop_ocr_path}", file=sys.stderr)

    if crop_result or nocrop_result:
        print_report(gt_skills, crop_result, nocrop_result)
    else:
        print("比較対象がありません。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
