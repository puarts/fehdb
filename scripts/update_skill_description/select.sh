#!/bin/bash

# データベース名
DATABASE="feh-skills.sqlite3"

# テーブル名
TABLE_NAME="skills"

# 引数でディレクトリを指定
FILES_DIR="$1"

# ディレクトリが指定されていない場合はエラーを表示
if [[ -z "$FILES_DIR" ]]; then
    echo "Error: No directory specified."
    exit 1
fi

# 指定されたディレクトリが存在しない場合はエラーを表示
if [[ ! -d "$FILES_DIR" ]]; then
    echo "Error: $FILES_DIR does not exist."
    exit 1
fi

# ディレクトリ内の全ての .txt ファイルを取得
for file_path in "$FILES_DIR"/*.txt; do

    # ID をファイル名から取得 (拡張子を取り除く)
    id=$(basename "$file_path" .txt)

    # SQLite コマンドを使用して ID を SELECT
    sqlite3 $DATABASE <<EOF
SELECT id,name,description,refine_description,refine_description2,special_refine_description FROM $TABLE_NAME WHERE id = '$id';
EOF

    echo
done
