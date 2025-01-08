import argparse
import re
import sqlite3
import sys
from typing import List, Tuple

from unidecode import unidecode

from parse_file import parse_file
from util import warn


def insert_data(conn, data: List[Tuple[str, str, dict]]) -> None:
    """
    データをテーブルに挿入する関数

    :param conn:
    :param data: (info, description, dict) のタプルのリスト
    """
    cursor = conn.cursor()
    for info, description, other_field_dict in data:
        split = info.split('-')
        skill_id, refinement_type, skill_name = split
        skill_e_name = None
        if len(split) == 4:
            skill_e_name = split[3]
        print(skill_id, skill_e_name, refinement_type, skill_name, description)
        fields = ''
        is_refinement = False
        is_special_refinement = False
        special_refine_hp = 0
        if refinement_type == 'n':
            fields = ['id', 'name', 'description']
        elif refinement_type == 'r':
            fields = ['id', 'name', 'refine_description']
            is_refinement = True
        elif refinement_type == 's':
            fields = ['id', 'name', 'special_refine_description']
            is_refinement = True
            is_special_refinement = True
        elif refinement_type == 's3':
            fields = ['id', 'name', 'special_refine_description']
            is_refinement = True
            is_special_refinement = True
            special_refine_hp = 3
        print(fields)
        id_field, name_field, description_field = fields

        # 新規スキル
        if not is_refinement or skill_id != 0:
            # noinspection SqlInsertValues
            cursor.execute(f'''
            INSERT INTO skills ({','.join(fields)})
            VALUES (?, ?, ?)
            ON CONFLICT({id_field}) DO UPDATE
            SET {name_field} = excluded.{name_field},
                {description_field} = excluded.{description_field}
            ''', (skill_id, skill_name, description))
        else:
            # 武器錬成
            # 月光のように同じ名前がある場合は0以外のidを指定すること
            query = f"UPDATE skills SET {description_field} = :description WHERE name = :skill_name"
            cursor.execute(query, {'description': description, 'skill_name': skill_name})

        # 英語名がある場合は入力
        if skill_e_name is not None:
            query = "UPDATE skills SET english_name = :english_name WHERE id = :id"
            cursor.execute(query, {'english_name': skill_e_name, 'id': skill_id})

        # オプションの設定
        if other_field_dict and not is_refinement:
            # フィールドを安全に動的に更新するためのクエリ作成
            set_clause = ", ".join([f"{field} = :{field}" for field in other_field_dict.keys()])
            query = f"UPDATE skills SET {set_clause} WHERE id = :id"
            cursor.execute(query, {**other_field_dict, 'id': skill_id})

        # 武器錬成可能設定
        if is_refinement:
            if skill_id != 0:
                query = f'UPDATE skills SET can_status_refine = "true" WHERE id = :skill_id'
                cursor.execute(query, {'id': skill_id})
            else:
                query = f'UPDATE skills SET can_status_refine = "true" WHERE name = :skill_name'
                cursor.execute(query, {'name': skill_name})

        # 特殊錬成のHP設定
        if is_special_refinement:
            if skill_id != 0:
                query = f"UPDATE skills SET special_refine_hp = {special_refine_hp} WHERE id = :skill_id"
                cursor.execute(query, {'id': skill_id})
            else:
                query = f"UPDATE skills SET special_refine_hp = {special_refine_hp} WHERE name = :skill_name"
                cursor.execute(query, {'name': skill_name})
    conn.commit()


def parse_field(parsed: List[Tuple[str, str]]) -> List[Tuple[str, str, str, str, str]]:
    results = []
    for info, description in parsed:
        skill_id, refinement_type, skill_name = info.split('-')
        if refinement_type == 'n':
            results.append((skill_id, skill_name, description, None, None))
        elif refinement_type == 'r':
            results.append((skill_id, skill_name, None, description, None))
        elif refinement_type == 's':
            results.append((skill_id, skill_name, None, None, description))
    return results


def main():
    # 引数パーサを作成
    parser = argparse.ArgumentParser(description='This script inserts skill descriptions into the database.')

    # `--dry-run` 引数をオプションとして追加（指定しないと `False` になる）
    parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without making changes')

    parser.add_argument('--check-id', action='store_true', help='Check skill id')

    # ファイル名を引数として追加
    parser.add_argument('input_file', type=str, help='Filename')

    # 引数を解析
    args = parser.parse_args()

    if not args.input_file:
        print("Error: input_file is required.", file=sys.stderr)
        sys.exit(1)

    # dry-run フラグが設定されていれば True、されていなければ False
    dry_run = args.dry_run

    # データベースに接続する（存在しない場合は作成される）
    conn = sqlite3.connect('./../../feh-skills.sqlite3')

    should_check_id = args.check_id
    data_to_insert = parse_file(args.input_file)

    # データを挿入する
    if not dry_run:
        insert_data(conn, data_to_insert)
    else:
        check_id(conn, data_to_insert, should_check_id)
        check_type(data_to_insert)
        check_weapon(data_to_insert)
        check_might(data_to_insert)
        check_special(data_to_insert)
        print('[変換結果]')
        print('\n'.join(map(str, data_to_insert)))

        print('')
        print('[シミュレータ用出力]')
        print_simulator_code(data_to_insert)

    # データベース接続を閉じる
    conn.close()


def print_simulator_code(data_to_insert):
    for data in data_to_insert:
        # print(f"data: {data}")
        # print(f"data0: {data[0].split('-')}")
        header = data[0].split('-')
        skill_id = header[0]
        skill_name = header[2]
        if len(header) >= 4:
            skill_e_name = header[3]
        else:
            skill_e_name = skill_name
        skill_e_name = to_pascal_case(skill_e_name)
        options = data[2]
        if 'type' in options:
            skill_type = options['type']
        else:
            skill_type = 'null'
        print(f"{type_symbol(skill_type)}.{skill_e_name}: {skill_id}, // {skill_name}")


def to_pascal_case(sentence):
    # アルファベットのみに変換
    sentence = unidecode(sentence)

    sentence = sentence.replace("/", " ").replace("+", " Plus")

    # 単語を変数名に適した形に変換した後に単語から不要な記号を削除
    words = [re.sub(r'[^a-zA-Z0-9\s]', '', replace_skill_word(word)) for word in sentence.split()]

    # 各単語をタイトルケースに変換し連結(その際に変数名に適した変換をする)
    pascal_case = ''.join(replace_skill_word(word).capitalize() for word in words)

    return pascal_case


def replace_skill_word(name):
    return name.replace("II", "2")


def check_id(conn, data_to_insert, should_check_id):
    id_list = list(map(lambda x: int(x[0].split('-')[0]), data_to_insert))
    if len(id_list) >= 1 and should_check_id:
        # 最大値を取得するクエリ
        query = f"SELECT MAX(id) FROM skills"

        cursor = conn.cursor()
        try:
            cursor.execute(query)
            max_id = cursor.fetchone()[0]  # 最大値を取得
            if max_id is None:
                print(warn('テーブルが空です。'))
            print(f"最大のid: {max_id}")
            if not (max_id < id_list[0]):
                print(warn(f"idが現在の最大値より大きくありません: not {max_id} < {id_list}"))
        finally:
            cursor.close()
            conn.close()
        if not is_incrementing_by_one(id_list):
            print(warn(f"idが順番になっていません: {id_list}"))


def is_incrementing_by_one(lst):
    # リストが空または1つの要素だけの場合は+1ずつ増えているとみなす
    if len(lst) < 2:
        return True

    # 隣接する要素の差が1かどうかをチェック
    for i in range(1, len(lst)):
        if lst[i] - lst[i - 1] != 1:
            return False

    return True


def check_type(lines: List[Tuple[str, str, dict]]):
    for line in lines:
        name, _, d = line
        if not 'type' in d:
            print(warn(f"スキルタイプがありません. name: {name}, d: {d}"))


def check_weapon(lines: List[Tuple[str, str, dict]]):
    for line in lines:
        name, _, d = line
        if 'type' in d and d['type'] == '武器' and not 'weapon_type' in d:
            print(warn(f"武器タイプがありません. name: {name}, d: {d}"))


def check_might(lines: List[Tuple[str, str, dict]]):
    for line in lines:
        name, _, d = line
        if 'weapon_type' in d and not 'might' in d:
            print(warn(f"威力がありません. name: {name}, d: {d}"))


def check_special(lines: List[Tuple[str, str, dict]]):
    for line in lines:
        name, _, d = line
        if 'type' in d and d['type'] == '奥義' and not 'count' in d:
            print(warn(f"カウントがありません. name: {name}, d: {d}"))


def type_symbol(type_str):
    if type_str == '武器':
        return 'Weapon'
    if type_str == 'サポート':
        return 'Support'
    if type_str == '奥義':
        return 'Special'
    if type_str == 'パッシブA':
        return 'PassiveA'
    if type_str == 'パッシブB':
        return 'PassiveB'
    if type_str == 'パッシブC':
        return 'PassiveC'
    if type_str == '響心':
        return 'PassiveX'


if __name__ == '__main__':
    main()
