import os
import sys
import re


def replace_in_file(input_file, output_file, replacements):
    with open(input_file, 'r', encoding='utf-8') as infile:
        content = infile.read()
        
    for search, replace in replacements:
        content = content.replace(search, replace)

    check_content(content)
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write(content)

def check_content(content):
    warning_words = [
        '可能戦闘中'
        '軽減奥義',
        '計算自分から',
        '、<br>',
    ]
    for word in warning_words:
        if word in content:
            print(f"[WARN] {word}が含まれます 本文: {content}")

    patterns = [
        # 行頭、<br>以外に続く暗器効果(文の途中に出てくる)
        r"(?<!^)(?<!<br>)【暗器\([0-9]\)】",
    ]
    for pattern in patterns:
        if re.search(pattern, content):
            print(f"[WARN] {pattern}が含まれます 本文: {content}")

def main(input_directory, output_directory):
    if not os.path.isdir(input_directory):
        print(f"Error: Input directory '{input_directory}' does not exist.")
        sys.exit(1)

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    replacements = [
        (' ', ''),
        ('增幅', '増幅'),
        ('擊', '撃'),
        ('守備魔防', '守備、魔防'),
        ('攻撃速さ', '攻撃、速さ'),
        ('－', '-'),
        ('~', '～'),
        ('備ー', '備-'),
        ('撃ー', '撃-'),
        ('さー', 'さ-'),
        ('防ー', '防-'),
        ('Pー', 'P-'),
        ('ダメージー', 'ダメージ-'),
        ('カウントー', 'カウント-'),
        ('量ー', '量-'),
        ('＋', '+'),
        ('x', '×'),
        ('✕', '×'),
        ('（', '('),
        ('）', ')'),
        ('奥盖', '奥義'),
        ('值', '値'),
        (',', '、'),
        ('.', '、'),
        ('天顔', '天脈'),
        ('最大倍', '最大値'),
        ('自身の奥義発動カウント変動量を無効', '自身の奥義発動カウント変動量-を無効'),
        ('ダメージを%軽減','ダメージを○○%軽減'),
        ('ダメージ+×', 'ダメージ+○×'),
        ('ダメージ+0×', 'ダメージ+○×'),
        ('（0は', '（○は'),
        ('〇', '○'),
        ('。', '、'),
        ('◎', '○'),
        ('\n', '<br>'),  # Unix/Linux/macOS の LF をスペースに置換
        ('\r\n', '<br>'), # Windows の CRLF をスペースに置換
    ]

    for filename in os.listdir(input_directory):
        if filename.endswith('.txt'):
            input_file = os.path.join(input_directory, filename)
            output_file = os.path.join(output_directory, filename)
            replace_in_file(input_file, output_file, replacements)

    print("Replacement completed.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python replace_in_directory.py <input_directory> <output_directory>")
        sys.exit(1)

    input_directory = sys.argv[1]
    output_directory = sys.argv[2]
    main(input_directory, output_directory)