import re
from typing import List
from typing import Tuple

from replace import REPLACEMENTS
from replace import replace


def parse_file(filename: str) -> List[Tuple[str, str, dict]]:
    """
    Args:
        filename:

    Returns:
        1行目、2行目以降のテキスト、その他のフィールド(キラー効果など)に分割したものを返す
        2行目以降の改行については<br>に置き換えられる
    """
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


def parse_entry(entry: str) -> Tuple[str, str, dict]:
    # コメント行を除去
    entries = entry.split("\n")
    skill_lines = [line for line in entries if not line.strip().startswith('#')]
    fields_comments = [line for line in entries if line.strip().startswith('##')]
    if len(skill_lines) >= 2:
        entry_id = skill_lines[0].strip()  # 1行目がentry_id
        description = "\n".join(skill_lines[1:]).strip()  # 2行目以降をdescriptionとして結合
        replaced = replace(description, REPLACEMENTS)
        field_dict = get_field_dict(replaced.split('<br>'), fields_comments)
        return entry_id, replaced, field_dict


def get_field_dict(descriptions: List[str], fields_comments: List[str]) -> dict:
    return {**get_field_dict_from_description(descriptions), **get_field_dict_from_comments(fields_comments)}


def get_field_dict_from_description(descriptions: List[str]) -> dict:
    result = {}
    for description in descriptions:
        description = description.strip()
        if description == '奥義が発動しやすい(発動カウント-1)':
            result['cooldown_count'] = -1
        elif description == '自分から攻撃した時、2回攻撃':
            result['atk_count'] = 2
    return result


def get_field_dict_from_comments(comments: List[str]) -> dict:
    result = {}
    for comment in comments:
        comment = comment.replace('##', '').strip()
        for field in comment.split(','):
            field = field.strip()
            # w-rs: 剣
            # [asdr]-3: 攻撃、速さ、守備、魔防-3
            if '-' in field:
                prefix, suffix = field.split('-')
                if prefix == 'w':
                    _set_weapon(suffix, result)
                else:
                    # [asdr]-3: 攻撃、速さ、守備、魔防-3
                    _set_stats(prefix, -int(suffix), result)
            if '+' in field:
                prefix, suffix = field.split('+')
                # [asdr]+3: 攻撃、速さ、守備、魔防+3
                _set_stats(prefix, int(suffix), result)
            else:
                # ex) s: 奥義
                _set_type(field, result)
                # ex) @2: カウント2
                _set_count(field, result)
                ## 威力：14
                _set_might(field, result)
    return result


def _set_weapon(suffix: str, result: dict):
    result['type'] = '武器'
    if suffix == 'rs':
        result['weapon_type'] = '剣'
    elif suffix == 'bl':
        result['weapon_type'] = '槍'
    elif suffix == 'ga':
        result['weapon_type'] = '斧'
    elif suffix == 'bo':
        result['weapon_type'] = '弓'
    elif suffix == 'cs':
        result['weapon_type'] = '杖'
    elif suffix == 'br':
        result['weapon_type'] = '竜石'
    elif suffix == 'be':
        result['weapon_type'] = '獣'
    else:
        if len(suffix) >= 2:
            result['weapon_type'] = f"{_get_weapon_color(suffix[0])}{_get_weapon_type(suffix[1])}"


def _get_weapon_color(color: str) -> str:
    return {
        'r': '赤',
        'b': '青',
        'g': '緑',
        'c': '無',
    }[color]


def _get_weapon_type(weapon_type: str) -> str:
    return {
        't': '魔法',
    }[weapon_type]


def _set_stats(stats: str, value: int, result: dict):
    for stat in stats:
        if stat == 'a':
            result['atk'] = value
        if stat == 's':
            result['spd'] = value
        if stat == 'd':
            result['def'] = value
        if stat == 'r':
            result['res'] = value


def _set_type(type_str: str, result: dict):
    if type_str == 's':
        result['type'] = '奥義'
    if type_str == 'a':
        result['type'] = 'サポート'
    if type_str == 'pa':
        result['type'] = 'パッシブA'
    if type_str == 'pb':
        result['type'] = 'パッシブB'
    if type_str == 'pc':
        result['type'] = 'パッシブC'
    if type_str == 'px':
        result['type'] = '響心'


def _set_count(count_str: str, result: dict):
    if count_str.startswith('@'):
        count = int(count_str.replace('@', ''))
        result['count'] = count


def _set_might(might_str: str, result: dict):
    match = re.match(r'威力[:：](?P<num>\d+)', might_str)
    if match:
        result['might'] = int(match.group('num'))


def main():
    # ファイルからid, descriptionのペアを抽出して表示
    # filename = 'your_file.txt'
    filename = './../../sources/skill-desc/8-9-17.txt'
    pairs = parse_file(filename)
    for pair in pairs:
        print(pair)


if __name__ == '__main__':
    main()
