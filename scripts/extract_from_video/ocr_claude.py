"""Claude Vision APIによるOCRバックエンド"""

import time

import anthropic

from models import ExtractedSkill, FrameGroup
from ocr import (
    extract_json, print_json, parse_jp_response, parse_en_response,
    load_images, build_match_prompt, augment_prompt_with_ocr_hint,
    JP_USER_PROMPT_NEW_ONLY, EN_USER_PROMPT_NEW_ONLY,
    JP_LINEBREAK_RULES, JP_LINEBREAK_EXAMPLES,
)

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3

# リトライ対象のエラー（500 Internal Server Error + 429 Rate Limit）
_RETRYABLE_ERRORS = (anthropic.RateLimitError, anthropic.InternalServerError)

JP_SYSTEM_PROMPT = """\
あなたはFEH（ファイアーエムブレム ヒーローズ）のスキル説明文を正確に書き起こす専門家です。
スキルテキストは枠線で囲まれたカード内に表示され、カード上部にスキルアイコン（丸型）と
大きな文字のスキル名、その下にスキル効果の説明文が続きます。
画面に表示されているスキル情報をすべて正確にJSON形式で抽出してください。
この構造がない画面（英雄紹介、キャラクター説明等）の場合はスキルがないことを示してください。"""

JP_USER_PROMPT = """\
このFEHのスキル画面から以下の情報を正確にJSON形式で抽出してください。

- この画面にスキルのカード（枠線＋アイコン＋スキル名の構造）がない場合、
  skill_nameを空文字 "" にしてください

抽出フィールド:
- skill_name: スキル名（文字列）
- skill_type: スキル種別。次のいずれか: "武器", "奥義", "サポート", "パッシブA", "パッシブB", "パッシブC", "響心"
- weapon_type: 武器種（武器の場合のみ。例: "剣", "槍", "斧", "弓", "暗器", "杖", "竜石", "獣", "赤魔法", "青魔法", "緑魔法", "無魔法"）
- might: 威力（武器の場合のみ、整数）
- range: 射程（整数。武器の場合のみ）
- special_count: 奥義カウント（奥義の場合のみ、整数）
- description: 説明文（行ごとの配列）
- hero_name: この画面に表示されている英雄名（表示されていればnull以外）

descriptionの改行ルール:
""" + JP_LINEBREAK_RULES + """

""" + JP_LINEBREAK_EXAMPLES + """

注意事項:
- テキストは一字一句正確に写してください。意味の推測による修正はしないでください
- 「ー」（長音）と「-」（ハイフン/マイナス）の区別に注意してください
- 数値は半角で記述してください
- 【】や（）はそのまま写してください
- 複数画像が送られた場合は同一スキルのスクロール続きです。重複部分を除去して結合してください
- skill_typeは画面の表示から判断してください。画面左側のアイコンの位置や色で判断できます

出力形式（JSONのみ、他のテキストは不要）:
```json
{
  "skill_name": "スキル名",
  "skill_type": "武器",
  "weapon_type": "剣",
  "might": 16,
  "range": 1,
  "special_count": null,
  "description": ["1行目", "2行目", "3行目"],
  "hero_name": "英雄名"
}
```"""

EN_SYSTEM_PROMPT = """\
You are an expert at reading Fire Emblem Heroes skill screens.
Skills are displayed inside bordered cards with a circular skill icon and skill name at the top,
followed by the skill effect description below.
If the screen does not contain this card structure (e.g., hero introduction or character description),
indicate that no skills are present.
Extract only the skill names from the screenshots."""

class ClaudeOCRBackend:
    """Claude Vision APIを使用するOCRバックエンド"""

    def __init__(self, model: str = MODEL):
        self.model = model
        self.client = anthropic.Anthropic()

    def ocr_jp_skills(self, frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]:
        """日本語版スキル画面をOCRし、ExtractedSkillリストを返す"""
        from pathlib import Path

        results = []
        for i, group in enumerate(frame_groups):
            print(f"  JP OCR [{i + 1}/{len(frame_groups)}]: {Path(group.representative).name}")
            images = load_images(group.all_frames)

            try:
                if new_only:
                    skills_data = self._call_vision_api_jp_new_only(images, ocr_hint=group.ocr_hint)
                    if not skills_data:
                        print("    → 新スキルなし（スキップ）")
                        continue
                    for skill_data in skills_data:
                        skill = parse_jp_response(skill_data, group.frame_index)
                        if not skill.jp_name:
                            print("    → 非スキル画面（スキップ）")
                            continue
                        results.append(skill)
                        print(f"    → {skill.jp_name}")
                else:
                    skill_data = self._call_vision_api_jp(images, ocr_hint=group.ocr_hint)
                    skill = parse_jp_response(skill_data, group.frame_index)
                    if not skill.jp_name:
                        print("    → 非スキル画面（スキップ）")
                        continue
                    results.append(skill)
            except Exception as e:
                print(f"    エラー: {e}")
                results.append(ExtractedSkill(
                    jp_name=f"__OCR_ERROR_{i}__",
                    description_lines=[f"OCRエラー: {e}"],
                    frame_index=group.frame_index,
                ))

        return results

    def ocr_en_skills(self, frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]:
        """英語版スキル画面をOCRし、ExtractedSkillリストを返す"""
        from pathlib import Path

        results = []
        for i, group in enumerate(frame_groups):
            print(f"  EN OCR [{i + 1}/{len(frame_groups)}]: {Path(group.representative).name}")
            images = load_images(group.all_frames)

            try:
                if new_only:
                    skills_data = self._call_vision_api_en_new_only(images)
                    for skill_data in skills_data:
                        skill = parse_en_response(skill_data, group.frame_index)
                        if skill.en_name:
                            results.append(skill)
                            print(f"    → {skill.en_name}")
                    if not skills_data:
                        print("    → 新スキルなし（スキップ）")
            except Exception as e:
                print(f"    エラー: {e}")

        return results

    def match_jp_en_skills(self, jp_skills: list[ExtractedSkill], en_skills: list[ExtractedSkill]) -> dict[str, str | None]:
        """JP/ENスキルリストをテキストLLMでマッチング"""
        prompt = build_match_prompt(jp_skills, en_skills)

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
                data = extract_json(text)
                print_json(data)
                if isinstance(data, dict):
                    return data
                return {}
            except _RETRYABLE_ERRORS:
                wait = 2 ** attempt
                print(f"    サーバーエラー/レート制限、{wait}秒待機...")
                time.sleep(wait)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    print(f"    エラー（スキップ）: {e}")
                    return {}

        return {}

    def _call_vision_api_jp_new_only(self, images: list[dict], ocr_hint: str | None = None) -> list[dict]:
        """JP画像をClaude Vision APIに送信し、新スキルのみJSON配列で返す"""
        prompt = augment_prompt_with_ocr_hint(JP_USER_PROMPT_NEW_ONLY, ocr_hint)
        content = images + [{"type": "text", "text": prompt}]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=JP_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}],
                )
                text = response.content[0].text
                data = extract_json(text)
                print_json(data)
                if isinstance(data, list):
                    return data
                return []
            except _RETRYABLE_ERRORS:
                wait = 2 ** attempt
                print(f"    サーバーエラー/レート制限、{wait}秒待機...")
                time.sleep(wait)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("JP OCR (new_only): 最大リトライ回数超過")

    def _call_vision_api_jp(self, images: list[dict], ocr_hint: str | None = None) -> dict:
        """JP画像をClaude Vision APIに送信し、JSONレスポンスを返す"""
        prompt = augment_prompt_with_ocr_hint(JP_USER_PROMPT, ocr_hint)
        content = images + [{"type": "text", "text": prompt}]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=JP_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}],
                )
                text = response.content[0].text
                data = extract_json(text)
                print_json(data)
                return data
            except _RETRYABLE_ERRORS:
                wait = 2 ** attempt
                print(f"    サーバーエラー/レート制限、{wait}秒待機...")
                time.sleep(wait)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("JP OCR: 最大リトライ回数超過")

    def _call_vision_api_en_new_only(self, images: list[dict]) -> list[dict]:
        """EN画像をClaude Vision APIに送信し、新スキルのみJSON配列で返す"""
        content = images + [{"type": "text", "text": EN_USER_PROMPT_NEW_ONLY}]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=EN_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}],
                )
                text = response.content[0].text
                data = extract_json(text)
                print_json(data)
                if isinstance(data, list):
                    return data
                return []
            except _RETRYABLE_ERRORS:
                wait = 2 ** attempt
                print(f"    サーバーエラー/レート制限、{wait}秒待機...")
                time.sleep(wait)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("EN OCR (new_only): 最大リトライ回数超過")

