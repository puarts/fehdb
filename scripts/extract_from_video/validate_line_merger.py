"""line_merger.py の LINE_START_PATTERNS を DB の既存スキル説明文と照合して検証する

feh-skills.sqlite3 の description / refine_description / special_refine_description を
「正解データ」として使い、_is_line_start() がカバーできていない行頭パターン（漏れ候補）を検出する。

Usage:
    uv run python scripts/extract_from_video/validate_line_merger.py
"""

import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from line_merger import _is_line_start

# DBでは独立行だが、OCRマージでは前行にくっつけたいパターン（漏れ報告から除外）
KNOWN_MERGE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'^\('),  # 半角括弧の補足説明は前行に結合すべき
]

# プロジェクトルートの DB
DB_PATH = Path(__file__).resolve().parent.parent.parent / "feh-skills.sqlite3"

# 新規/旧スキルの境界 ID
NEW_SKILL_THRESHOLD = 3000

# グルーピング用: 行頭の文字数
GROUP_PREFIX_LEN = 10

# グループあたりの代表例の最大表示数
MAX_EXAMPLES_PER_GROUP = 3


def fetch_descriptions(db_path: Path) -> list[tuple[int, str, str]]:
    """DB から <br> を含む説明文を (id, name, description_text) のリストで返す

    description, refine_description, special_refine_description すべてを対象にする。
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    results: list[tuple[int, str, str]] = []
    for col in ("description", "refine_description", "special_refine_description"):
        cur.execute(
            f"SELECT id, name, {col} FROM skills "  # noqa: S608
            f"WHERE {col} LIKE '%<br>%'",
        )
        for row in cur.fetchall():
            results.append((row[0], row[1], row[2]))
    conn.close()
    return results


def validate(
    descriptions: list[tuple[int, str, str]],
) -> tuple[dict, dict, int, int, int, int]:
    """全説明文を検証し、パターン漏れ候補を収集する

    Returns:
        new_misses: 新規スキル (id >= 3000) の漏れ {行頭prefix: [(id, name, line), ...]}
        old_misses: 旧スキル (id < 3000) の漏れ
        total_lines: 検証した行の総数
        matched_lines: パターンにマッチした行数
        missed_lines: パターン漏れの行数
        known_merge_lines: マージが正しい動作の行数
    """
    new_misses: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    old_misses: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    total_lines = 0
    matched_lines = 0
    missed_lines = 0
    known_merge_lines = 0

    for skill_id, name, desc in descriptions:
        parts = desc.split("<br>")
        # 2行目以降を検証（1行目は常にそのまま保持される）
        for line in parts[1:]:
            line = line.strip()
            if not line:
                continue
            total_lines += 1
            if _is_line_start(line):
                matched_lines += 1
            elif any(p.search(line) for p in KNOWN_MERGE_PATTERNS):
                # DBでは独立行だが、マージが正しい動作のパターン
                known_merge_lines += 1
            else:
                missed_lines += 1
                prefix = line[:GROUP_PREFIX_LEN]
                entry = (skill_id, name, line)
                if skill_id >= NEW_SKILL_THRESHOLD:
                    new_misses[prefix].append(entry)
                else:
                    old_misses[prefix].append(entry)

    return new_misses, old_misses, total_lines, matched_lines, missed_lines, known_merge_lines


def print_misses(misses: dict[str, list[tuple[int, str, str]]]) -> None:
    """グループ化された漏れ候補を表示する"""
    # 件数の多い順にソート
    sorted_groups = sorted(misses.items(), key=lambda x: len(x[1]), reverse=True)
    for prefix, entries in sorted_groups:
        print(f"  [{len(entries):>3}件] {prefix!r}")
        for skill_id, name, line in entries[:MAX_EXAMPLES_PER_GROUP]:
            display_line = line[:40] + ("..." if len(line) > 40 else "")
            print(f"        ID {skill_id}「{name}」→ \"{display_line}\"")


def main() -> None:
    if not DB_PATH.exists():
        print(f"エラー: DB が見つかりません: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    descriptions = fetch_descriptions(DB_PATH)
    print(f"DB から {len(descriptions)} 件の説明文を取得\n")

    new_misses, old_misses, total_lines, matched, missed, known_merge = validate(
        descriptions,
    )

    # --- 新規スキル ---
    new_miss_count = sum(len(v) for v in new_misses.values())
    print(f"=== パターン漏れ候補（新規スキル ID >= {NEW_SKILL_THRESHOLD}） ===")
    if new_misses:
        print(f"    {len(new_misses)} グループ, {new_miss_count} 件\n")
        print_misses(new_misses)
    else:
        print("    なし")
    print()

    # --- 旧スキル ---
    old_miss_count = sum(len(v) for v in old_misses.values())
    print(f"=== パターン漏れ候補（旧スキル ID < {NEW_SKILL_THRESHOLD}） ===")
    if old_misses:
        print(f"    {len(old_misses)} グループ, {old_miss_count} 件\n")
        print_misses(old_misses)
    else:
        print("    なし")
    print()

    # --- サマリー ---
    match_pct = (matched / total_lines * 100) if total_lines else 0
    merge_pct = (known_merge / total_lines * 100) if total_lines else 0
    miss_pct = (missed / total_lines * 100) if total_lines else 0
    print("=== サマリー ===")
    print(f"検証スキル数: {len(descriptions):,}")
    print(f"<br>区切りの行数: {total_lines:,}")
    print(f"パターンマッチ（独立行）: {matched:,} ({match_pct:.1f}%)")
    print(f"マージが正しい行: {known_merge:,} ({merge_pct:.1f}%)")
    print(f"パターン漏れ候補: {missed:,} ({miss_pct:.1f}%)")


if __name__ == "__main__":
    main()
