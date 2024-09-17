from typing import Tuple
from typing import List
from replace import replace
from replace import REPLACEMENTS


def parse_file(filename: str) -> List[Tuple[str, str]]:
    content = read_file(filename)  # ファイルの内容を取得し、前後の空白を除去
    entries = content.split("\n\n")
    result = []
    for entry in entries:
        parsed_entry = parse_entry(entry)
        if parsed_entry:
            result.append(parsed_entry)
    return result


def read_file(filename: str) -> str:
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read().strip()


def parse_entry(entry: str) -> Tuple[str, str]:
    # コメント行を除去
    lines = entry.split("\n")
    lines = [line for line in lines if not line.strip().startswith("#")]
    if len(lines) >= 2:
        entry_id = lines[0].strip()  # 1行目がentry_id
        description = "\n".join(lines[1:]).strip()  # 2行目以降をdescriptionとして結合
        replaced = replace(description, REPLACEMENTS)
        return entry_id, replaced


def main():
    # ファイルからid, descriptionのペアを抽出して表示
    # filename = 'your_file.txt'
    filename = './../../sources/skill-desc/8-9-17.txt'
    pairs = parse_file(filename)
    for pair in pairs:
        print(pair)


if __name__ == '__main__':
    main()
