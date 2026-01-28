import sqlite3
import re


def create_hero_info_js_variable(hero_db_path, skill_db_path):
    # --- 1. スキルデータの辞書化 ---
    skill_map = {}
    try:
        conn_skill = sqlite3.connect(skill_db_path)
        cursor_skill = conn_skill.cursor()
        # typeカラム: 武器, 補助, 奥義, A, B, C, X, 響心 など
        cursor_skill.execute("SELECT name, id, type FROM skills")
        for row in cursor_skill.fetchall():
            name, skill_id, skill_type = row
            skill_map[name] = {
                'id': skill_id,
                'type': skill_type
            }
        conn_skill.close()
    except sqlite3.Error as e:
        return f"Error reading skill database: {e}"

    # --- 2. ヒーローデータの処理 ---
    conn_hero = sqlite3.connect(hero_db_path)
    conn_hero.row_factory = sqlite3.Row
    cursor_hero = conn_hero.cursor()

    # Enum定義
    def get_move_type(jp_move):
        mapping = {
            '歩行': 'MoveType.Infantry',
            '騎馬': 'MoveType.Cavalry',
            '飛行': 'MoveType.Flying',
            '重装': 'MoveType.Armor'
        }
        return mapping.get(jp_move, 'MoveType.Infantry')

    def get_season(special_type):
        if not special_type: return 'SeasonType.None'
        mapping = {
            '火': 'SeasonType.Fire', '水': 'SeasonType.Water',
            '風': 'SeasonType.Wind', '地': 'SeasonType.Earth',
            '光': 'SeasonType.Light', '闇': 'SeasonType.Dark',
            '天': 'SeasonType.Astra', '理': 'SeasonType.Anima'
        }
        for key, val in mapping.items():
            if key in special_type: return val
        return 'SeasonType.None'

    def get_blessing_type(special_type):
        if not special_type: return 'BlessingType.None'
        # Hp数字_ステータス数字 または Hp数字 のみを抽出
        match = re.search(r'(Hp\d+(?:_[a-zA-Z0-9]+)?)', special_type)
        if match:
            return f"BlessingType.{match.group(1)}"
        return 'BlessingType.None'

    def get_bst(special_type, default=0):
        if not special_type: return default
        match = re.search(r'死闘(\d+)', special_type)
        return int(match.group(1)) if match else default

    def clean_weapon_type(raw):
        # 1. 魔・竜: 「無」も含めてそのまま保持
        if '魔' in raw or '竜' in raw:
            return raw
        # 2. 弓・暗器・獣: 色つきは保持するが、「無」は削除
        if any(x in raw for x in ['弓', '暗器', '獣']):
            return raw.replace('無', '')
        # 3. 剣・槍・斧・杖: 色情報を削除
        return raw.replace('赤', '').replace('青', '').replace('緑', '').replace('無', '')

    def parse_skill_string(skill_str):
        if not skill_str: return []
        parts = [p for p in skill_str.split('|') if p]
        names = [p.split(':')[0] for p in parts]
        return names

    def classify_skills(skill_names):
        classified = {
            'weapon': [], 'assist': [], 'special': [],
            'a': [], 'b': [], 'c': [], 'x': []
        }
        for name in skill_names:
            if name in skill_map:
                s_data = skill_map[name]
                s_id = s_data['id']
                s_type = s_data['type']

                if s_type == '武器':
                    classified['weapon'].append(s_id)
                elif s_type == 'サポート':
                    classified['assist'].append(s_id)
                elif s_type == '奥義':
                    classified['special'].append(s_id)
                elif s_type == 'パッシブA':
                    classified['a'].append(s_id)
                elif s_type == 'パッシブB':
                    classified['b'].append(s_id)
                elif s_type == 'パッシブC':
                    classified['c'].append(s_id)
                elif s_type in ['X', '響心']:
                    classified['x'].append(s_id)
        return classified

    def get_equipped_id(id_list):
        return id_list[-1] if id_list else -1

    def format_array(arr):
        if not arr: return "[]"
        return "[" + ", ".join(map(str, arr)) + ",]"

    # --- メイン処理 ---
    output_lines = []

    try:
        cursor_hero.execute("SELECT * FROM heroes")
        heroes = cursor_hero.fetchall()

        for row in heroes:
            name = row['name']
            internal_id = row['id']
            thumb = row['thumb']
            move_type = get_move_type(row['move_type'])

            raw_weapon = row['weapon_type']
            w_type_str = clean_weapon_type(raw_weapon)

            is_melee = any(mw in raw_weapon for mw in ['剣', '槍', '斧', '竜', '獣'])
            range_val = 1 if is_melee else 2

            hp, atk, spd, df, res = row['hp_5'], row['atk_5'], row['spd_5'], row['def_5'], row['res_5']
            hp1, atk1, spd1, df1, res1 = row['hp_5_lv1'], row['atk_5_lv1'], row['spd_5_lv1'], row['def_5_lv1'], row[
                'res_5_lv1']

            skill_names = parse_skill_string(row['skills'])
            s_dict = classify_skills(skill_names)

            w_id = get_equipped_id(s_dict['weapon'])
            a_id = get_equipped_id(s_dict['assist'])
            sp_id = get_equipped_id(s_dict['special'])
            pa_id = get_equipped_id(s_dict['a'])
            pb_id = get_equipped_id(s_dict['b'])
            pc_id = get_equipped_id(s_dict['c'])
            px_id = get_equipped_id(s_dict['x'])

            season = get_season(row['special_type'])
            blessing = get_blessing_type(row['special_type'])
            bst = get_bst(row['special_type'], default=0)

            epithet = row['epithet'] if row['epithet'] else ""
            p_names = row['pure_name'].strip('|').split('|') if row['pure_name'] else []
            p_names_str = "[" + ", ".join([f"'{n}'" for n in p_names if n]) + ",]"

            origin = row['origin'] if row['origin'] else ""
            how_to_get = row['how_to_get'] if row['how_to_get'] else "恒常"
            release_date = row['release_date']
            is_resplendent = 'true' if row['resplendent'] else 'false'

            # インデント(スペース2つ)をつけて可読性を向上
            line = (f"  new HeroInfo('{name}', '{thumb}', {move_type}, '{w_type_str}', {range_val}, "
                    f"{hp}, {atk}, {spd}, {df}, {res}, "
                    f"{hp1}, {atk1}, {spd1}, {df1}, {res1}, "
                    f"'0/0', '0/0', '0/0', '0/0', '0/0', "
                    f"{w_id}, {a_id}, {sp_id}, {pa_id}, {pb_id}, {pc_id}, {px_id}, "
                    f"{season}, {blessing}, '{epithet}', {p_names_str}, "
                    f"{bst}, {format_array(s_dict['weapon'])}, {format_array(s_dict['assist'])}, "
                    f"{internal_id}, {is_resplendent}, '{origin}', '{how_to_get}', '{release_date}', "
                    f"{format_array(s_dict['special'])}, {format_array(s_dict['a'])}, "
                    f"{format_array(s_dict['b'])}, {format_array(s_dict['c'])}, {format_array(s_dict['x'])}"
                    f")")
            output_lines.append(line)

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn_hero.close()

    # JS変数定義として出力
    print("const heroInfos = [")
    print(",\n".join(output_lines))
    print("];")
    return None


if __name__ == "__main__":
    create_hero_info_js_variable('feh-heroes.sqlite3', 'feh-skills.sqlite3')
