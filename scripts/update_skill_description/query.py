import sqlite3
from typing import List, Tuple
from parse_file import parse_file


def insert_data(conn, data: List[Tuple[str, str]]) -> None:
    """
    データをテーブルに挿入する関数

    :param conn:
    :param data: (info, description) のペアを含むタプルのリスト
    """
    cursor = conn.cursor()
    for info, description in data:
        skill_id, refinement_type, skill_name = info.split('-')
        print(skill_id, refinement_type, skill_name, description)
        fields = ''
        if refinement_type == 'n':
            fields = ['id', 'name', 'description']
        elif refinement_type == 'r':
            fields = ['id', 'name', 'refine_description']
        elif refinement_type == 's':
            fields = ['id', 'name', 'special_refine_description']
        print(fields)
        cursor.execute(f'''
        INSERT INTO skills ({','.join(fields)})
        VALUES (?, ?, ?)
        ON CONFLICT({fields[0]}) DO UPDATE
        SET {fields[1]} = excluded.{fields[1]},
            {fields[2]} = excluded.{fields[2]}
        ''', (skill_id, skill_name, description))

        # cursor.execute(f'''
        # INSERT OR UPDATE INTO skills ({fields})
        # VALUES (?, ?, ?)
        # ''', (skill_id, skill_name, description))
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
    # データベースに接続する（存在しない場合は作成される）
    # conn = sqlite3.connect('example.db')
    conn = sqlite3.connect('./../../feh-skills.sqlite3')

    # カーソルオブジェクトを作成
    cursor = conn.cursor()

    # サンプルデータ
    # data_to_insert = [
    #     ('1', 'First description'),
    #     ('2', 'Second description'),
    #     ('3', 'Third description')
    # ]

    data_to_insert = parse_file('./../../sources/skill-desc/8-9-17.txt')
    # データを挿入する
    insert_data(conn, data_to_insert)

    # 挿入されたデータを確認するために全データを取得して表示
    # cursor.execute('SELECT * FROM my_table')
    # rows = cursor.fetchall()
    # for row in rows:
    #     print(row)

    # データベース接続を閉じる
    conn.close()


if __name__ == '__main__':
    main()
