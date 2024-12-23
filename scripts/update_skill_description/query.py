import argparse
import sqlite3
from typing import List, Tuple
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
        skill_id, refinement_type, skill_name = info.split('-')
        print(skill_id, refinement_type, skill_name, description)
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
        # noinspection SqlInsertValues
        cursor.execute(f'''
        INSERT INTO skills ({','.join(fields)})
        VALUES (?, ?, ?)
        ON CONFLICT({fields[0]}) DO UPDATE
        SET {fields[1]} = excluded.{fields[1]},
            {fields[2]} = excluded.{fields[2]}
        ''', (skill_id, skill_name, description))

        if other_field_dict and not is_refinement:
            # フィールドを安全に動的に更新するためのクエリ作成
            set_clause = ", ".join([f"{field} = :{field}" for field in other_field_dict.keys()])
            query = f"UPDATE skills SET {set_clause} WHERE id = :id"
            cursor.execute(query, {**other_field_dict, 'id': skill_id})
        if is_refinement:
            query = f'UPDATE skills SET can_status_refine = "true" WHERE id = :id'
            cursor.execute(query, {'id': skill_id})
        if is_special_refinement:
            query = f"UPDATE skills SET special_refine_hp = {special_refine_hp} WHERE id = :id"
            cursor.execute(query, {'id': skill_id})
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
    parser = argparse.ArgumentParser(description="Dry run flag example")

    # `--dry-run` 引数をオプションとして追加（指定しないと `False` になる）
    parser.add_argument('--dry-run', action='store_true', help="Perform a dry run without making changes")

    # 引数を解析
    args = parser.parse_args()

    # dry-run フラグが設定されていれば True、されていなければ False
    dry_run = args.dry_run

    # データベースに接続する（存在しない場合は作成される）
    conn = sqlite3.connect('./../../feh-skills.sqlite3')

    should_check_id = True
    data_to_insert = parse_file('./../../sources/skill-desc/9-12-25.txt')
    # data_to_insert = parse_file('./../../sources/skill-desc/refine-2024-12.txt')
    # should_check_id = False

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

    # データベース接続を閉じる
    conn.close()


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


if __name__ == '__main__':
    main()
