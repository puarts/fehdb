import os
import sys
import re

from util import warn

REPLACEMENTS = [
    (' ', ''),
    ('自車', '自軍'),
    ('增幅', '増幅'),
    ('擊', '撃'),
    ('収撃', '攻撃'),
    ('寸備', '守備'),
    ('守備魔防', '守備、魔防'),
    ('攻撃速さ', '攻撃、速さ'),
    ('－', '-'),
    ('攻撃一', '攻撃-'),
    ('速さ一', '速さ-'),
    ('守備一', '守備-'),
    ('魔防一', '魔防-'),
    ('~', '～'),
    ('備ー', '備-'),
    ('撃ー', '撃-'),
    ('さー', 'さ-'),
    ('防ー', '防-'),
    ('Pー', 'P-'),
    ('ダメージー', 'ダメージ-'),
    ('カウントー', 'カウント-'),
    ('量ー', '量-'),
    ('速さ条件一', '速さ条件-'),
    ('条件を一', '条件を-'),
    ('ダメージ-フ', 'ダメージ-7'),
    ('攻撃-フ', '攻撃-7'),
    ('速さ-フ', '速さ-7'),
    ('守備-フ', '守備-7'),
    ('魔防-フ', '魔防-7'),
    ('ダメージ-て', 'ダメージ-7'),
    ('攻撃-て', '攻撃-7'),
    ('速さ-て', '速さ-7'),
    ('守備-て', '守備-7'),
    ('魔防-て', '魔防-7'),
    ('ダメージ-Z', 'ダメージ-7'),
    ('攻撃-Z', '攻撃-7'),
    ('速さ-Z', '速さ-7'),
    ('守備-Z', '守備-7'),
    ('魔防-Z', '魔防-7'),
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
    ('児の護り手', '兜の護り手'),
    ('化身状なら', '化身状態なら'),
    ('双界効果・香', '双界効果・盾'),
    ('自身の奥義発動カウント変動量を無効', '自身の奥義発動カウント変動量-を無効'),
    ('ダメージを%軽減', 'ダメージを○○%軽減'),
    ('ダメージ+×', 'ダメージ+○×'),
    ('ダメージ+0×', 'ダメージ+○×'),
    ('ダメージ+0,', 'ダメージ+○,'),
    ('ダメージ+O,', 'ダメージ+○,'),
    ('（0は', '（○は'),
    ('〇', '○'),
    ('。', '、'),
    ('◎', '○'),
    ('●', '○'),
    ('：', ':'),
    ('\n', '<br>'),  # Unix/Linux/macOS の LF をスペースに置換
    ('\r\n', '<br>'),  # Windows の CRLF をスペースに置換
]


def replace(input_text, replacements):
    result = input_text
    for search_word, replace_word in replacements:
        result = result.replace(search_word, replace_word)
    check_content(result)
    return result


def replace_in_file(input_file, output_file, replacements):
    with open(input_file, 'r', encoding='utf-8') as infile:
        content = infile.read()

    content = replace(content, replacements)

    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write(content)


def check_content(content):
    warning_words = [
        '可能戦闘中'
        '軽減奥義',
        '計算自分から',
        '、<br>',
        'かっ',
    ]
    for word in warning_words:
        if word in content:
            print(warn(f"{word}が含まれます 本文: {content}"))

    patterns = [
        # 行頭、<br>以外に続く暗器効果(文の途中に出てくる)
        r'(?<!^)(?<!<br>)【暗器\([0-9]\)】',
        # ひらがな (\u3040-\u309F)、カタカナ (\u30A0-\u30FF)、および漢字 (\u4E00-\u9FAF)
        # 反撃する<br>か反撃する、がおそらく正しい
        r'距離に関係なく反撃する[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+',
        r'[0-9]戦闘開始時',
        r'[0-9]周囲',
        r'\([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{1,10}】',
        r'【[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{1,10}\)',
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            print(warn(f"{pattern}が含まれます match: {match}, 本文: {content}"))


def main(input_dir, output_dir):
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist.")
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    replacements = REPLACEMENTS
    for filename in os.listdir(input_dir):
        if filename.endswith('.txt'):
            input_file = os.path.join(input_dir, filename)
            output_file = os.path.join(output_dir, filename)
            replace_in_file(input_file, output_file, replacements)

    print("Replacement completed.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python replace_in_directory.py <input_directory> <output_directory>")
        sys.exit(1)

    input_directory = sys.argv[1]
    output_directory = sys.argv[2]
    main(input_directory, output_directory)
