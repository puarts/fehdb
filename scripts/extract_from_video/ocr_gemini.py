"""Gemini Vision APIによるOCRバックエンド"""

import time
from pathlib import Path

from google import genai
from google.genai import types

from models import ExtractedSkill, FrameGroup
from ocr import (
    extract_json, print_json, parse_jp_response, parse_en_response,
    build_match_prompt, augment_prompt_with_ocr_hint,
    JP_USER_PROMPT_NEW_ONLY, EN_USER_PROMPT_NEW_ONLY,
)
from ocr_claude import (
    JP_SYSTEM_PROMPT, JP_USER_PROMPT,
    EN_SYSTEM_PROMPT,
)

MODEL = "gemini-3-flash-preview"
MAX_RETRIES = 3

# リトライ対象のエラー
_RETRYABLE_ERRORS = (
    genai.errors.ServerError,
    genai.errors.ClientError,
)


def _load_image_parts(paths: list[str]) -> list[types.Part]:
    """画像ファイルをGemini用のPartオブジェクトに変換"""
    parts = []
    for path in paths:
        data = Path(path).read_bytes()
        parts.append(types.Part.from_bytes(data=data, mime_type="image/png"))
    return parts


class GeminiOCRBackend:
    """Gemini Vision APIを使用するOCRバックエンド"""

    def __init__(self, model: str = MODEL):
        self.model = model
        self.client = genai.Client()

    def ocr_jp_skills(self, frame_groups: list[FrameGroup], new_only: bool = True) -> list[ExtractedSkill]:
        """日本語版スキル画面をOCRし、ExtractedSkillリストを返す"""
        results = []
        for i, group in enumerate(frame_groups):
            print(f"  JP OCR [{i + 1}/{len(frame_groups)}]: {Path(group.representative).name}")

            try:
                if new_only:
                    skills_data = self._call_vision_api_jp_new_only(group.all_frames, ocr_hint=group.ocr_hint)
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
                    skill_data = self._call_vision_api_jp(group.all_frames, ocr_hint=group.ocr_hint)
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
                    skills_data = self._call_vision_api_en_new_only(group.all_frames)
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
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0,
                    ),
                )
                text = response.text
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

    def _call_vision_api_jp_new_only(self, frame_paths: list[str], ocr_hint: str | None = None) -> list[dict]:
        """JP画像をGemini Vision APIに送信し、新スキルのみJSON配列で返す"""
        image_parts = _load_image_parts(frame_paths)
        prompt = augment_prompt_with_ocr_hint(JP_USER_PROMPT_NEW_ONLY, ocr_hint)
        contents = image_parts + [prompt]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=JP_SYSTEM_PROMPT,
                        temperature=0,
                    ),
                )
                text = response.text
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

    def _call_vision_api_jp(self, frame_paths: list[str], ocr_hint: str | None = None) -> dict:
        """JP画像をGemini Vision APIに送信し、JSONレスポンスを返す"""
        image_parts = _load_image_parts(frame_paths)
        prompt = augment_prompt_with_ocr_hint(JP_USER_PROMPT, ocr_hint)
        contents = image_parts + [prompt]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=JP_SYSTEM_PROMPT,
                        temperature=0,
                    ),
                )
                text = response.text
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

    def _call_vision_api_en_new_only(self, frame_paths: list[str]) -> list[dict]:
        """EN画像をGemini Vision APIに送信し、新スキルのみJSON配列で返す"""
        image_parts = _load_image_parts(frame_paths)
        contents = image_parts + [EN_USER_PROMPT_NEW_ONLY]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=EN_SYSTEM_PROMPT,
                        temperature=0,
                    ),
                )
                text = response.text
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

