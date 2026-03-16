"""OCRプロンプト改善のA/B検証スクリプト

既存プロンプト(baseline)と改善プロンプト(proposed)でOCRを実行し、
正解データとの一致率を比較する。verify_ocr_crop.py ベース。
"""

import argparse
import copy
import difflib
import re
import sys
from pathlib import Path

# scripts/extract_from_video をモジュール検索パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from card_crop import crop_frame_groups
from formatter import TEXT_REPLACEMENTS, format_output
from frames import deduplicate_frames, detect_skill_frames
from models import FrameGroup
import ocr as ocr_module
from ocr import create_backend


# === 提案プロンプト定義 ===

# 変更1: 色参照削除 + 変更2: 型アノテーション + 変更3: is_new明確化 + 変更4: few-shot例
PROPOSED_JP_USER_PROMPT_SINGLE_CARD = """\
このFEHのスキルカード画像から以下の情報を正確にJSON形式で抽出してください。

この画像は1つのスキルカードのクロップです。

抽出フィールド:
- skill_name: string — スキル名
- skill_type: string — スキル種別。スキル名の左にあるアイコンで判別:
  - 「威力」「射程」の表示がある → "武器"
  - 渦巻きアイコン + カウント数字 → "奥義"
  - 水色/緑色の盾アイコン → "サポート"
  - 「A」のアイコン → "パッシブA"
  - 「B」のアイコン → "パッシブB"
  - 「C」のアイコン → "パッシブC"
  - 「X」のアイコン → "響心"
  ※新スキルの場合「！」マークがアイコンに重なりますが、アイコン内の文字は判別可能です
- weapon_type: string|null — 武器種（武器の場合のみ。例: "剣", "槍", "斧", "弓", "暗器", "杖", "竜石", "獣", "赤魔法", "青魔法", "緑魔法", "無魔法"）
- might: integer|null — 威力（武器の場合のみ）
- range: integer|null — 射程（武器の場合のみ）
- special_count: integer|null — 奥義カウント（奥義の場合のみ）
- description: string[] — 説明文（行ごとの配列）
- hero_name: string|null — 英雄名（表示されていればnull以外）
- is_new: boolean — このスキルが新スキルかどうか（スキルアイコン左上に黄色い「！」マークがある場合true）

descriptionの改行ルール:
""" + ocr_module.JP_LINEBREAK_RULES + """

""" + ocr_module.JP_LINEBREAK_EXAMPLES + """

注意事項:
- テキストは一字一句正確に写してください。意味の推測による修正はしないでください
- 数値は半角で記述してください

入出力の例:
（パッシブBスキルカードの画像に対する出力例）
```json
{"skill_name": "奥義隊形・竜眼", "skill_type": "パッシブB", "weapon_type": null, "might": null, "range": null, "special_count": null, "description": ["敵から攻撃された時、または、戦闘開始時、自身のHPが25%以上の時、戦闘中、敵の攻撃、魔防-4、自分は、与えるダメージ+魔防の20%(範囲奥義を除く)、受けるダメージ-魔防の20%(範囲奥義を除く)、自分の奥義発動カウント変動量+1(同系統効果複数時、最大値適用)、かつ敵が攻撃時発動型奥義装備時、かつ戦闘中、魔防が敵より5以上高い時、敵の最初の攻撃前に敵の奥義発動カウント+1(奥義発動カウントの最大値は超えない)"], "hero_name": null, "is_new": true}
```

出力形式（JSONのみ、他のテキストは不要）:
```json
{"skill_name": "スキル名", "skill_type": "武器", "is_new": true, ...}
```"""

# JP_USER_PROMPT_NEW_ONLY: 変更2(型アノテーション)のみ適用
PROPOSED_JP_USER_PROMPT_NEW_ONLY = """\
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
- skill_name: string — スキル名
- skill_type: string — スキル種別。次のいずれか: "武器", "奥義", "サポート", "パッシブA", "パッシブB", "パッシブC", "響心"
- weapon_type: string|null — 武器種（武器の場合のみ）
- might: integer|null — 威力（武器の場合のみ）
- range: integer|null — 射程（武器の場合のみ）
- special_count: integer|null — 奥義カウント（奥義の場合のみ）
- description: string[] — 説明文（行ごとの配列）
- hero_name: string|null — この画面に表示されている英雄名

descriptionの改行ルール:
""" + ocr_module.JP_LINEBREAK_RULES + """

""" + ocr_module.JP_LINEBREAK_EXAMPLES + """

注意事項:
- テキストは一字一句正確に写してください。意味の推測による修正はしないでください
- 数値は半角で記述してください

出力形式（JSON配列のみ、他のテキストは不要）:
```json
[{"skill_name": "スキル名", "skill_type": "武器", ...}]
```"""

# EN prompts: 変更1(色削除) + 変更2(型) + 変更3(is_new)
PROPOSED_EN_USER_PROMPT_SINGLE_CARD = """\
Extract skill information from this FEH skill card image.

This image is a crop of a single skill card.

Extract the following fields:
- skill_name: string — Skill name
- skill_type: string — Determine from the icon to the left of the skill name:
  - Has "Mt" and "Rng" display → "Weapon"
  - Swirl icon + cooldown number → "Special"
  - Cyan/green shield icon → "Assist"
  - Letter "A" icon → "Passive A"
  - Letter "B" icon → "Passive B"
  - Letter "C" icon → "Passive C"
  - Letter "X" icon → "Harmonized"
  Note: New skills have a "!" mark overlapping the icon, but the letter is still identifiable
- weapon_type: string|null — Weapon type (for weapons only)
- might: integer|null — Might (for weapons only)
- range: integer|null — Range (for weapons only)
- special_count: integer|null — Special cooldown (for specials only)
- description: string[] — Skill effect text (array of lines)
- hero_name: string|null — Hero name (if shown, otherwise null)
- is_new: boolean — Whether this is a new skill (true if yellow "!" mark is at the top-left of the skill icon)

Description line-break rules:
""" + ocr_module.EN_LINEBREAK_RULES + """

Important:
- Transcribe text exactly as shown. Do not correct or paraphrase.
- Use half-width numbers.

Output as JSON only (no other text):
```json
{"skill_name": "Heroic Maltet", "skill_type": "Weapon", "is_new": true, ...}
```"""

PROPOSED_EN_USER_PROMPT_NEW_ONLY = """\
Extract skills from this FEH skill screen.

How to identify skill text:
- Skills are displayed inside bordered cards
- Each card has a skill icon (circular) and skill name in large text at the top
- Skill effect description follows below
- Hero introduction or character description text is NOT skill data
- If this screen does not have this card structure, return an empty array []

There are two types of screens:

**Type A — "Skills learnable" list screen:**
This screen has a header like "Skills learnable" and shows multiple skills in a list.
Each row is: "!" indicator (for new skills only) → skill type icon (circular badge) → skill name.
The "!" is a small orange/yellow mark at the far left of the row.
Circular icons (skill type badges) are NOT the "!" indicator.
→ Extract ONLY skills with the "!" mark. Ignore skills without "!".

**Type B — Single-skill card screen (Style / Harmonized / Duo):**
This screen shows a single skill in a large card format, without a "Skills learnable" header and without "!" marks.
→ Extract the skill displayed on the card.

If the screen does not match either type, return an empty array [].

For each extracted skill, provide:
- skill_name: string — Skill name
- skill_type: string — One of "Weapon", "Special", "Assist", "Passive A", "Passive B", "Passive C", "Harmonized"
- weapon_type: string|null — Weapon type (for weapons only)
- might: integer|null — Might (for weapons only)
- range: integer|null — Range (for weapons only)
- special_count: integer|null — Special cooldown (for specials only)
- description: string[] — Skill effect text (array of lines)
- hero_name: string|null — Hero name shown on this screen

Description line-break rules:
""" + ocr_module.EN_LINEBREAK_RULES + """

Important:
- Transcribe text exactly as shown. Do not correct or paraphrase.
- Use half-width numbers.

Output as JSON array only (no other text):
```json
[{"skill_name": "Heroic Maltet", "skill_type": "Weapon", ...}]
```"""


# === 正解ファイルパーサ（verify_ocr_crop.py から再利用） ===


def parse_ground_truth(path: Path) -> list[dict]:
    """正解ファイルをパースしてスキルブロックのリストを返す"""
    text = path.read_text(encoding="utf-8")
    blocks = text.strip().split("\n\n")
    skills = []
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue
        header = lines[0]
        parts = header.split("-", 3)
        skill_id = int(parts[0])
        jp_name = parts[2] if len(parts) >= 3 else ""

        metadata_lines = []
        desc_lines = []
        for line in lines[1:]:
            if line.startswith("##"):
                metadata_lines.append(line)
            else:
                desc_lines.append(line)

        skills.append({
            "id": skill_id,
            "name": jp_name,
            "metadata_lines": metadata_lines,
            "description": "\n".join(desc_lines),
        })
    return skills


def normalize_text(text: str) -> str:
    """比較用にテキストを正規化"""
    for search, replace in TEXT_REPLACEMENTS:
        text = text.replace(search, replace)
    text = re.sub(r'\s+', '', text)
    return text


def parse_ocr_result(path: Path) -> list[dict]:
    """format_output() の出力をパースしてスキルブロックのリストを返す"""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks = text.strip().split("\n\n")
    skills = []
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue
        header = lines[0]
        header = re.sub(r'\s*#\s*TODO.*$', '', header)
        parts = header.split("-", 3)
        jp_name = parts[2] if len(parts) >= 3 else ""

        metadata_lines = []
        desc_lines = []
        for line in lines[1:]:
            if line.startswith("##"):
                metadata_lines.append(line)
            else:
                desc_lines.append(line)

        skills.append({
            "name": jp_name,
            "metadata_lines": metadata_lines,
            "description": "\n".join(desc_lines),
        })
    return skills


# === 比較 ===


def _match_skills(gt_skills: list[dict], ocr_skills: list[dict]) -> list[tuple[dict, dict]]:
    """正解とOCR結果を名前ベースでマッチング"""
    pairs = []
    used_ocr = set()
    for gt in gt_skills:
        gt_norm = normalize_text(gt["name"])
        best_idx = None
        best_sim = 0.0
        for i, ocr_skill in enumerate(ocr_skills):
            if i in used_ocr:
                continue
            ocr_norm = normalize_text(ocr_skill["name"])
            sim = difflib.SequenceMatcher(None, gt_norm, ocr_norm).ratio()
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        if best_idx is not None and best_sim > 0.3:
            pairs.append((gt, ocr_skills[best_idx]))
            used_ocr.add(best_idx)
    return pairs


def compare_skills(gt_skills: list[dict], ocr_skills: list[dict], label: str) -> dict:
    """正解とOCR結果を比較してレポートデータを返す"""
    results = {
        "label": label,
        "gt_count": len(gt_skills),
        "ocr_count": len(ocr_skills),
        "name_matches": 0,
        "meta_matches": 0,
        "desc_similarities": [],
        "details": [],
    }

    matched_pairs = _match_skills(gt_skills, ocr_skills)

    for gt, ocr_skill in matched_pairs:
        detail = {"id": gt["id"], "name": gt["name"]}

        # 名前比較
        name_match = normalize_text(gt["name"]) == normalize_text(ocr_skill["name"])
        detail["name_match"] = name_match
        if name_match:
            results["name_matches"] += 1

        # メタデータ比較
        gt_meta = "\n".join(gt["metadata_lines"])
        ocr_meta = "\n".join(ocr_skill["metadata_lines"])
        meta_match = normalize_text(gt_meta) == normalize_text(ocr_meta)
        detail["meta_match"] = meta_match
        if meta_match:
            results["meta_matches"] += 1

        # 説明文類似度
        gt_desc = normalize_text(gt["description"])
        ocr_desc = normalize_text(ocr_skill["description"])
        similarity = difflib.SequenceMatcher(None, gt_desc, ocr_desc).ratio() * 100
        detail["desc_similarity"] = similarity
        results["desc_similarities"].append(similarity)

        # 差分（不一致時のみ）
        if similarity < 100.0:
            diff = list(difflib.unified_diff(
                gt["description"].split("\n"),
                ocr_skill["description"].split("\n"),
                fromfile="正解",
                tofile=label,
                lineterm="",
            ))
            detail["diff"] = diff
        else:
            detail["diff"] = []

        results["details"].append(detail)

    # マッチしなかったOCRスキル
    matched_ocr_indices = {id(ocr_skill) for _, ocr_skill in matched_pairs}
    unmatched = [s for s in ocr_skills if id(s) not in matched_ocr_indices]
    results["unmatched_ocr"] = [s["name"] for s in unmatched]

    return results


# === レポート出力 ===


def print_report(gt_skills: list[dict], baseline_result: dict | None, proposed_result: dict | None):
    """比較レポートを出力"""
    print("=== OCRプロンプト検証レポート ===")
    gt_count = len(gt_skills)
    id_range = f"{gt_skills[0]['id']}-{gt_skills[-1]['id']}" if gt_skills else "N/A"
    print(f"正解: {gt_count}スキル (ID {id_range})")
    print()

    # 検出数
    print("--- 検出数 ---")
    header = f"{'':14s}{'正解':>8s}"
    if baseline_result:
        header += f"{'Baseline':>12s}"
    if proposed_result:
        header += f"{'Proposed':>12s}"
    print(header)

    row = f"{'スキル数:':14s}{gt_count:>8d}"
    if baseline_result:
        row += f"{baseline_result['ocr_count']:>12d}"
    if proposed_result:
        row += f"{proposed_result['ocr_count']:>12d}"
    print(row)
    print()

    # スキル別比較
    print("--- スキル別比較 ---")
    for gt in gt_skills:
        sid = gt["id"]
        print(f"#{sid} {gt['name']}")

        bl_detail = _find_detail(baseline_result, sid) if baseline_result else None
        pr_detail = _find_detail(proposed_result, sid) if proposed_result else None

        # 名前
        parts = ["  名前: "]
        if bl_detail:
            mark = "✓" if bl_detail["name_match"] else "✗"
            parts.append(f"baseline={mark}")
        if pr_detail:
            mark = "✓" if pr_detail["name_match"] else "✗"
            parts.append(f"  proposed={mark}")
        print("".join(parts))

        # メタ
        parts = ["  メタ: "]
        if bl_detail:
            mark = "✓" if bl_detail["meta_match"] else "✗"
            parts.append(f"baseline={mark}")
        if pr_detail:
            mark = "✓" if pr_detail["meta_match"] else "✗"
            parts.append(f"  proposed={mark}")
        print("".join(parts))

        # 説明文
        parts = ["  説明: "]
        if bl_detail:
            parts.append(f"baseline={bl_detail['desc_similarity']:.1f}%")
        if pr_detail:
            parts.append(f"  proposed={pr_detail['desc_similarity']:.1f}%")
        print("".join(parts))

        # 差分表示
        for label, detail in [("baseline", bl_detail), ("proposed", pr_detail)]:
            if detail and detail["diff"]:
                print(f"  [{label} diff]:")
                for line in detail["diff"]:
                    print(f"    {line}")

        print()

    # 集計
    print("--- 集計 ---")
    header = f"{'':14s}"
    if baseline_result:
        header += f"{'Baseline':>14s}"
    if proposed_result:
        header += f"{'Proposed':>14s}"
    print(header)

    # 名前一致
    row = f"{'名前一致:':14s}"
    if baseline_result:
        s = f"{baseline_result['name_matches']}/{len(baseline_result['details'])}"
        row += f"{s:>14s}"
    if proposed_result:
        s = f"{proposed_result['name_matches']}/{len(proposed_result['details'])}"
        row += f"{s:>14s}"
    print(row)

    # メタ一致
    row = f"{'メタ一致:':14s}"
    if baseline_result:
        s = f"{baseline_result['meta_matches']}/{len(baseline_result['details'])}"
        row += f"{s:>14s}"
    if proposed_result:
        s = f"{proposed_result['meta_matches']}/{len(proposed_result['details'])}"
        row += f"{s:>14s}"
    print(row)

    # 説明文類似度
    for metric_name, func in [("説明avg:", lambda sims: sum(sims) / len(sims)),
                               ("説明min:", lambda sims: min(sims))]:
        row = f"{metric_name:14s}"
        if baseline_result and baseline_result["desc_similarities"]:
            row += f"{func(baseline_result['desc_similarities']):>13.1f}%"
        if proposed_result and proposed_result["desc_similarities"]:
            row += f"{func(proposed_result['desc_similarities']):>13.1f}%"
        print(row)

    # マッチなしスキル
    for result in [baseline_result, proposed_result]:
        if result and result["unmatched_ocr"]:
            print(f"\n  [{result['label']}] マッチなし: {', '.join(result['unmatched_ocr'])}")

    # リグレッション判定
    print()
    if baseline_result and proposed_result:
        _check_regression(baseline_result, proposed_result)


def _find_detail(result: dict | None, skill_id: int) -> dict | None:
    if result is None:
        return None
    for d in result["details"]:
        if d["id"] == skill_id:
            return d
    return None


def _check_regression(baseline: dict, proposed: dict):
    """リグレッション判定"""
    print("--- リグレッション判定 ---")
    regressions = []

    # 名前一致
    if proposed["name_matches"] < baseline["name_matches"]:
        regressions.append(
            f"名前一致: {baseline['name_matches']} → {proposed['name_matches']}"
        )

    # メタ一致
    if proposed["meta_matches"] < baseline["meta_matches"]:
        regressions.append(
            f"メタ一致: {baseline['meta_matches']} → {proposed['meta_matches']}"
        )

    # 説明文平均
    if baseline["desc_similarities"] and proposed["desc_similarities"]:
        bl_avg = sum(baseline["desc_similarities"]) / len(baseline["desc_similarities"])
        pr_avg = sum(proposed["desc_similarities"]) / len(proposed["desc_similarities"])
        if pr_avg < bl_avg - 0.5:
            regressions.append(f"説明avg: {bl_avg:.1f}% → {pr_avg:.1f}%")

        # 説明文最低値
        bl_min = min(baseline["desc_similarities"])
        pr_min = min(proposed["desc_similarities"])
        if pr_min < bl_min - 2.0:
            regressions.append(f"説明min: {bl_min:.1f}% → {pr_min:.1f}%")

    # スキル別の名前リグレッション
    for bl_d in baseline["details"]:
        pr_d = _find_detail(proposed, bl_d["id"])
        if pr_d and bl_d["name_match"] and not pr_d["name_match"]:
            regressions.append(f"#{bl_d['id']} {bl_d['name']}: 名前一致 ✓→✗")

    if regressions:
        print("FAIL: リグレッション検出")
        for r in regressions:
            print(f"  - {r}")
    else:
        print("PASS: リグレッションなし")


# === プロンプト差し替え ===


def apply_proposed_prompts():
    """提案プロンプトをocr_moduleにmonkey-patch"""
    ocr_module.JP_USER_PROMPT_SINGLE_CARD = PROPOSED_JP_USER_PROMPT_SINGLE_CARD
    ocr_module.JP_USER_PROMPT_NEW_ONLY = PROPOSED_JP_USER_PROMPT_NEW_ONLY
    ocr_module.EN_USER_PROMPT_SINGLE_CARD = PROPOSED_EN_USER_PROMPT_SINGLE_CARD
    ocr_module.EN_USER_PROMPT_NEW_ONLY = PROPOSED_EN_USER_PROMPT_NEW_ONLY


def save_baseline_prompts() -> dict[str, str]:
    """現在のプロンプトを保存"""
    return {
        "JP_USER_PROMPT_SINGLE_CARD": ocr_module.JP_USER_PROMPT_SINGLE_CARD,
        "JP_USER_PROMPT_NEW_ONLY": ocr_module.JP_USER_PROMPT_NEW_ONLY,
        "EN_USER_PROMPT_SINGLE_CARD": ocr_module.EN_USER_PROMPT_SINGLE_CARD,
        "EN_USER_PROMPT_NEW_ONLY": ocr_module.EN_USER_PROMPT_NEW_ONLY,
    }


def restore_baseline_prompts(saved: dict[str, str]):
    """保存したプロンプトを復元"""
    for key, value in saved.items():
        setattr(ocr_module, key, value)


# === メイン処理 ===


def run_ocr_mode(
    frame_groups: list[FrameGroup],
    output_dir: Path,
    start_id: int,
    label: str,
    ocr_backend: str = "gemini",
) -> Path:
    """OCRを実行して結果ファイルを保存"""
    # カードクロップ
    crop_output = output_dir / "cards"
    crop_output.mkdir(parents=True, exist_ok=True)
    crop_frame_groups(frame_groups, str(crop_output))

    backend = create_backend(ocr_backend)
    jp_skills = backend.ocr_jp_skills(frame_groups, new_only=True)
    print(f"[{label}] OCR結果: {len(jp_skills)}スキル検出")

    # API呼び出し数
    if hasattr(backend, "api_call_count"):
        print(f"[{label}] API呼び出し: {backend.api_call_count}回")

    content = format_output(jp_skills, None, start_id=start_id)

    result_path = output_dir / "ocr_result.txt"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(content, encoding="utf-8")
    print(f"[{label}] 保存: {result_path}")

    return result_path


def main():
    parser = argparse.ArgumentParser(description="OCRプロンプト改善A/B検証")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".work/10-03-06"),
        help="テストデータパス (default: .work/10-03-06)",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=None,
        help="正解ファイルパス",
    )
    parser.add_argument("--start-id", type=int, default=3581, help="開始ID (default: 3581)")
    parser.add_argument(
        "--prompt-version",
        choices=["baseline", "proposed", "both"],
        default="both",
        help="テスト対象 (default: both)",
    )
    parser.add_argument("--skip-ocr", action="store_true", help="OCRスキップ、保存済み結果で再比較")
    parser.add_argument(
        "--ocr",
        default="gemini",
        choices=["claude", "gemini", "ollama"],
        help="OCRバックエンド (default: gemini)",
    )
    args = parser.parse_args()

    # パス解決
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = args.data_dir if args.data_dir.is_absolute() else base_dir / args.data_dir
    if args.ground_truth:
        gt_path = args.ground_truth if args.ground_truth.is_absolute() else base_dir / args.ground_truth
    else:
        gt_path = base_dir / "data" / "10-03-06" / "annotations" / "ocr_ground_truth.txt"

    if not gt_path.exists():
        print(f"エラー: 正解ファイルが見つかりません: {gt_path}", file=sys.stderr)
        sys.exit(1)

    gt_skills = parse_ground_truth(gt_path)
    print(f"正解ファイル: {gt_path} ({len(gt_skills)}スキル)")

    run_baseline = args.prompt_version in ("baseline", "both")
    run_proposed = args.prompt_version in ("proposed", "both")

    baseline_dir = data_dir / "verify_baseline"
    proposed_dir = data_dir / "verify_proposed"

    if not args.skip_ocr:
        # フレーム読み込み + FrameGroup構築
        frames_dir = data_dir / "frames" / "jp"
        frame_paths = sorted(str(p) for p in frames_dir.glob("frame_*.png"))
        if not frame_paths:
            print(f"エラー: フレームが見つかりません: {frames_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"フレーム数: {len(frame_paths)}")

        skill_frames = detect_skill_frames(frame_paths)
        print(f"スキル画面: {len(skill_frames)}")

        base_groups = deduplicate_frames(skill_frames)
        print(f"FrameGroup数: {len(base_groups)}")

        saved_prompts = save_baseline_prompts()

        if run_baseline:
            print("\n--- Run A: Baseline ---")
            restore_baseline_prompts(saved_prompts)
            groups = copy.deepcopy(base_groups)
            run_ocr_mode(groups, baseline_dir, args.start_id, label="baseline", ocr_backend=args.ocr)

        if run_proposed:
            print("\n--- Run B: Proposed ---")
            apply_proposed_prompts()
            groups = copy.deepcopy(base_groups)
            run_ocr_mode(groups, proposed_dir, args.start_id, label="proposed", ocr_backend=args.ocr)

        # 復元
        restore_baseline_prompts(saved_prompts)
    else:
        print("OCRスキップ: 保存済み結果を使用")

    # 比較
    print("\n")
    baseline_result = None
    proposed_result = None

    if run_baseline:
        bl_path = baseline_dir / "ocr_result.txt"
        if bl_path.exists():
            bl_ocr = parse_ocr_result(bl_path)
            baseline_result = compare_skills(gt_skills, bl_ocr, "Baseline")
        else:
            print(f"警告: baseline結果なし: {bl_path}", file=sys.stderr)

    if run_proposed:
        pr_path = proposed_dir / "ocr_result.txt"
        if pr_path.exists():
            pr_ocr = parse_ocr_result(pr_path)
            proposed_result = compare_skills(gt_skills, pr_ocr, "Proposed")
        else:
            print(f"警告: proposed結果なし: {pr_path}", file=sys.stderr)

    if baseline_result or proposed_result:
        print_report(gt_skills, baseline_result, proposed_result)
    else:
        print("比較対象がありません。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
