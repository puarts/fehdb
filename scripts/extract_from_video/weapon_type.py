"""英雄紹介フレームの武器種アイコンをテンプレートマッチングで検出

フレーム画像の右下部分（英雄名横のアイコン領域）にある武器種+移動タイプの
アイコンペアをOpenCVテンプレートマッチングで検出する。

検出結果:
- 武器種名（"sword", "lance", "axe" 等）
- None（アイコンが見つからない = 英雄紹介フレームではない）
"""

from pathlib import Path

import cv2
import numpy as np

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
