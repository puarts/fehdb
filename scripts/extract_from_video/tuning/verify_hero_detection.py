"""英雄紹介フレーム検出のパラメータ最適化スクリプト

freezedetect（noise緩和）のパラメータをグリッドサーチし、
複数動画にわたって英雄紹介フレームの検出精度を最大化するパラメータ組み合わせを探索する。

正解データ: data/{session}/annotations/hero_frame_labels.json
動画: .work/{session}/videos/jp_video.mp4

評価基準:
- FN=0 制約（英雄紹介を1つも見逃さない）を最優先
- FN=0 の中で FP が最少のパラメータを選出
"""

import itertools
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frames import _parse_freezedetect

# タイムスタンプ照合の許容誤差（秒）
TIMESTAMP_TOLERANCE = 2.0

# 対象セッション
SESSIONS = [
    "10-03-06",  # 超英雄・春（パーティクル多）
    "10-02-27",  # 神階英雄チキ
    "09-01-06",  # 新英雄＆響心ブリギッド
    "09-05-07",  # 新英雄＆魔器ドゥドゥー
    "09-09-16",  # つながりアシュ＆響心リョウマ
    "09-10-17",  # つながりシャロン＆比翼エリンシア
    "10-02-16",  # 双界英雄ヘクトル・セリカ＆救世フィヨルム
]


# --- パラメータ定義 ---

@dataclass(frozen=True)
class FreezeParams:
    noise: float
    min_duration: float


# グリッドサーチ範囲
FREEZE_SWEEP = {
    "noise": [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10],
    "min_duration": [0.5, 0.8, 1.0, 1.5],
}


# --- 正解データ ---

@dataclass
class VideoGroundTruth:
    """1動画の正解データ"""
    session: str
    video_path: str
    hero_timestamps: list[float]
    description: str


def load_video_ground_truth(
    base_dir: Path,
    session: str,
) -> VideoGroundTruth | None:
    """1セッションの正解データを読み込む"""
    labels_path = base_dir / "data" / session / "annotations" / "hero_frame_labels.json"
    video_path = base_dir / ".work" / session / "videos" / "jp_video.mp4"

    if not labels_path.exists():
        print(f"  {session}: ラベルなし、スキップ")
        return None
    if not video_path.exists():
        print(f"  {session}: 動画なし、スキップ")
        return None

    with open(labels_path) as f:
        data = json.load(f)

    hero_timestamps = []
    for info in data["frames"].values():
        if info["label"] == "hero_intro":
            hero_timestamps.append(info["timestamp"])
    hero_timestamps.sort()

    return VideoGroundTruth(
        session=session,
        video_path=str(video_path),
        hero_timestamps=hero_timestamps,
        description=data.get("description", session),
    )


# --- ffmpeg 実行 + キャッシュ ---

# キャッシュキー: (video_path, params) → timestamps
_cache: dict[str, list[float]] = {}


def run_freezedetect(
    video_path: str,
    params: FreezeParams,
) -> list[float]:
    """freezedetect を実行してタイムスタンプを返す（キャッシュ付き）"""
    cache_key = f"{video_path}:freeze:{params.noise}:{params.min_duration}"
    if cache_key in _cache:
        return _cache[cache_key]

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"freezedetect=n={params.noise}:d={params.min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    intervals = _parse_freezedetect(result.stderr)

    timestamps = [round((s + e) / 2, 3) for s, e in intervals]
    _cache[cache_key] = timestamps
    return timestamps


# --- 評価 ---

@dataclass
class VideoEvalResult:
    """1動画の評価結果"""
    session: str
    tp: int
    fp: int
    fn: int
    detected_count: int
    missed: list[float] = field(default_factory=list)


@dataclass
class AggregateResult:
    """全動画の集約評価結果"""
    params: FreezeParams
    total_tp: int
    total_fp: int
    total_fn: int
    total_detected: int
    total_hero: int
    per_video: list[VideoEvalResult] = field(default_factory=list)
    all_missed: list[tuple[str, float]] = field(default_factory=list)


def evaluate_timestamps(
    detected: list[float],
    ground_truth: list[float],
    tolerance: float = TIMESTAMP_TOLERANCE,
) -> tuple[int, int, int, list[float]]:
    """検出タイムスタンプを正解データと照合

    Returns: (tp, fp, fn, missed_timestamps)
    """
    det_matched = set()

    for gt_ts in ground_truth:
        best_det_idx = None
        best_dist = float("inf")
        for det_idx, det_ts in enumerate(detected):
            if det_idx in det_matched:
                continue
            dist = abs(gt_ts - det_ts)
            if dist <= tolerance and dist < best_dist:
                best_dist = dist
                best_det_idx = det_idx
        if best_det_idx is not None:
            det_matched.add(best_det_idx)

    tp = len(det_matched)
    fn = len(ground_truth) - tp
    fp = len(detected) - tp
    missed = [
        gt_ts for i, gt_ts in enumerate(ground_truth)
        if not any(
            abs(gt_ts - detected[d]) <= tolerance
            for d in det_matched
            if abs(gt_ts - detected[d]) <= tolerance
        )
    ]
    # 再計算: missedを正確に
    gt_matched = set()
    for gt_idx, gt_ts in enumerate(ground_truth):
        for det_idx in det_matched:
            if abs(gt_ts - detected[det_idx]) <= tolerance:
                gt_matched.add(gt_idx)
                break
    missed = [gt_ts for i, gt_ts in enumerate(ground_truth) if i not in gt_matched]

    return tp, fp, fn, missed


def evaluate_all_videos(
    videos: list[VideoGroundTruth],
    params: FreezeParams,
) -> AggregateResult:
    """全動画に対してパラメータを評価"""
    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_detected = 0
    total_hero = 0
    per_video = []
    all_missed = []

    for v in videos:
        timestamps = run_freezedetect(v.video_path, params)
        tp, fp, fn, missed = evaluate_timestamps(timestamps, v.hero_timestamps)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_detected += len(timestamps)
        total_hero += len(v.hero_timestamps)
        per_video.append(VideoEvalResult(
            session=v.session, tp=tp, fp=fp, fn=fn,
            detected_count=len(timestamps), missed=missed,
        ))
        for m in missed:
            all_missed.append((v.session, m))

    return AggregateResult(
        params=params,
        total_tp=total_tp,
        total_fp=total_fp,
        total_fn=total_fn,
        total_detected=total_detected,
        total_hero=total_hero,
        per_video=per_video,
        all_missed=all_missed,
    )


# --- メイン ---

def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent

    # 正解データ読み込み
    print("正解データ読み込み中...")
    videos: list[VideoGroundTruth] = []
    for session in SESSIONS:
        v = load_video_ground_truth(base_dir, session)
        if v:
            videos.append(v)
            print(f"  {session}: hero_intro={len(v.hero_timestamps)} — {v.description}")

    total_hero = sum(len(v.hero_timestamps) for v in videos)
    print(f"\n合計: {len(videos)} 動画, {total_hero} hero_intro")

    # === グリッドサーチ ===
    freeze_keys = list(FREEZE_SWEEP.keys())
    freeze_values = [FREEZE_SWEEP[k] for k in freeze_keys]
    combos = list(itertools.product(*freeze_values))
    print(f"\nグリッドサーチ開始: {len(combos)} パラメータ × {len(videos)} 動画 = {len(combos) * len(videos)} ffmpeg実行")

    start = time.time()
    results: list[AggregateResult] = []

    for i, combo in enumerate(combos):
        params = FreezeParams(**dict(zip(freeze_keys, combo)))
        agg = evaluate_all_videos(videos, params)
        results.append(agg)
        if (i + 1) % 7 == 0:
            cached = len(_cache)
            print(f"  {i+1}/{len(combos)} 完了（キャッシュ: {cached}）")

    elapsed = time.time() - start
    print(f"  完了: {elapsed:.1f}秒")

    # === FN=0 制約 ===
    print(f"\n{'=' * 90}")
    print(f" FN=0 制約付き結果（FP昇順）— 全{len(videos)}動画, hero_intro={total_hero}")
    print(f"{'=' * 90}")

    zero_fn = [r for r in results if r.total_fn == 0]
    if zero_fn:
        zero_fn.sort(key=lambda r: r.total_fp)
        print(
            f"{'Rank':>4} {'noise':>6} {'d':>4} {'TP':>4} {'FP':>5} {'FN':>3} "
            f"{'Det':>6} {'FP/vid':>7}"
        )
        print("-" * 50)
        for rank, r in enumerate(zero_fn[:10], 1):
            fp_per_vid = r.total_fp / len(videos)
            print(
                f"{rank:>4} {r.params.noise:>6.3f} {r.params.min_duration:>4.1f} "
                f"{r.total_tp:>4} {r.total_fp:>5} {r.total_fn:>3} "
                f"{r.total_detected:>6} {fp_per_vid:>7.1f}"
            )

        best = zero_fn[0]
        print(f"\n最良: noise={best.params.noise}, d={best.params.min_duration}")
        print(f"  TP={best.total_tp}/{total_hero}, FP={best.total_fp}, 検出総数={best.total_detected}")
        print("\n  動画別内訳:")
        for v in best.per_video:
            print(f"    {v.session}: TP={v.tp}, FP={v.fp}, 検出={v.detected_count}")
    else:
        print("FN=0 を達成するパラメータが見つかりません")

    # === 全結果 Top 15 ===
    print(f"\n{'=' * 90}")
    print(" 全結果（FN昇順 → FP昇順）Top 15")
    print(f"{'=' * 90}")
    results.sort(key=lambda r: (r.total_fn, r.total_fp))
    print(
        f"{'Rank':>4} {'noise':>6} {'d':>4} {'TP':>4} {'FP':>5} {'FN':>3} "
        f"{'Det':>6} {'Missed'}"
    )
    print("-" * 90)
    for rank, r in enumerate(results[:15], 1):
        missed_str = ""
        if r.all_missed:
            missed_str = ", ".join(f"{s}@{t:.0f}s" for s, t in r.all_missed)
        print(
            f"{rank:>4} {r.params.noise:>6.3f} {r.params.min_duration:>4.1f} "
            f"{r.total_tp:>4} {r.total_fp:>5} {r.total_fn:>3} "
            f"{r.total_detected:>6} {missed_str}"
        )

    # === FN=1以下で FP最少（FN=0がない場合のフォールバック） ===
    if not zero_fn:
        fn1 = [r for r in results if r.total_fn <= 1]
        if fn1:
            fn1.sort(key=lambda r: (r.total_fn, r.total_fp))
            print(f"\nFN≤1 最良:")
            best = fn1[0]
            print(f"  noise={best.params.noise}, d={best.params.min_duration}")
            print(f"  TP={best.total_tp}/{total_hero}, FP={best.total_fp}, FN={best.total_fn}")
            print(f"  見逃し: {best.all_missed}")


if __name__ == "__main__":
    main()
