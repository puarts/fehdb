"""武器種テンプレートマッチングの検証スクリプト

ラベル済み7動画のhero_introフレームに対して武器種検出の精度を検証する。
差分法（loose - strict）で抽出した候補フレームに武器種テンプレートマッチングを行い、
英雄紹介フレームの検出精度（hero intro detection）を評価する。

使用法:
    cd scripts/extract_from_video
    uv run python tuning/verify_weapon_detection.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weapon_type import detect_weapon_type, get_weapon_code, DETECTION_THRESHOLD

# 対象セッション
SESSIONS = [
    "10-03-06",
    "10-02-27",
    "09-01-06",
    "09-05-07",
    "09-09-16",
    "09-10-17",
    "10-02-16",
]


def load_hero_frames(base_dir: Path, session: str) -> dict[str, dict]:
    """hero_frame_labels.jsonからhero_introフレーム情報を読み込む"""
    labels_path = base_dir / "data" / session / "annotations" / "hero_frame_labels.json"
    if not labels_path.exists():
        return {}

    with open(labels_path) as f:
        data = json.load(f)

    hero_frames = {}
    for fname, info in data["frames"].items():
        if info["label"] == "hero_intro":
            hero_frames[fname] = info

    return hero_frames


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent

    print("=" * 70)
    print("武器種テンプレートマッチング検証")
    print(f"検出閾値: {DETECTION_THRESHOLD}")
    print("=" * 70)

    total_hero = 0
    total_detected = 0
    total_non_hero = 0
    total_fp = 0

    for session in SESSIONS:
        hero_frames = load_hero_frames(base_dir, session)
        all_frames_dir = base_dir / "data" / session / "all_frames"

        if not all_frames_dir.exists():
            print(f"\n{session}: all_frames/ なし、スキップ")
            continue

        labels_path = base_dir / "data" / session / "annotations" / "hero_frame_labels.json"
        with open(labels_path) as f:
            all_labels = json.load(f)

        print(f"\n{'=' * 60}")
        print(f"セッション: {session} (hero_intro={len(hero_frames)})")
        print(f"{'=' * 60}")

        session_hero = 0
        session_detected = 0
        session_non_hero = 0
        session_fp = 0

        for fname, info in all_labels["frames"].items():
            frame_path = str(all_frames_dir / fname)
            if not os.path.exists(frame_path):
                continue

            is_hero = info["label"] == "hero_intro"
            weapon = detect_weapon_type(frame_path)

            if is_hero:
                session_hero += 1
                hero_name = info.get("hero_name", "?")

                if weapon:
                    session_detected += 1
                    code = get_weapon_code(weapon)
                    print(f"  ✓ {hero_name:12s} → {weapon} (code={code})")
                else:
                    print(f"  ✗ {hero_name:12s} → NOT DETECTED (FN)")
            else:
                session_non_hero += 1
                if weapon:
                    session_fp += 1
                    if session_fp <= 5:  # 最初の5件のみ表示
                        print(f"  FP {fname}: {weapon}")

        recall = session_detected / session_hero * 100 if session_hero else 0
        fp_rate = session_fp / session_non_hero * 100 if session_non_hero else 0

        print(f"\n  Hero: {session_detected}/{session_hero} 検出 (recall={recall:.0f}%)")
        print(f"  FP: {session_fp}/{session_non_hero} (FP rate={fp_rate:.1f}%)")

        total_hero += session_hero
        total_detected += session_detected
        total_non_hero += session_non_hero
        total_fp += session_fp

    # 全体結果
    overall_recall = total_detected / total_hero * 100 if total_hero else 0
    overall_fp_rate = total_fp / total_non_hero * 100 if total_non_hero else 0

    print(f"\n{'=' * 70}")
    print("全体結果")
    print(f"{'=' * 70}")
    print(f"  Hero intro 検出: {total_detected}/{total_hero} (recall={overall_recall:.1f}%)")
    print(f"  False Positive: {total_fp}/{total_non_hero} (FP rate={overall_fp_rate:.1f}%)")
    print(f"  FN（見逃し）: {total_hero - total_detected}")


if __name__ == "__main__":
    main()
