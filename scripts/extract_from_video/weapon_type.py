"""英雄紹介フレームの武器種検出

2つの検出方式を提供:
1. テンプレートマッチング（detect_weapon_type / detect_weapon_types_batch）
   - 英雄紹介フレームの検出用（recall=100%）
   - 武器種の分類精度は限定的

2. CV線アンカー + LLM分類（classify_weapon_type_with_llm）
   - CV/イラスト上の水平線を検出してアイコン領域をクロップ
   - Gemini等のLLMで武器種を分類（精度50-58%、ヒント用途）
"""

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

# テンプレート画像のディレクトリ
TEMPLATES_DIR = Path(__file__).parent / "templates" / "weapon_icons"

# 検索領域（フレーム画像に対する比率）
# 英雄名の右側、画面の右下部分
SEARCH_REGION = (0.35, 0.52, 1.0, 0.82)  # (left, top, right, bottom)

# 標準フレームサイズ（テンプレートはこのサイズで作成）
STANDARD_SIZE = (480, 854)

# テンプレートマッチングの閾値
DETECTION_THRESHOLD = 0.65

# 武器種コード → weapon_code のマッピング
# CLAUDE.md のスキル説明文フォーマットで使用するコード
WEAPON_TYPE_TO_CODE: dict[str, str] = {
    "sword": "rs",
    "lance": "bl",
    "axe": "ga",
    "red_bow": "bo",
    "blue_bow": "bo",
    "green_bow": "bo",
    "colorless_bow": "bo",
    "red_dagger": "da",
    "blue_dagger": "da",
    "green_dagger": "da",
    "colorless_dagger": "da",
    "staff": "cs",
    "red_tome": "rt",
    "blue_tome": "bt",
    "green_tome": "gt",
    "colorless_tome": "ct",
    "red_dragon": "br",
    "blue_dragon": "br",
    "green_dragon": "br",
    "colorless_dragon": "br",
    "red_beast": "be",
    "blue_beast": "be",
    "green_beast": "be",
    "colorless_beast": "be",
}


def _load_templates(templates_dir: Path | None = None) -> dict[str, np.ndarray]:
    """テンプレート画像を読み込む"""
    d = templates_dir or TEMPLATES_DIR
    templates = {}
    for p in d.glob("*.png"):
        tmpl = cv2.imread(str(p))
        if tmpl is not None:
            templates[p.stem] = tmpl
    return templates


# モジュールレベルでテンプレートをキャッシュ
_templates_cache: dict[str, np.ndarray] | None = None


def _get_templates() -> dict[str, np.ndarray]:
    global _templates_cache
    if _templates_cache is None:
        _templates_cache = _load_templates()
    return _templates_cache


def detect_weapon_type(
    frame_path: str,
    templates_dir: str | None = None,
    search_region: tuple[float, float, float, float] = SEARCH_REGION,
    threshold: float = DETECTION_THRESHOLD,
) -> str | None:
    """フレーム画像から武器種アイコンをテンプレートマッチングで検出

    Args:
        frame_path: フレーム画像のパス
        templates_dir: テンプレート画像ディレクトリ（Noneでデフォルト）
        search_region: 検索範囲（left, top, right, bottom）の比率
        threshold: マッチングスコアの閾値

    Returns:
        武器種名（"sword", "lance" 等）またはNone（非英雄紹介フレーム）
    """
    if templates_dir:
        templates = _load_templates(Path(templates_dir))
    else:
        templates = _get_templates()

    if not templates:
        print("警告: テンプレート画像が見つかりません")
        return None

    img = cv2.imread(frame_path)
    if img is None:
        return None

    h, w = img.shape[:2]

    # 標準サイズにリサイズ（テンプレートとのスケール合わせ）
    if (w, h) != STANDARD_SIZE:
        img = cv2.resize(img, STANDARD_SIZE)
        h, w = STANDARD_SIZE[1], STANDARD_SIZE[0]

    # 検索領域をクロップ
    left, top, right, bottom = search_region
    sy = int(h * top)
    ey = int(h * bottom)
    sx = int(w * left)
    ex = int(w * right)
    search = img[sy:ey, sx:ex]

    best_score = 0.0
    best_name: str | None = None

    for tname, tmpl in templates.items():
        th, tw = tmpl.shape[:2]
        if search.shape[0] < th or search.shape[1] < tw:
            continue

        result = cv2.matchTemplate(search, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        if max_val > best_score:
            best_score = max_val
            best_name = tname

    if best_score >= threshold:
        return best_name
    return None


def detect_weapon_types_batch(
    frame_paths: list[str],
    threshold: float = DETECTION_THRESHOLD,
) -> list[tuple[str, str | None, float]]:
    """複数フレームに対して武器種検出を一括実行

    Returns:
        [(frame_path, weapon_type, score), ...] のリスト
    """
    templates = _get_templates()
    if not templates:
        print("警告: テンプレート画像が見つかりません")
        return [(p, None, 0.0) for p in frame_paths]

    results = []
    for path in frame_paths:
        img = cv2.imread(path)
        if img is None:
            results.append((path, None, 0.0))
            continue

        h, w = img.shape[:2]
        if (w, h) != STANDARD_SIZE:
            img = cv2.resize(img, STANDARD_SIZE)
            h, w = STANDARD_SIZE[1], STANDARD_SIZE[0]

        left, top, right, bottom = SEARCH_REGION
        sy = int(h * top)
        ey = int(h * bottom)
        sx = int(w * left)
        ex = int(w * right)
        search = img[sy:ey, sx:ex]

        best_score = 0.0
        best_name: str | None = None

        for tname, tmpl in templates.items():
            th, tw = tmpl.shape[:2]
            if search.shape[0] < th or search.shape[1] < tw:
                continue

            result = cv2.matchTemplate(search, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)

            if max_val > best_score:
                best_score = max_val
                best_name = tname

        detected = best_name if best_score >= threshold else None
        results.append((path, detected, best_score))

    return results


def get_weapon_code(weapon_type: str) -> str | None:
    """武器種名からweapon_codeに変換

    Args:
        weapon_type: "sword", "lance", "blue_bow" 等

    Returns:
        weapon_code ("rs", "bl", "bo" 等) またはNone
    """
    return WEAPON_TYPE_TO_CODE.get(weapon_type)


# === CV線アンカー + LLM分類 ===

# 水平Sobelフィルタ
_KERNEL_H = ImageFilter.Kernel(
    size=(3, 3),
    kernel=[1, 2, 1, 0, 0, 0, -1, -2, -1],
    scale=1, offset=128,
)

# CV線検出パラメータ
_CV_LINE_Y_RANGE = (0.73, 0.79)  # フレーム高さに対するy範囲
_CV_LINE_THRESHOLD = 70  # 水平エッジ強度の閾値

# アイコンクロップパラメータ（CV線基準）
_ICON_CROP_X = (0.60, 0.97)  # フレーム幅に対するx範囲
_ICON_CROP_Y_OFFSET = 0.12  # CV線からの上方向オフセット（フレーム高さ比）
_ICON_UPSCALE = 4  # LLM送信前の拡大倍率

# Wiki参照アイコンのディレクトリ
WIKI_ICONS_DIR = Path(__file__).parent / "templates" / "weapon_icons" / "originals"

# 全武器種名（LLMプロンプト用）
ALL_WEAPON_TYPES = [
    "sword", "lance", "axe", "staff",
    "red_tome", "blue_tome", "green_tome", "colorless_tome",
    "red_bow", "blue_bow", "green_bow", "colorless_bow",
    "red_dagger", "blue_dagger", "green_dagger", "colorless_dagger",
    "red_dragon", "blue_dragon", "green_dragon", "colorless_dragon",
    "red_beast", "blue_beast", "green_beast", "colorless_beast",
]


def find_cv_line_y(img: Image.Image) -> int | None:
    """英雄紹介フレームのCV/イラスト上部にある水平線のy座標を検出

    Returns:
        水平線のy座標（ピクセル）、検出できない場合はNone
    """
    w, h = img.size
    gray = img.convert("L")
    edges = gray.filter(_KERNEL_H)
    arr = np.array(edges)

    y_start = int(h * _CV_LINE_Y_RANGE[0])
    y_end = int(h * _CV_LINE_Y_RANGE[1])
    region = arr[y_start:y_end, :]

    row_strengths = np.mean(np.abs(region.astype(float) - 128), axis=1)
    max_idx = int(np.argmax(row_strengths))
    max_val = float(row_strengths[max_idx])

    if max_val >= _CV_LINE_THRESHOLD:
        return y_start + max_idx
    return None


def crop_icon_region(img: Image.Image, cv_line_y: int) -> Image.Image:
    """CV線基準で武器+移動アイコン領域をクロップ"""
    w, h = img.size
    left = int(w * _ICON_CROP_X[0])
    right = int(w * _ICON_CROP_X[1])
    top = max(0, cv_line_y - int(h * _ICON_CROP_Y_OFFSET))
    bottom = cv_line_y + int(h * 0.005)
    return img.crop((left, top, right, bottom))


def classify_weapon_type_with_llm(
    frame_path: str,
    model: str = "gemini-2.5-flash",
) -> str | None:
    """英雄紹介フレームからLLMで武器種を推定（ヒント用途）

    CV線を検出 → アイコン領域をクロップ → 拡大 → LLMに送信

    Args:
        frame_path: 英雄紹介フレーム画像のパス
        model: Geminiモデル名

    Returns:
        武器種名（"lance", "red_tome" 等）またはNone
    """
    from google import genai
    from google.genai import types

    img = Image.open(frame_path)
    cv_y = find_cv_line_y(img)
    if cv_y is None:
        return None

    # アイコン領域をクロップして拡大
    crop = crop_icon_region(img, cv_y)
    upscaled = crop.resize(
        (crop.width * _ICON_UPSCALE, crop.height * _ICON_UPSCALE),
        Image.LANCZOS,
    )

    # 画像をバイトに変換
    buf = io.BytesIO()
    upscaled.save(buf, format="PNG")
    crop_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")

    # Wiki参照アイコンをパーツとして構築
    parts: list = [
        "Fire Emblem Heroes weapon type icon reference:\n",
    ]
    for wt in ALL_WEAPON_TYPES:
        icon_path = WIKI_ICONS_DIR / f"{wt}.png"
        if icon_path.exists():
            data = icon_path.read_bytes()
            parts.append(f"\n{wt}:")
            parts.append(types.Part.from_bytes(data=data, mime_type="image/png"))

    parts.append(
        "\n\nThe image below is an ENLARGED crop from a Fire Emblem Heroes "
        "hero introduction screen. It contains two small square icons: "
        "the TOP icon is the weapon type, the BOTTOM icon is the movement type. "
        "Identify the TOP icon's weapon type from the reference list above.\n\n"
        "IMPORTANT: Reply with ONLY the exact weapon type name "
        "(e.g. 'lance', 'red_tome', 'colorless_bow'). No explanation.\n"
    )
    parts.append(crop_part)

    client = genai.Client()
    try:
        response = client.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(temperature=0),
        )
        text = (response.text or "").strip().split("\n")[0].strip().strip("*").strip()
        if text in ALL_WEAPON_TYPES:
            return text
        return None
    except Exception as e:
        print(f"  武器種LLM分類エラー: {e}")
        return None


def classify_weapon_hints_batch(
    frame_paths: list[str],
    model: str = "gemini-2.5-flash",
) -> list[tuple[str, str | None]]:
    """複数フレームに対してLLMで武器種ヒントを一括取得

    Returns:
        [(frame_path, weapon_type_or_none), ...] のリスト
    """
    results = []
    for path in frame_paths:
        weapon = classify_weapon_type_with_llm(path, model=model)
        results.append((path, weapon))
        if weapon:
            code = get_weapon_code(weapon)
            print(f"  {Path(path).name}: {weapon} (code={code}) [LLMヒント]")
        else:
            print(f"  {Path(path).name}: 分類不可")
    return results
