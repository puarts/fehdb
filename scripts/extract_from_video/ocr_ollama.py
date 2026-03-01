"""Ollama VLMによるOCRバックエンド"""

import json
import time
from pathlib import Path

import ollama
from pydantic import BaseModel, ValidationError

from models import ExtractedSkill, FrameGroup
from ocr import parse_jp_response, parse_en_response, extract_json, print_json, build_match_prompt, augment_prompt_with_ocr_hint, EN_USER_PROMPT_NEW_ONLY, JP_LINEBREAK_RULES

# Claude版と同じプロンプトを流用（EN系のみ）
from ocr_claude import EN_SYSTEM_PROMPT

MAX_RETRIES = 3


# === Pydanticモデル（Ollama constrained decoding用） ===


class SkillEntry(BaseModel):
    skill_name: str
    skill_type: str
    weapon_type: str | None = None
    might: int | None = None
    range: int | None = None
    special_count: int | None = None
    description: list[str] = []
    hero_name: str | None = None


class SkillListResponse(BaseModel):
    skills: list[SkillEntry]


# === Ollama専用の簡略化JPプロンプト ===

JP_USER_PROMPT_OLLAMA_NEW_ONLY = """\
このFEHのスキル画面から「！」マーク付きの新スキルのみを抽出してください。

スキルの見分け方: スキルは枠線で囲まれたカード内に表示され、カード上部にスキルアイコン（丸型）と大きな文字のスキル名、その下に説明文が続きます。
英雄紹介やキャラクター説明のテキストはスキルではありません。この構造がない画面では skills: [] を返してください。

「習得可能スキル」のヘッダーがない画面（双界スキル画面、スタイル画面など）では新スキルなし（skills: []）です。
「！」マークはオレンジ/黄色の小さいビックリマークで、スキル名の左側に表示されます。
丸い円形のアイコン（スキル種別バッジ）は「！」マークではありません。
テキストは画面に表示されたものを一字一句正確に写してください。数値は半角で記述してください。

descriptionの改行ルール:
""" + JP_LINEBREAK_RULES + """

例:
{"skills": [{"skill_name": "フィンブルの花", "skill_type": "武器", "weapon_type": "青魔法", "might": 14, "range": 2, "special_count": null, "description": ["ターン開始時、自身のHPが25%以上の時、自分と周囲2マスの味方の攻撃、速さ+6（1ターン）"], "hero_name": "春風の配達人 エイリーク"}]}"""

JP_USER_PROMPT_OLLAMA = """\
このFEHのスキル画面からスキル情報を抽出してください。

スキルの見分け方: スキルは枠線で囲まれたカード内に表示され、カード上部にスキルアイコン（丸型）と大きな文字のスキル名、その下に説明文が続きます。
英雄紹介やキャラクター説明のテキストはスキルではありません。この構造がない画面では skill_name を空文字 "" にしてください。

テキストは画面に表示されたものを一字一句正確に写してください。数値は半角で記述してください。
複数画像が送られた場合は同一スキルのスクロール続きです。重複部分を除去して結合してください。
skill_typeは「武器」「奥義」「サポート」「パッシブA」「パッシブB」「パッシブC」「響心」のいずれかです。

descriptionの改行ルール:
""" + JP_LINEBREAK_RULES + """

例:
{"skill_name": "フィンブルの花", "skill_type": "武器", "weapon_type": "青魔法", "might": 14, "range": 2, "special_count": null, "description": ["ターン開始時、自身のHPが25%以上の時、自分と周囲2マスの味方の攻撃、速さ+6（1ターン）"], "hero_name": "春風の配達人 エイリーク"}"""


class OllamaOCRBackend:
    """Ollama VLMを使用するOCRバックエンド"""

    def __init__(self, model: str = "qwen2.5vl"):
        self.model = model

    def ocr_jp_skills(self, frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]:
        """日本語版スキル画面をOCRし、ExtractedSkillリストを返す"""
        results = []

        for i, group in enumerate(frame_groups):
            print(f"  JP OCR [{i + 1}/{len(frame_groups)}]: {Path(group.representative).name}")

            try:
                if new_only:
                    skills_data = self._call_jp_new_only(group.all_frames, ocr_hint=group.ocr_hint)
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
                    skill_data = self._call_jp(group.all_frames, ocr_hint=group.ocr_hint)
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
        results = []

        for i, group in enumerate(frame_groups):
            print(f"  EN OCR [{i + 1}/{len(frame_groups)}]: {Path(group.representative).name}")

            try:
                if new_only:
                    skills_data = self._call_en_new_only(group.all_frames)
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
                response = ollama.chat(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": prompt,
                    }],
                    format="json",
                    options={"temperature": 0},
                )
                text = response.message.content
                data = extract_json(text)
                print_json(data)
                if isinstance(data, dict):
                    return data
                return {}
            except (ollama.ResponseError, ConnectionError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    print(f"    エラー（スキップ）: {e}")
                    return {}

        return {}

    def _call_jp_new_only(self, image_paths: list[str], ocr_hint: str | None = None) -> list[dict]:
        """JP画像をOllama VLMに送信し、新スキルのみJSON配列で返す"""
        prompt = augment_prompt_with_ocr_hint(JP_USER_PROMPT_OLLAMA_NEW_ONLY, ocr_hint)
        for attempt in range(MAX_RETRIES):
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": prompt,
                        "images": image_paths,
                    }],
                    format=SkillListResponse.model_json_schema(),
                    options={"temperature": 0},
                )
                text = response.message.content
                print_json(json.loads(text))
                parsed = SkillListResponse.model_validate_json(text)
                return [entry.model_dump() for entry in parsed.skills]
            except (ollama.ResponseError, ConnectionError, ValidationError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("JP OCR (Ollama, new_only): 最大リトライ回数超過")

    def _call_jp(self, image_paths: list[str], ocr_hint: str | None = None) -> dict:
        """JP画像をOllama VLMに送信し、JSONレスポンスを返す"""
        prompt = augment_prompt_with_ocr_hint(JP_USER_PROMPT_OLLAMA, ocr_hint)
        for attempt in range(MAX_RETRIES):
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": prompt,
                        "images": image_paths,
                    }],
                    format=SkillEntry.model_json_schema(),
                    options={"temperature": 0},
                )
                text = response.message.content
                print_json(json.loads(text))
                parsed = SkillEntry.model_validate_json(text)
                return parsed.model_dump()
            except (ollama.ResponseError, ConnectionError, ValidationError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("JP OCR (Ollama): 最大リトライ回数超過")

    def _call_en_new_only(self, image_paths: list[str]) -> list[dict]:
        """EN画像をOllama VLMに送信し、新スキルのみJSON配列で返す"""
        prompt = f"{EN_SYSTEM_PROMPT}\n\n{EN_USER_PROMPT_NEW_ONLY}"

        for attempt in range(MAX_RETRIES):
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": prompt,
                        "images": image_paths,
                    }],
                    format="json",
                    options={"temperature": 0},
                )
                text = response.message.content
                print_json(json.loads(text))
                data = extract_json(text)
                if isinstance(data, list):
                    return data
                # {"skills": [...]} のようなラッパーを処理
                if isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, list):
                            return v
                return []
            except (ollama.ResponseError, ConnectionError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"    リトライ ({attempt + 1}/{MAX_RETRIES}): {e}")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("EN OCR (Ollama, new_only): 最大リトライ回数超過")

