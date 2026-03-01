from dataclasses import dataclass, field


@dataclass
class ExtractedSkill:
    """OCRで抽出されたスキル情報"""

    jp_name: str
    en_name: str | None = None
    skill_type: str = ""  # "武器", "奥義", "サポート", "パッシブA", "パッシブB", "パッシブC", "響心"
    weapon_code: str | None = None  # "rs", "bl", "gt" 等
    might: int | None = None
    range_: int | None = None
    count: int | None = None  # 奥義カウント
    stat_bonuses: dict[str, int] = field(default_factory=dict)  # {"a": 9, "s": 9}
    description_lines: list[str] = field(default_factory=list)
    hero_name: str | None = None
    frame_index: int = 0  # 動画内の順番


@dataclass
class FrameGroup:
    """重複除去後のフレームグループ"""

    representative: str  # 代表フレームのパス
    all_frames: list[str] = field(default_factory=list)  # スクロール含む全フレーム
    frame_index: int = 0
    ocr_hint: str | None = None  # ローカルOCRヒントテキスト


@dataclass
class VideoInfo:
    """ダウンロードした動画の情報"""

    path: str
    language: str  # "jp" or "en"
    title: str = ""
