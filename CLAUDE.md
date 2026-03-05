# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリで作業する際のガイダンスを提供します。

## プロジェクト概要

ファイアーエムブレム ヒーローズ (FEH) のデータベース管理システム。英雄のステータス、スキルデータ、ストーリーの会話、CYL投票結果をSQLiteデータベースで管理する。公式紹介動画やゲームスクリーンショットからOCRでスキル説明文を取り込む処理パイプラインと、外部の戦闘シミュレータ向けにTypeScript/JavaScriptデータを出力するコードジェネレータを含む。

ゲームデータおよびコメントはすべて日本語。

## セットアップとコマンド

```bash
# 依存関係のインストール（uvパッケージマネージャが必要）
uv sync

# スキル説明文をデータベースに挿入・更新
python scripts/update_skill_description/query.py <input_file>
python scripts/update_skill_description/query.py --dry-run <input_file>   # DB書き込みなしで検証
python scripts/update_skill_description/query.py --check-id <input_file>  # スキルIDの存在確認

# データベースをCSV/SQLにエクスポート
bash dumps/dump-description.sh    # dumps/ ディレクトリから実行

# 外部シミュレータ向けTypeScript英雄・スキルデータの生成
python create_hero_infos.py
python create_skill_info.py

# 誕生日TSVファイルの生成
python scripts/python/create_birthday_list_tsv.py

# 公式動画からスキル説明文を自動抽出（詳細は scripts/extract_from_video/README.md）
cd scripts/extract_from_video
uv run python main.py --jp-url "<JP動画URL>" --en-url "<EN動画URL>" -o "<出力ファイル名>"
```

## アーキテクチャ

### 動画自動抽出パイプライン（`scripts/extract_from_video/`）

公式紹介動画からスキル説明文を自動抽出し、`query.py` 互換の `.txt` ファイルを出力する：

1. **yt-dlp** — YouTube動画ダウンロード（1080p）
2. **ffmpeg freezedetect** — 静止区間検出 → 中間フレーム抽出
3. **色分析 + パーセプチュアルハッシュ** — スキル画面候補の検出・重複除去
4. **OCR**（Claude Vision API / Ollama VLM）— フレーム画像から構造化JSONデータを抽出
5. **JP/ENマッチング + テキスト正規化** → `sources/skill-desc/{date}.txt` を出力

詳細は `scripts/extract_from_video/README.md` を参照。

### スキル説明文パイプライン（`scripts/update_skill_description/`）

OCR結果のテキストファイルを構造化されたデータベースエントリに変換するワークフロー：

1. **replace.py** — テキスト正規化：OCR文字誤りの修正、全角→半角変換、スペース除去、改行を`<br>`に変換
2. **parse_file.py** — 正規化テキストを構造化されたスキルエントリにパース：スキルID、名前、錬成タイプ、メタデータコメント（武器種、威力、ステータス）を抽出
3. **query.py** — パースされた説明文で `feh-skills.sqlite3` を挿入・更新

### スキル説明文ファイルフォーマット

`.txt` ファイルの各スキルエントリの構造：
```
[skill_id]-[錬成タイプ]-[スキル名]
## w-[武器コード]
## 威力：[威力] 射程：[射程]
[説明文テキスト（改行は<br>で表現）]
```

錬成タイプ: `n`（新規）、`nr`（新規＋錬成）、`r`（錬成）、`s`（特殊錬成）、`s3`（特殊錬成＋HPボーナス）

武器コード: `rs`（剣）、`bl`（槍）、`ga`（斧）、`bo`（弓）、`da`（暗器）、`cs`（杖）、`br`（竜）、`be`（獣）、`rt/bt/gt/ct`（赤/青/緑/無属性魔法）

メタデータコメントの接頭辞: `## w-`（武器種）、`## @N`（奥義カウント）、`## h+N/a+N/s+N/d+N/r+N`（ステータスボーナス）、`## s/a/pa/pb/pc/px`（スキル種別）

### データベース

- **feh-skills.sqlite3** — スキルテーブル（約40カラム：id、name、description、ステータス、継承ルール、錬成データ）
- **feh-heroes.sqlite3** — 英雄テーブル（Lv1/Lv40のステータス、パイプ区切りのスキル文字列、メタデータ）
- **feh.sqlite3** — シリーズ・タイトルデータ
- **feh-cyl.sqlite3** — 英雄総選挙の投票データ
- **feh-story.sqlite3** — ストーリーの会話データ

### コードジェネレータ

`create_hero_infos.py` と `create_skill_info.py` はSQLiteデータベースから読み取り、外部のFEH戦闘シミュレータ向けにJavaScriptの `const` 宣言を出力する。日本語のフィールド値をTypeScriptのenumにマッピングする。

## 規約

- Python 3.12+、`uv` ワークスペースで管理（ルートに `pyproject.toml`、`scripts/update_skill_description/` と `scripts/extract_from_video/` がワークスペースメンバー）
- SQLiteは生SQL使用（ORMなし）。真偽値は文字列 `'true'`/`'false'` で保存
- 配列的なフィールドはパイプ `|` を区切り文字として使用
- コミットメッセージは日本語（例：「DB更新」）
- ファイルエンコーディングはすべてUTF-8
