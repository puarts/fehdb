#!/bin/bash

# データベース名
DATABASE="feh-skills.sqlite3"

# テーブル名
TABLE_NAME="skills"

# 引数からディレクトリを取得
FILES_DIR="$1"
DESCRIPTION_FIELD="$2"

# ディレクトリ内のすべての.txtファイルを処理
for file_path in "$FILES_DIR"/*.txt; do
    # ファイルの存在を確認
    if [[ ! -f "$file_path" ]]; then
        echo "Error: $file_path does not exist."
        continue
    fi

    # ID をファイル名から取得 (拡張子を取り除く)
    id=$(basename "$file_path" .txt)

    # テキストファイルの内容を読み込む
    description=$(cat "$file_path")

    # SQLite コマンドを使用して INSERT または UPDATE を実行
    sqlite3 $DATABASE <<EOF
    -- テーブルの ID に基づいて description フィールドを更新
    UPDATE $TABLE_NAME
    SET $DESCRIPTION_FIELD = '$description'
    WHERE id = '$id';
EOF
    # insert or update
#    sqlite3 $DATABASE <<EOF
#-- テーブルに ID が存在するか確認
#INSERT INTO $TABLE_NAME (id, $DESCRIPTION_FIELD)
#VALUES ('$id', '$description')
#ON CONFLICT(id) DO UPDATE SET $DESCRIPTION_FIELD=excluded.$DESCRIPTION_FIELD;
#EOF
    echo "Processed: $(basename "$file_path")"
done