import re
import subprocess
import sys
from pathlib import Path

from models import VideoInfo


def download_video(url: str, language: str | None = None, *, video_dir: Path = Path(".work/videos")) -> VideoInfo:
    """yt-dlpで動画をダウンロードし、VideoInfoを返す"""
    video_dir.mkdir(parents=True, exist_ok=True)

    # まずタイトルを取得して言語判定
    title = _get_video_title(url)
    if language is None:
        language = _detect_language(title)
    print(f"動画タイトル: {title} (言語: {language})")

    output_path = video_dir / f"{language}_video.mp4"
    if output_path.exists():
        print(f"既存ファイルを使用: {output_path}")
        return VideoInfo(path=str(output_path), language=language, title=title)

    cmd = [
        "yt-dlp",
        "--format", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        url,
    ]
    print(f"ダウンロード中: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"yt-dlp エラー:\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"動画ダウンロードに失敗: {url}")

    print(f"ダウンロード完了: {output_path}")
    return VideoInfo(path=str(output_path), language=language, title=title)


def load_local_video(path: str, language: str) -> VideoInfo:
    """ローカルの動画ファイルをVideoInfoとして返す"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"動画ファイルが見つかりません: {path}")
    return VideoInfo(path=str(p), language=language, title=p.stem)


def _get_video_title(url: str) -> str:
    """yt-dlpでタイトルのみ取得"""
    cmd = ["yt-dlp", "--get-title", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _detect_language(title: str) -> str:
    """タイトルにひらがな/カタカナが含まれていれば日本語版と判定"""
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', title):
        return "jp"
    return "en"
