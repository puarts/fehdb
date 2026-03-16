"""FEH公式動画からスキルテキストを自動抽出するCLIツール

使用例:
  # 基本: JP + EN動画から抽出
  uv run python scripts/extract_from_video/main.py \
    --jp-url "https://youtube.com/watch?v=xxx" \
    --en-url "https://youtube.com/watch?v=yyy" \
    -o "10-02-17.txt"

  # JPのみ（英語名なし）
  uv run python scripts/extract_from_video/main.py \
    --jp-url "https://youtube.com/watch?v=xxx"

  # ローカル動画ファイルを使用
  uv run python scripts/extract_from_video/main.py \
    --jp-video /path/to/jp.mp4 --en-video /path/to/en.mp4

  # ドライラン
  uv run python scripts/extract_from_video/main.py --jp-url "..." --dry-run
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from download import download_video, load_local_video
from frames import extract_static_frames, extract_hero_intro_candidates, detect_skill_frames, deduplicate_frames
from ocr import create_backend
from formatter import format_output, format_en_output, write_output, get_max_skill_id
from models import VideoInfo

SOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "sources" / "skill-desc"
WORK_DIR_BASE = Path(".work")
_VALID_ID_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


def main():
    parser = argparse.ArgumentParser(
        description="FEH公式動画からスキルテキストを自動抽出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # 動画ソース
    jp_group = parser.add_mutually_exclusive_group(required=True)
    jp_group.add_argument("--jp-url", help="日本語版動画のURL")
    jp_group.add_argument("--jp-video", help="日本語版動画のローカルパス")

    en_group = parser.add_mutually_exclusive_group()
    en_group.add_argument("--en-url", help="英語版動画のURL")
    en_group.add_argument("--en-video", help="英語版動画のローカルパス")

    # 出力設定
    parser.add_argument("-o", "--output", help="出力ファイル名（sources/skill-desc/ に配置）")
    parser.add_argument("--start-id", type=int, help="スキルID開始番号（デフォルト: DB最大値+1）")

    # OCRバックエンド
    parser.add_argument("--ocr", choices=["claude", "gemini", "ollama"], default="claude",
                        help="OCRバックエンド（デフォルト: claude）")
    parser.add_argument("--gemini-model",
                        choices=["gemini-3-flash-preview", "gemini-2.5-flash"],
                        default="gemini-3-flash-preview",
                        help="Geminiモデル名（デフォルト: gemini-3-flash-preview）")
    parser.add_argument("--ollama-model", default="qwen2.5vl",
                        help="Ollamaモデル名（デフォルト: qwen2.5vl）")

    # キャッシュ
    parser.add_argument("--id", help="キャッシュ識別子（動画ごとにキャッシュを分離）")

    # オプション
    parser.add_argument("--all", action="store_true",
                        help="全スキルをOCR（デフォルト: 新スキルのみ）")
    parser.add_argument("--dry-run", action="store_true", help="プレビューのみ（ファイル出力しない）")
    parser.add_argument("--frames-only", action="store_true",
                        help="フレーム抽出・スキル画面検出まで実行（OCRは行わない）")
    parser.add_argument("--keep-frames", action="store_true", help="デバッグ用にフレーム画像を残す")
    parser.add_argument("--min-duration", type=float, default=1.4,
                        help="静止区間の最低秒数（これより短い静止を無視、デフォルト: 1.4秒）")
    parser.add_argument("--local-ocr",
                        choices=["auto", "apple", "tesseract", "none"],
                        default="none",
                        help="ローカルOCRでVLMにヒント提供（デフォルト: none）")
    parser.add_argument("--no-card-crop", action="store_true",
                        help="カードクロップを無効化（従来の全画面OCRを使用）")
    parser.add_argument("--detect-weapon", action="store_true",
                        help="英雄紹介フレームから武器種を自動検出")

    args = parser.parse_args()

    # 外部ツールの確認
    _check_dependencies()

    work_dir = WORK_DIR_BASE / args.id if args.id else WORK_DIR_BASE

    try:
        _run_pipeline(args, work_dir)
    finally:
        if not args.keep_frames and not args.frames_only and work_dir.exists():
            # フレーム画像のみ削除（動画はキャッシュとして残す）
            frames_dir = work_dir / "frames"
            if frames_dir.exists():
                shutil.rmtree(frames_dir)


def _check_dependencies():
    """必要な外部ツールの存在確認"""
    missing = []
    for tool in ["yt-dlp", "ffmpeg"]:
        if shutil.which(tool) is None:
            missing.append(tool)
    if missing:
        print(f"エラー: 以下のツールがインストールされていません: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def _run_pipeline(args, work_dir: Path):
    """メインパイプラインの実行"""

    if args.id and not _VALID_ID_RE.match(args.id):
        print(f"エラー: --id に使用できない文字が含まれています: {args.id!r}（英数字, -, _ のみ）", file=sys.stderr)
        sys.exit(1)

    # === Step 1: 動画の取得 ===
    print("=" * 50)
    print("Step 1: 動画の取得")
    print("=" * 50)

    video_dir = work_dir / "videos"
    jp_video = _get_video(args.jp_url, args.jp_video, "jp", video_dir=video_dir)
    en_video = _get_video(args.en_url, args.en_video, "en", video_dir=video_dir) if (args.en_url or args.en_video) else None

    # === Step 2: 静止区間検出 + フレーム抽出 ===
    print()
    print("=" * 50)
    print("Step 2: 静止区間検出 + フレーム抽出")
    print("=" * 50)

    # 前回のフレームキャッシュを削除（残骸防止）
    frames_dir = work_dir / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)

    jp_frames_dir = str(work_dir / "frames" / "jp")
    jp_static_frames = extract_static_frames(
        jp_video.path, jp_frames_dir, min_duration=args.min_duration,
    )

    en_frame_groups = None
    en_static_frames = None
    if en_video:
        en_frames_dir = str(work_dir / "frames" / "en")
        en_static_frames = extract_static_frames(
            en_video.path, en_frames_dir, min_duration=args.min_duration,
        )

    # === Step 2.5: 英雄紹介フレーム検出（武器種ヒント取得） ===
    # timestamp → weapon_type のヒント（LLM推定、確度低）
    hero_weapon_hints: dict[float, str] = {}
    strict_timestamps: list[float] = []
    if args.detect_weapon:
        from weapon_type import (
            detect_weapon_types_batch, get_weapon_code,
            classify_weapon_hints_batch,
        )

        print()
        print("=" * 50)
        print("Step 2.5: 英雄紹介フレーム検出（武器種ヒント取得）")
        print("=" * 50)

        strict_timestamps = _extract_timestamps(jp_video.path, min_duration=args.min_duration)

        hero_candidates_dir = str(work_dir / "frames" / "hero_candidates")
        hero_candidates = extract_hero_intro_candidates(
            jp_video.path,
            strict_timestamps=strict_timestamps,
            output_dir=hero_candidates_dir,
            noise=0.08,
            min_duration=1.5,
        )

        if hero_candidates:
            # テンプレートマッチングで英雄紹介フレームを検出
            candidate_paths = [path for path, _ in hero_candidates]
            tm_results = detect_weapon_types_batch(candidate_paths)

            # テンプレートマッチングで検出されたフレームのみLLM分類
            hero_frames = [
                (path, ts)
                for (path, weapon, score), (_, ts) in zip(tm_results, hero_candidates)
                if weapon is not None
            ]

            if hero_frames:
                print(f"\n英雄紹介フレーム: {len(hero_frames)} 検出")
                print("LLMで武器種ヒント取得中...")
                gemini_model = getattr(args, "gemini_model", "gemini-2.5-flash")
                llm_results = classify_weapon_hints_batch(
                    [path for path, _ in hero_frames],
                    model=gemini_model,
                )
                for (_, weapon_hint), (_, ts) in zip(llm_results, hero_frames):
                    if weapon_hint:
                        hero_weapon_hints[ts] = weapon_hint
                print(f"武器種ヒント: {len(hero_weapon_hints)}/{len(hero_frames)}")
        else:
            print("  差分候補フレームなし")

    # === Step 3: スキル画面検出 + 重複除去 ===
    print()
    print("=" * 50)
    print("Step 3: スキル画面検出 + 重複除去")
    print("=" * 50)

    jp_skill_frames = detect_skill_frames(jp_static_frames)
    jp_frame_groups = deduplicate_frames(jp_skill_frames)

    if en_static_frames:
        en_skill_frames = detect_skill_frames(en_static_frames)
        en_frame_groups = deduplicate_frames(en_skill_frames)

    print(f"\nJP スキル数: {len(jp_frame_groups)}")
    if en_frame_groups:
        print(f"EN スキル数: {len(en_frame_groups)}")

    # 武器種ヒントをFrameGroupに関連付け
    if hero_weapon_hints and strict_timestamps:
        _assign_weapon_hints(jp_frame_groups, jp_static_frames, strict_timestamps, hero_weapon_hints)

    # === Step 3.5: スキルカードクロップ ===
    if not args.no_card_crop:
        from card_crop import crop_frame_groups

        print()
        print("=" * 50)
        print("Step 3.5: スキルカードクロップ")
        print("=" * 50)

        print("\n[日本語版]")
        jp_cropped_dir = work_dir / "frames" / "cropped_jp"
        crop_frame_groups(jp_frame_groups, jp_cropped_dir)

        if en_frame_groups:
            print("\n[英語版]")
            en_cropped_dir = work_dir / "frames" / "cropped_en"
            crop_frame_groups(en_frame_groups, en_cropped_dir)

    if args.frames_only:
        print("\n--frames-only: フレーム抽出完了。OCRはスキップします。")
        print(f"フレーム保存先: {work_dir / 'frames'}")
        return

    # === Step 3.7: ローカルOCRヒント ===
    if args.local_ocr != "none":
        from local_ocr import detect_local_ocr_engine, run_local_ocr
        engine = detect_local_ocr_engine(args.local_ocr)
        if engine:
            print()
            print("=" * 50)
            print(f"Step 3.5: ローカルOCRヒント（{engine}）")
            print("=" * 50)
            run_local_ocr(jp_frame_groups, engine, lang="ja")

    # === Step 4: OCR ===
    backend_kwargs = {}
    if args.ocr == "gemini":
        backend_kwargs["model"] = args.gemini_model
        backend_label = f"Gemini ({args.gemini_model})"
    elif args.ocr == "ollama":
        backend_kwargs["model"] = args.ollama_model
        backend_label = f"Ollama ({args.ollama_model})"
    else:
        backend_label = "Claude Vision API"

    new_only = not args.all
    mode_label = "新スキルのみ" if new_only else "全スキル"

    print()
    print("=" * 50)
    print(f"Step 4: OCR（{backend_label}、{mode_label}）")
    print("=" * 50)

    backend = create_backend(args.ocr, **backend_kwargs)

    print("\n[日本語版]")
    jp_skills = backend.ocr_jp_skills(jp_frame_groups, new_only=new_only)

    # DB照合: LLMのis_new誤判定を補正し、既存スキルを除去
    from formatter import get_existing_skill_names
    existing_names = get_existing_skill_names()
    if existing_names:
        before_count = len(jp_skills)
        jp_skills = [s for s in jp_skills if s.jp_name.startswith("__") or s.jp_name not in existing_names]
        removed = before_count - len(jp_skills)
        if removed > 0:
            print(f"  DB照合: {removed}件の既存スキルを除去（残り{len(jp_skills)}件）")

    en_skills = []
    if en_frame_groups:
        print("\n[英語版 OCR]")
        en_skills = backend.ocr_en_skills(en_frame_groups, new_only=False)
        print(f"  EN スキル数: {len(en_skills)}")

        print("\n[JP↔ENマッチング]")
        jp_valid = [s for s in jp_skills if not s.jp_name.startswith("__")]
        en_map = backend.match_jp_en_skills(jp_valid, en_skills)
        # LLMがキーにメタデータ（例: "スキル名 (パッシブB)"）を含める場合があるので
        # 括弧以前のスキル名のみで照合する正規化マップを作成
        en_map_normalized: dict[str, str | None] = {}
        for k, v in en_map.items():
            name = k.split(" (")[0].strip()
            # 同名スキルの重複時は最初のマッチを優先
            if name not in en_map_normalized:
                en_map_normalized[name] = v
        for skill in jp_skills:
            if not skill.jp_name.startswith("__"):
                skill.en_name = en_map_normalized.get(skill.jp_name)
        matched = sum(1 for s in jp_skills if s.en_name)
        print(f"  マッチング結果: {matched}/{len(jp_valid)} スキル")

    # === Step 5: 出力生成 ===
    print()
    print("=" * 50)
    print("Step 5: 出力生成")
    print("=" * 50)

    start_id = args.start_id
    if start_id is None:
        max_id = get_max_skill_id()
        start_id = max_id + 1
        print(f"DB最大ID: {max_id} → 開始ID: {start_id}")

    output_content = format_output(jp_skills, None, start_id)

    print()
    print("-" * 40)
    print(output_content)
    print("-" * 40)

    # EN出力
    en_output_content = None
    if en_skills:
        en_output_content = format_en_output(en_skills)
        print()
        print("[EN出力プレビュー]")
        print("-" * 40)
        print(en_output_content)
        print("-" * 40)

    # LLM API呼び出し回数の集計
    llm_calls = 0
    if hasattr(backend, "api_call_count"):
        llm_calls += backend.api_call_count
    if hero_weapon_hints:
        llm_calls += len(hero_weapon_hints)  # classify_weapon_hints_batch の呼び出し数
    if llm_calls > 0:
        print(f"\nLLM API呼び出し回数: {llm_calls}")

    if args.dry_run:
        print(f"[ドライラン] JP スキル数: {len(jp_skills)}")
        if en_skills:
            print(f"[ドライラン] EN スキル数: {len(en_skills)}")
    else:
        if args.output:
            jp_output_path = str(SOURCES_DIR / args.output)
        else:
            jp_output_path = str(SOURCES_DIR / _generate_output_name())
        write_output(output_content, jp_output_path)
        print(f"完了: {len(jp_skills)} スキルを {jp_output_path} に出力しました")

        if en_output_content:
            en_filename = Path(jp_output_path).stem + "-en" + Path(jp_output_path).suffix
            en_output_path = str(Path(jp_output_path).parent / en_filename)
            write_output(en_output_content, en_output_path)
            print(f"完了: {len(en_skills)} ENスキルを {en_output_path} に出力しました")


def _get_video(url: str | None, local_path: str | None, language: str, *, video_dir: Path) -> VideoInfo:
    """URLまたはローカルパスから動画を取得"""
    if local_path:
        return load_local_video(local_path, language)
    if url:
        return download_video(url, language, video_dir=video_dir)
    raise ValueError(f"{language}動画のソースが指定されていません")


def _extract_timestamps(
    video_path: str,
    min_duration: float = 1.5,
    noise: float = 0.003,
) -> list[float]:
    """動画からfreezedetectでタイムスタンプを取得（フレーム抽出なし）"""
    import subprocess
    from frames import _parse_freezedetect

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"freezedetect=n={noise}:d={min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    intervals = _parse_freezedetect(result.stderr)
    return [(s + e) / 2 for s, e in intervals]


def _assign_weapon_hints(
    frame_groups: list,
    static_frame_paths: list[str],
    static_timestamps: list[float],
    hero_weapon_hints: dict[float, str],
) -> None:
    """英雄紹介フレームの武器種ヒントを後続のFrameGroupに関連付け

    Args:
        frame_groups: スキルFrameGroupのリスト
        static_frame_paths: extract_static_framesの出力パスリスト
        static_timestamps: static_frame_pathsと1:1対応するタイムスタンプ
        hero_weapon_hints: 英雄紹介タイムスタンプ → 武器種ヒント
    """
    if not hero_weapon_hints:
        return

    hint_timestamps = sorted(hero_weapon_hints.keys())

    # static_frame_pathsのファイル名 → タイムスタンプのマッピング
    frame_name_to_ts: dict[str, float] = {}
    for path, ts in zip(static_frame_paths, static_timestamps):
        frame_name_to_ts[Path(path).name] = ts

    for group in frame_groups:
        rep_name = Path(group.representative).name
        skill_ts = frame_name_to_ts.get(rep_name)
        if skill_ts is None:
            continue

        # このスキルフレームより前で最も近い英雄紹介のヒントを選ぶ
        best_hint = None
        for ts in hint_timestamps:
            if ts < skill_ts:
                best_hint = hero_weapon_hints[ts]
            else:
                break

        if best_hint:
            group.weapon_hint = best_hint


def _generate_output_name() -> str:
    """日付ベースのデフォルト出力ファイル名を生成"""
    from datetime import date
    today = date.today()
    # FEHの日付フォーマット: book-chapter-day (例: 10-02-17)
    # 自動生成は単純に日付を使う
    return f"auto-{today.strftime('%Y%m%d')}.txt"


if __name__ == "__main__":
    main()
