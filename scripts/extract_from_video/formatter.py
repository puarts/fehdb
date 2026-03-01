import sqlite3
import sys
from pathlib import Path

from models import ExtractedSkill

# replace.pyのREPLACEMENTSを再利用（importが難しいので必要なものだけ定義）
# 全角→半角等の基本的な正規化
TEXT_REPLACEMENTS = [
    ('＋', '+'),
    ('（', '('),
    ('）', ')'),
    ('：', ':'),
    ('！', '!'),
    ('『', '「'),
    ('〇', '○'),
    ('◎', '○'),
    ('●', '○'),
    ('•', '・'),
    (',', '、'),
]

# スキルタイプ→メタデータコメントのマッピング
SKILL_TYPE_TO_COMMENT = {
    "奥義": "s",
    "サポート": "a",
    "パッシブA": "pa",
    "パッシブB": "pb",
    "パッシブC": "pc",
    "響心": "px",
}

DB_PATH = Path(__file__).resolve().parent.parent.parent / "feh-skills.sqlite3"


def get_max_skill_id() -> int:
    """feh-skills.sqlite3から現在の最大スキルIDを取得"""
    if not DB_PATH.exists():
        print(f"警告: データベースが見つかりません: {DB_PATH}", file=sys.stderr)
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM skills")
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0
    finally:
        conn.close()


def format_output(
    jp_skills: list[ExtractedSkill],
    en_names: list[str] | None,
    start_id: int | None = None,
) -> str:
    """ExtractedSkillリストを既存パイプライン互換の.txtフォーマットに変換"""
    if start_id is None:
        start_id = get_max_skill_id() + 1

    # JP/ENマッチング
    if en_names is not None:
        _match_en_names(jp_skills, en_names)

    lines: list[str] = []
    for i, skill in enumerate(jp_skills):
        skill_id = start_id + i
        entry = _format_skill_entry(skill_id, skill)
        lines.append(entry)

    return "\n\n".join(lines) + "\n"


def _match_en_names(jp_skills: list[ExtractedSkill], en_names: list[str]) -> None:
    """日本語スキルリストに英語名をマッチングして設定"""
    if len(jp_skills) == len(en_names):
        # 数が一致 → インデックスで対応付け
        for skill, en_name in zip(jp_skills, en_names):
            skill.en_name = en_name
    else:
        # 数が不一致 → skill_typeの系列でアライメントを試行
        print(
            f"警告: スキル数不一致 (JP: {len(jp_skills)}, EN: {len(en_names)})",
            file=sys.stderr,
        )
        # 少ない方に合わせてインデックスで対応付け
        for i in range(min(len(jp_skills), len(en_names))):
            jp_skills[i].en_name = en_names[i]

        # マッチできなかったものにコメントを追加
        if len(jp_skills) > len(en_names):
            for i in range(len(en_names), len(jp_skills)):
                jp_skills[i].en_name = None


def _format_skill_entry(skill_id: int, skill: ExtractedSkill) -> str:
    """1スキルのエントリをフォーマット"""
    parts: list[str] = []

    # 1行目: ID-錬成タイプ-日本語名[-英語名]
    header = f"{skill_id}-n-{skill.jp_name}"
    if skill.en_name:
        # 英語名のハイフンは=に置換（-はデリミタのため）
        en_name = skill.en_name.replace("-", "=")
        header += f"-{en_name}"
    elif skill.en_name is None and skill.jp_name and not skill.jp_name.startswith("__"):
        header += "  # TODO: 英語名未確認"
    parts.append(header)

    # メタデータコメント行
    metadata_lines = _generate_metadata_comments(skill)
    parts.extend(metadata_lines)

    # 説明文
    description = _normalize_description(skill.description_lines)
    parts.append(description)

    return "\n".join(parts)


def _generate_metadata_comments(skill: ExtractedSkill) -> list[str]:
    """スキルのメタデータからコメント行を生成"""
    comments: list[str] = []

    if skill.skill_type == "武器" and skill.weapon_code:
        comments.append(f"## w-{skill.weapon_code}")

        # 威力・射程
        might_range_parts = []
        if skill.might is not None:
            might_range_parts.append(f"威力：{skill.might}")
        if skill.range_ is not None:
            might_range_parts.append(f"射程：{skill.range_}")
        if might_range_parts:
            comments.append(f"## {' '.join(might_range_parts)}")
    elif skill.skill_type in SKILL_TYPE_TO_COMMENT:
        comments.append(f"## {SKILL_TYPE_TO_COMMENT[skill.skill_type]}")

        # 奥義カウント
        if skill.count is not None:
            comments.append(f"## @{skill.count}")

    # ステータスボーナス
    if skill.stat_bonuses:
        bonus_parts = []
        for stat, value in skill.stat_bonuses.items():
            sign = "+" if value >= 0 else "-"
            bonus_parts.append(f"{stat}{sign}{abs(value)}")
        if bonus_parts:
            comments.append(f"## {','.join(bonus_parts)}")

    return comments


def _normalize_description(lines: list[str]) -> str:
    """説明文行リストを改行区切りのテキストに正規化

    <br>変換は後続の.txtファイル読み込み時（replace.py）に行うため、
    この段階では改行のまま出力する。
    """
    # 空行を除去
    lines = [line.strip() for line in lines if line.strip()]

    # 基本的な正規化を適用
    joined = "\n".join(lines)
    for search, replace in TEXT_REPLACEMENTS:
        joined = joined.replace(search, replace)

    return joined


def write_output(content: str, output_path: str) -> None:
    """出力ファイルに書き込み"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"出力ファイル: {path}")
