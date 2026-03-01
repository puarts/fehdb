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
from frames import extract_static_frames, detect_skill_frames, deduplicate_frames
from ocr import create_backend
from formatter import format_output, write_output, get_max_skill_id
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
    parser.add_argument("--min-duration", type=float, default=1.5,
                        help="静止区間の最低秒数（これより短い静止を無視、デフォルト: 1.5秒）")
    parser.add_argument("--local-ocr",
                        choices=["auto", "apple", "tesseract", "none"],
                        default="none",
                        help="ローカルOCRでVLMにヒント提供（デフォルト: none）")

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

    if args.frames_only:
        print("\n--frames-only: フレーム抽出完了。OCRはスキップします。")
        print(f"フレーム保存先: {work_dir / 'frames'}")
        return

    # === Step 3.5: ローカルOCRヒント ===
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

    if en_frame_groups:
        print("\n[英語版 OCR]")
        en_skills = backend.ocr_en_skills(en_frame_groups, new_only=new_only)
        print(f"  EN スキル数: {len(en_skills)}")

        print("\n[JP↔ENマッチング]")
        jp_valid = [s for s in jp_skills if not s.jp_name.startswith("__")]
        en_map = backend.match_jp_en_skills(jp_valid, en_skills)
        for skill in jp_skills:
            if not skill.jp_name.startswith("__"):
                skill.en_name = en_map.get(skill.jp_name)
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

    if args.dry_run:
        print(f"[ドライラン] スキル数: {len(jp_skills)}")
    else:
        if args.output:
            output_path = str(SOURCES_DIR / args.output)
        else:
            # デフォルトファイル名を生成
            output_path = str(SOURCES_DIR / _generate_output_name())
        write_output(output_content, output_path)
        print(f"完了: {len(jp_skills)} スキルを {output_path} に出力しました")


def _get_video(url: str | None, local_path: str | None, language: str, *, video_dir: Path) -> VideoInfo:
    """URLまたはローカルパスから動画を取得"""
    if local_path:
        return load_local_video(local_path, language)
    if url:
        return download_video(url, language, video_dir=video_dir)
    raise ValueError(f"{language}動画のソースが指定されていません")


def _generate_output_name() -> str:
    """日付ベースのデフォルト出力ファイル名を生成"""
    from datetime import date
    today = date.today()
    # FEHの日付フォーマット: book-chapter-day (例: 10-02-17)
    # 自動生成は単純に日付を使う
    return f"auto-{today.strftime('%Y%m%d')}.txt"


if __name__ == "__main__":
    main()
