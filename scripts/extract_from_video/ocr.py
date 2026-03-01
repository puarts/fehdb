"""OCRバックエンド共通インターフェース + ファクトリ + 共有ユーティリティ"""

import base64
import json
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from line_merger import merge_lines
from models import ExtractedSkill, FrameGroup


# === 改行ルール（両バックエンドで共有） ===

JP_LINEBREAK_RULES = """\
画面上のテキスト折り返し（word wrap）で分割しないこと。
1行 = 1つの独立した効果・条件ブロック。1行が100文字以上になることもある。

改行する（新しい配列要素にする）タイミング:
- 「飛行特効」等の特効効果（単語1つでも独立した行）
- 「奥義が発動しやすい（発動カウント-1）」等の発動カウント効果
- 「ターン開始時、...」で始まるターン開始効果
- 「戦闘中、...」で始まる戦闘効果
- 「自分から攻撃した時、...」等の条件付き効果
- 「【再移動（...）】を発動可能」等の再移動効果

改行しない（同じ行に続ける）場合:
- 条件と効果が読点（、）で繋がっている場合
- 括弧内の補足「（範囲奥義を除く）」等
- 「かつ」「および」で繋がる場合"""

JP_LINEBREAK_EXAMPLES = """\
改行の例:

例1（武器スキル、5行）:
["杖は他の武器同様のダメージ計算になる", "奥義が発動しやすい（発動カウント-1）（奥義発動カウント最大値の下限は1）", "自身を中心とした縦3列と横3列の敵は、戦闘中、攻撃、速さ、守備、魔防-5、奥義以外のスキルによる「ダメージを○○％軽減」を半分無効（無効にする数値は端数切捨て）（範囲奥義を除く）、奥義以外の「敵の致死攻撃を受けた時、ダメージをHPが1残るように軽減」する効果を無効", "戦闘中、攻撃、速さ、守備、魔防+10、与えるダメージ+25（範囲奥義を除く）、受けるダメージ-15（範囲奥義を除く）", "下記の【スタイル】を使用可能【スタイル】：フリーズ"]
※3行目は約130文字だが、同一効果が読点で繋がっているため1行。

例2（パッシブC、3行）:
["【再移動（マス間の距離、最大3、最低1）】を発動可能", "自分から攻撃した時、戦闘後、敵とその周囲2マスの敵に【護られ不可】、【不和】を付与（敵次回行動終了まで）、敵のマスとその周囲2マスのマスに【天脈・気】を付与（1ターン）", "戦闘中、攻撃、速さ、守備、魔防+5、与えるダメージ+7（範囲奥義を除く）、受けるダメージ-7（範囲奥義を除く）、自身の奥義発動カウント変動量-を無効、かつ追撃の速さ条件を-10した状態で追撃の速さ条件を満たしている時（絶対追撃、追撃不可は含まない）、戦闘中、【神速追撃：ダメージ100%】を発動"]
※3行目は約150文字。「かつ」で繋がる条件は改行しない。"""


# === 新スキルフィルタリング用プロンプト（両バックエンドで共有） ===

JP_USER_PROMPT_NEW_ONLY = """\
このFEHのスキル画面から、新スキルのみを抽出してください。

スキルテキストの見分け方:
- スキルは枠線で囲まれたカード内に表示される
- カード上部にスキルアイコン（丸型）と大きな文字のスキル名がある
- その下にスキル効果の説明文が続く
- 英雄紹介やキャラクター説明のテキストはスキルではありません
- この構造がない画面の場合、空配列 [] を返してください

この画面に「習得可能スキル」のヘッダーがない場合（双界スキル画面、スタイル画面など）は、「！」マークは表示されないため空配列 [] を返してください。

画面のスキル一覧では、各行が左から「！」マーク（新スキルの場合のみ表示）→ スキル種別アイコン（丸いバッジ）→ スキル名 の順に並んでいます。
「！」マークはオレンジ/黄色の小さいビックリマークで、行の最左端に表示されます。
丸い円形のアイコン（スキル種別バッジ）は「！」マークではありません。
「！」マークがないスキルは新スキルではないので無視してください。

まず各スキルの「！」マークの有無を確認し、「！」があるスキルのみ以下の情報をJSON配列で出力してください。
該当スキルがない場合は空配列 [] を返してください。

抽出フィールド:
- skill_name: スキル名（文字列）
- skill_type: スキル種別。次のいずれか: "武器", "奥義", "サポート", "パッシブA", "パッシブB", "パッシブC", "響心"
- weapon_type: 武器種（武器の場合のみ）
- might: 威力（武器の場合のみ、整数）
- range: 射程（武器の場合のみ、整数）
- special_count: 奥義カウント（奥義の場合のみ、整数）
- description: 説明文（行ごとの配列）
- hero_name: この画面に表示されている英雄名

descriptionの改行ルール:
""" + JP_LINEBREAK_RULES + """

""" + JP_LINEBREAK_EXAMPLES + """

注意事項:
- テキストは一字一句正確に写してください。意味の推測による修正はしないでください
- 数値は半角で記述してください

出力形式（JSON配列のみ、他のテキストは不要）:
```json
[{"skill_name": "スキル名", "skill_type": "武器", ...}]
```"""

EN_USER_PROMPT_NEW_ONLY = """\
Extract ONLY new skills from this FEH skill screen.

How to identify skill text:
- Skills are displayed inside bordered cards
- Each card has a skill icon (circular) and skill name in large text at the top
- Skill effect description follows below
- Hero introduction or character description text is NOT skill data
- If this screen does not have this card structure, return an empty array []

If this screen does not show a "Skills learnable" header (e.g., Harmonized Skill or Style screens), return an empty array [] — "!" marks only appear on skill list screens.

In the skill list, each row is laid out as: "!" indicator (shown only for new skills) → skill type icon (circular badge) → skill name.
The "!" is a small orange/yellow mark at the far left of the row.
Circular icons (skill type badges) are NOT the "!" indicator.
Skills without the "!" mark are not new — ignore them.

First check each skill for the "!" indicator, then extract only those with "!".
If no skills have "!", return an empty array: []

For each skill with "!", extract:
- skill_name: Skill name (string)
- skill_type: One of "Weapon", "Special", "Assist", "Passive A", "Passive B", "Passive C", "Harmonized"
- weapon_type: Weapon type (for weapons only)
- might: Might (for weapons only, integer)
- range: Range (for weapons only, integer)
- special_count: Special cooldown (for specials only, integer)
- description: Skill effect text (array of lines)
- hero_name: Hero name shown on this screen

Output as JSON array:
```json
[{"skill_name": "Heroic Maltet", "skill_type": "Weapon", ...}]
```"""


def augment_prompt_with_ocr_hint(prompt: str, ocr_hint: str | None) -> str:
    """OCRヒントテキストをプロンプトに追加"""
    if not ocr_hint:
        return prompt
    return prompt + f"""

参考情報（ローカルOCRによる事前読み取り結果）:
以下はOCRエンジンで読み取ったテキストです。誤読がある可能性があります。
画像の表示を正として、このテキストは読み取りの参考にしてください。

```
{ocr_hint}
```"""


@runtime_checkable
class OCRBackend(Protocol):
    """OCRバックエンドのプロトコル"""

    def ocr_jp_skills(self, frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]: ...
    def ocr_en_skills(self, frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]: ...
    def match_jp_en_skills(self, jp_skills: list[ExtractedSkill], en_skills: list[ExtractedSkill]) -> dict[str, str | None]: ...


def create_backend(name: str, **kwargs) -> OCRBackend:
    """指定名のOCRバックエンドを生成"""
    if name == "claude":
        from ocr_claude import ClaudeOCRBackend
        return ClaudeOCRBackend(**kwargs)
    elif name == "gemini":
        from ocr_gemini import GeminiOCRBackend
        return GeminiOCRBackend(**kwargs)
    elif name == "ollama":
        from ocr_ollama import OllamaOCRBackend
        return OllamaOCRBackend(**kwargs)
    raise ValueError(f"Unknown OCR backend: {name}")


# === 共有ユーティリティ ===

_FULLWIDTH_DIGIT_TABLE = str.maketrans('０１２３４５６７８９', '0123456789')


def _normalize_digits(text: str) -> str:
    """全角数字を半角に変換"""
    return text.translate(_FULLWIDTH_DIGIT_TABLE)


_ASCII_WORD_RE = re.compile(r'[a-zA-Z]{2,}')


def _validate_jp_name(name: str) -> str:
    """JP名に英単語が混入していないかチェック"""
    matches = _ASCII_WORD_RE.findall(name)
    if matches:
        print(f"  警告: JP名に英単語が検出されました: {name!r} ({matches})")
    return name


def parse_en_response(data: dict, frame_index: int) -> ExtractedSkill:
    """EN APIレスポンスのJSONをExtractedSkillに変換"""
    return ExtractedSkill(
        jp_name="",
        en_name=data.get("skill_name", ""),
        skill_type=data.get("skill_type", ""),
        might=data.get("might"),
        range_=data.get("range"),
        count=data.get("special_count"),
        description_lines=data.get("description", []),
        hero_name=data.get("hero_name"),
        frame_index=frame_index,
    )


def build_match_prompt(jp_skills: list[ExtractedSkill], en_skills: list[ExtractedSkill]) -> str:
    """JP/ENスキルリストからマッチングプロンプトを生成"""
    jp_lines = []
    for i, s in enumerate(jp_skills):
        meta = f"({s.skill_type}"
        if s.might:
            meta += f", 威力{s.might}"
        if s.count:
            meta += f", @{s.count}"
        if s.hero_name:
            meta += f", {s.hero_name}"
        meta += ")"
        jp_lines.append(f"{i + 1}. {s.jp_name} {meta}")

    en_lines = []
    for i, s in enumerate(en_skills):
        meta = f"({s.skill_type}"
        if s.might:
            meta += f", Mt{s.might}"
        if s.count:
            meta += f", @{s.count}"
        if s.hero_name:
            meta += f", {s.hero_name}"
        meta += ")"
        en_lines.append(f"{i + 1}. {s.en_name} {meta}")

    return f"""\
Match each Japanese FEH skill to its English counterpart based on skill type, stats, and hero name.
Both lists are from the same game update, shown in similar order.

Japanese skills:
{chr(10).join(jp_lines)}

English skills:
{chr(10).join(en_lines)}

Return a JSON object mapping each Japanese skill name to its English skill name.
If no match is found, use null.
Example: {{"双勇マルテ": "Heroic Maltet", "重装の双炎": "Armored Flare"}}"""


def extract_json(text: str) -> dict | list:
    """テキストからJSON部分を抽出してパース"""
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + len("```")
        end = text.index("```", start)
        text = text[start:end].strip()

    return json.loads(text)


def print_json(data) -> None:
    """パース済みJSONデータを整形して表示"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def parse_jp_response(data: dict, frame_index: int) -> ExtractedSkill:
    """APIレスポンスのJSONをExtractedSkillに変換"""
    raw_lines = [_normalize_digits(line) for line in data.get("description", [])]
    merged_lines = merge_lines(raw_lines)
    jp_name = _validate_jp_name(_normalize_digits(data.get("skill_name", "")))
    return ExtractedSkill(
        jp_name=jp_name,
        skill_type=data.get("skill_type", ""),
        weapon_code=weapon_type_to_code(data.get("weapon_type")),
        might=data.get("might"),
        range_=data.get("range"),
        count=data.get("special_count"),
        description_lines=merged_lines,
        hero_name=data.get("hero_name"),
        frame_index=frame_index,
    )


def weapon_type_to_code(weapon_type: str | None) -> str | None:
    """日本語武器種名をコードに変換"""
    if weapon_type is None:
        return None
    mapping = {
        "剣": "rs",
        "槍": "bl",
        "斧": "ga",
        "弓": "bo",
        "暗器": "da",
        "杖": "cs",
        "竜石": "br",
        "獣": "be",
        "赤魔法": "rt",
        "青魔法": "bt",
        "緑魔法": "gt",
        "無魔法": "ct",
    }
    return mapping.get(weapon_type)


def load_images(paths: list[str]) -> list[dict]:
    """画像ファイルをbase64エンコードしたメッセージコンテンツに変換"""
    contents = []
    for path in paths:
        data = Path(path).read_bytes()
        b64 = base64.standard_b64encode(data).decode("utf-8")
        contents.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        })
    return contents


# === 後方互換関数（デフォルトClaude） ===


def ocr_jp_skills(frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]:
    """日本語版スキル画面をOCRし、ExtractedSkillリストを返す（後方互換）"""
    backend = create_backend("claude")
    return backend.ocr_jp_skills(frame_groups, new_only=new_only)


def ocr_en_skills(frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]:
    """英語版スキル画面をOCRし、ExtractedSkillリストを返す（後方互換）"""
    backend = create_backend("claude")
    return backend.ocr_en_skills(frame_groups, new_only=new_only)
