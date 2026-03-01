"""ローカルOCRエンジン（Apple Vision / Tesseract）によるVLMヒント生成"""

import platform
import sys
from pathlib import Path

from PIL import Image

from frames import DEFAULT_SKILL_PANEL_CROP

# Apple Vision / Tesseract の言語コードマッピング
_LANG_MAP = {
    "apple": {"ja": "ja-JP", "en": "en-US"},
    "tesseract": {"ja": "jpn", "en": "eng"},
}


def detect_local_ocr_engine(preference: str) -> str | None:
    """エンジンの自動検出

    Args:
        preference: "auto", "apple", "tesseract", "none"

    Returns:
        使用するエンジン名（"apple" / "tesseract"）、利用不可なら None
    """
    if preference == "none":
        return None

    if preference == "auto":
        if platform.system() == "Darwin":
            try:
                import ocrmac  # noqa: F401
                return "apple"
            except ImportError:
                pass
        try:
            import pytesseract  # noqa: F401
            return "tesseract"
        except ImportError:
            pass
        print("警告: ローカルOCRエンジンが見つかりません（ocrmac または pytesseract をインストールしてください）", file=sys.stderr)
        return None

    if preference == "apple":
        if platform.system() != "Darwin":
            print("警告: Apple Vision は macOS でのみ利用可能です", file=sys.stderr)
            return None
        try:
            import ocrmac  # noqa: F401
            return "apple"
        except ImportError:
            print("警告: ocrmac がインストールされていません（uv sync --extra ocr-apple）", file=sys.stderr)
            return None

    if preference == "tesseract":
        try:
            import pytesseract  # noqa: F401
            return "tesseract"
        except ImportError:
            print("警告: pytesseract がインストールされていません（uv sync --extra ocr-tesseract）", file=sys.stderr)
            return None

    return None


def run_local_ocr(
    frame_groups: list,
    engine: str,
    lang: str = "ja",
    crop_ratios: tuple[float, float, float, float] = DEFAULT_SKILL_PANEL_CROP,
) -> None:
    """フレームグループ一括処理（in-place で ocr_hint を設定）

    Args:
        frame_groups: FrameGroup のリスト
        engine: "apple" または "tesseract"
        lang: 言語（"ja" / "en"）
        crop_ratios: スキルパネル領域のクロップ比率
    """
    for i, group in enumerate(frame_groups):
        name = Path(group.representative).name
        print(f"  ローカルOCR [{i + 1}/{len(frame_groups)}]: {name}")

        try:
            text = _ocr_single_frame(group.representative, engine, crop_ratios, lang)
            if text:
                group.ocr_hint = text
                # プレビュー表示（最初の80文字）
                preview = text.replace("\n", " ")[:80]
                print(f"    → {preview}{'...' if len(text.replace(chr(10), ' ')) > 80 else ''}")
            else:
                print("    → テキスト検出なし")
        except Exception as e:
            print(f"    警告: OCRエラー（スキップ）: {e}")


def _ocr_single_frame(
    frame_path: str,
    engine: str,
    crop_ratios: tuple[float, float, float, float],
    lang: str,
) -> str:
    """1フレームのOCR実行

    Args:
        frame_path: フレーム画像のパス
        engine: "apple" または "tesseract"
        crop_ratios: クロップ比率 (left, top, right, bottom)
        lang: 言語コード ("ja" / "en")

    Returns:
        OCR結果テキスト
    """
    img = Image.open(frame_path)
    w, h = img.size

    # スキルパネル領域にクロップ
    left = int(w * crop_ratios[0])
    top = int(h * crop_ratios[1])
    right = int(w * crop_ratios[2])
    bottom = int(h * crop_ratios[3])
    cropped = img.crop((left, top, right, bottom))

    if engine == "apple":
        return _ocr_apple(cropped, lang)
    elif engine == "tesseract":
        return _ocr_tesseract(cropped, lang)
    else:
        raise ValueError(f"Unknown OCR engine: {engine}")


def _ocr_apple(image: Image.Image, lang: str) -> str:
    """Apple Vision (ocrmac) による OCR"""
    from ocrmac.ocrmac import OCR

    lang_code = _LANG_MAP["apple"].get(lang, "ja-JP")
    results = OCR(
        image,
        framework="livetext",
        language_preference=[lang_code],
    ).recognize()

    if not results:
        return ""

    # y座標でソートしてテキストを結合
    # ocrmac の結果: [(text, confidence, (x, y, w, h)), ...]
    sorted_results = sorted(results, key=lambda r: r[2][1])
    return "\n".join(r[0] for r in sorted_results)


def _ocr_tesseract(image: Image.Image, lang: str) -> str:
    """Tesseract による OCR"""
    import pytesseract

    lang_code = _LANG_MAP["tesseract"].get(lang, "jpn")
    text = pytesseract.image_to_string(image, lang=lang_code)
    return text.strip()
