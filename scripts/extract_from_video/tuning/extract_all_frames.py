"""英雄紹介フレーム検出用の正解データ作成支援スクリプト

緩いパラメータで大量にフレームを抽出し、手動ラベル付けの素材を作る。
- ffmpeg freezedetect（緩いnoise設定）
- ffmpeg scene detection（シーン変化時点のフレーム）
両方の結果を統合して出力する。
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frames import _parse_freezedetect

# デフォルト設定（通常より緩い）
DEFAULT_NOISE = 0.05
DEFAULT_MIN_DURATION = 0.5
DEFAULT_SCENE_THRESHOLD = 0.3
TIMESTAMP_MERGE_TOLERANCE = 1.0  # 秒。これ以内のタイムスタンプは統合


def extract_freezedetect_timestamps(
    video_path: str,
    noise: float,
    min_duration: float,
) -> list[dict]:
    """freezedetect で静止区間の中間タイムスタンプを取得"""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"freezedetect=n={noise}:d={min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    intervals = _parse_freezedetect(result.stderr)

    timestamps = []
    for start, end in intervals:
        mid = (start + end) / 2
        timestamps.append({
            "timestamp": round(mid, 3),
            "method": "freezedetect",
            "detail": f"noise={noise}, d={min_duration}, interval=[{start:.3f}, {end:.3f}]",
        })
    return timestamps


def extract_scene_timestamps(
    video_path: str,
    scene_threshold: float,
) -> list[dict]:
    """scene detection でシーン変化時点のタイムスタンプを取得"""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    timestamps = []
    for line in result.stderr.split("\n"):
        if "pts_time:" in line:
            m = re.search(r"pts_time:\s*([\d.]+)", line)
            if m:
                ts = float(m.group(1))
                timestamps.append({
                    "timestamp": round(ts, 3),
                    "method": "scene",
                    "detail": f"threshold={scene_threshold}",
                })
    return timestamps


def merge_timestamps(
    all_timestamps: list[dict],
    tolerance: float = TIMESTAMP_MERGE_TOLERANCE,
) -> list[dict]:
    """近接タイムスタンプを統合（tolerance秒以内は1つにまとめる）"""
    if not all_timestamps:
        return []

    sorted_ts = sorted(all_timestamps, key=lambda x: x["timestamp"])
    merged = [sorted_ts[0]]

    for item in sorted_ts[1:]:
        if item["timestamp"] - merged[-1]["timestamp"] <= tolerance:
            # 近い場合は methods を統合
            prev = merged[-1]
            if "methods" not in prev:
                prev["methods"] = [prev.pop("method")]
                prev["details"] = [prev.pop("detail")]
            prev["methods"].append(item["method"])
            prev["details"].append(item["detail"])
            # タイムスタンプは平均を取る
            n = len(prev["methods"])
            prev["timestamp"] = round(
                (prev["timestamp"] * (n - 1) + item["timestamp"]) / n, 3
            )
        else:
            merged.append(item)

    # 単一メソッドのものも統一フォーマットに
    for item in merged:
        if "methods" not in item:
            item["methods"] = [item.pop("method")]
            item["details"] = [item.pop("detail")]

    return merged


def extract_frames(
    video_path: str,
    timestamps: list[dict],
    output_dir: Path,
) -> list[str]:
    """タイムスタンプ位置のフレームを抽出"""
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []

    for i, item in enumerate(timestamps):
        ts = item["timestamp"]
        output_path = output_dir / f"frame_{i:05d}.png"
        cmd = [
            "ffmpeg", "-ss", str(ts), "-i", video_path,
            "-frames:v", "1", "-q:v", "2",
            str(output_path), "-y",
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        if output_path.exists():
            frames.append(str(output_path))

    return frames


def main() -> None:
    parser = argparse.ArgumentParser(
        description="緩いパラメータでフレームを大量抽出（正解データ作成用）"
    )
    parser.add_argument(
        "--video", "-v",
        default=str(
            Path(__file__).resolve().parent.parent
            / ".work" / "10-03-06" / "videos" / "jp_video.mp4"
        ),
        help="動画ファイルパス",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(
            Path(__file__).resolve().parent.parent
            / "data" / "10-03-06" / "all_frames"
        ),
        help="フレーム出力ディレクトリ",
    )
    parser.add_argument("--noise", type=float, default=DEFAULT_NOISE)
    parser.add_argument("--min-duration", type=float, default=DEFAULT_MIN_DURATION)
    parser.add_argument("--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD)
    parser.add_argument(
        "--no-scene", action="store_true",
        help="scene detectionを無効化",
    )
    args = parser.parse_args()

    video_path = args.video
    output_dir = Path(args.output)

    if not Path(video_path).exists():
        print(f"動画が見つかりません: {video_path}")
        sys.exit(1)

    # Step 1: freezedetect
    print(f"=== freezedetect (noise={args.noise}, d={args.min_duration}) ===")
    freeze_ts = extract_freezedetect_timestamps(
        video_path, args.noise, args.min_duration
    )
    print(f"  検出数: {len(freeze_ts)}")

    # Step 2: scene detection
    scene_ts = []
    if not args.no_scene:
        print(f"\n=== scene detection (threshold={args.scene_threshold}) ===")
        scene_ts = extract_scene_timestamps(video_path, args.scene_threshold)
        print(f"  検出数: {len(scene_ts)}")

    # Step 3: 統合
    all_ts = freeze_ts + scene_ts
    merged = merge_timestamps(all_ts)
    print(f"\n統合後: {len(merged)} フレーム（統合前: {len(all_ts)}）")

    # Step 4: フレーム抽出
    print(f"\nフレーム抽出中 → {output_dir}")
    frames = extract_frames(video_path, merged, output_dir)
    print(f"抽出完了: {len(frames)} フレーム")

    # Step 5: メタデータ保存
    metadata = {
        "source_video": video_path,
        "parameters": {
            "noise": args.noise,
            "min_duration": args.min_duration,
            "scene_threshold": args.scene_threshold if not args.no_scene else None,
        },
        "frames": {},
    }
    for i, item in enumerate(merged):
        name = f"frame_{i:05d}.png"
        metadata["frames"][name] = {
            "timestamp": item["timestamp"],
            "methods": item["methods"],
            "details": item["details"],
        }

    metadata_path = output_dir / "extraction_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"メタデータ保存: {metadata_path}")


if __name__ == "__main__":
    main()
