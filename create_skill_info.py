import sqlite3


def create_skill_info_split(skill_db_path):
    conn = sqlite3.connect(skill_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- 1. WeaponType Mapping ---
    weapon_type_map = {
        '剣': 'WeaponType.Sword',
        '槍': 'WeaponType.Lance',
        '斧': 'WeaponType.Axe',
        '赤魔': 'WeaponType.RedTome',
        '青魔': 'WeaponType.BlueTome',
        '緑魔': 'WeaponType.GreenTome',
        '無魔': 'WeaponType.ColorlessTome',
        '赤弓': 'WeaponType.RedBow',
        '青弓': 'WeaponType.BlueBow',
        '緑弓': 'WeaponType.GreenBow',
        '弓': 'WeaponType.ColorlessBow',
        '赤暗器': 'WeaponType.RedDagger',
        '青暗器': 'WeaponType.BlueDagger',
        '緑暗器': 'WeaponType.GreenDagger',
        '暗器': 'WeaponType.ColorlessDagger',
        '杖': 'WeaponType.Staff',
        '赤竜': 'WeaponType.RedBreath',
        '青竜': 'WeaponType.BlueBreath',
        '緑竜': 'WeaponType.GreenBreath',
        '無竜': 'WeaponType.ColorlessBreath',
        '赤獣': 'WeaponType.RedBeast',
        '青獣': 'WeaponType.BlueBeast',
        '緑獣': 'WeaponType.GreenBeast',
        '無獣': 'WeaponType.ColorlessBeast',
        '獣': 'WeaponType.ColorlessBeast',
    }

    def get_weapon_type(jp_type):
        if not jp_type: return 'WeaponType.None'
        if jp_type in weapon_type_map: return weapon_type_map[jp_type]

        # フォールバック処理
        if '剣' in jp_type: return 'WeaponType.Sword'
        if '槍' in jp_type: return 'WeaponType.Lance'
        if '斧' in jp_type: return 'WeaponType.Axe'
        if '赤' in jp_type and '魔' in jp_type: return 'WeaponType.RedTome'
        if '青' in jp_type and '魔' in jp_type: return 'WeaponType.BlueTome'
        if '緑' in jp_type and '魔' in jp_type: return 'WeaponType.GreenTome'
        if '魔' in jp_type: return 'WeaponType.ColorlessTome'
        if '赤' in jp_type and '弓' in jp_type: return 'WeaponType.RedBow'
        if '青' in jp_type and '弓' in jp_type: return 'WeaponType.BlueBow'
        if '緑' in jp_type and '弓' in jp_type: return 'WeaponType.GreenBow'
        if '弓' in jp_type: return 'WeaponType.ColorlessBow'
        if '赤' in jp_type and '暗器' in jp_type: return 'WeaponType.RedDagger'
        if '青' in jp_type and '暗器' in jp_type: return 'WeaponType.BlueDagger'
        if '緑' in jp_type and '暗器' in jp_type: return 'WeaponType.GreenDagger'
        if '暗器' in jp_type: return 'WeaponType.ColorlessDagger'
        if '杖' in jp_type: return 'WeaponType.Staff'
        if '赤' in jp_type and '竜' in jp_type: return 'WeaponType.RedBreath'
        if '青' in jp_type and '竜' in jp_type: return 'WeaponType.BlueBreath'
        if '緑' in jp_type and '竜' in jp_type: return 'WeaponType.GreenBreath'
        if '無' in jp_type and '竜' in jp_type: return 'WeaponType.ColorlessBreath'
        if '竜' in jp_type: return 'WeaponType.ColorlessBreath'
        if '赤' in jp_type and '獣' in jp_type: return 'WeaponType.RedBeast'
        if '青' in jp_type and '獣' in jp_type: return 'WeaponType.BlueBeast'
        if '緑' in jp_type and '獣' in jp_type: return 'WeaponType.GreenBeast'
        if '無' in jp_type and '獣' in jp_type: return 'WeaponType.ColorlessBeast'
        if '獣' in jp_type: return 'WeaponType.ColorlessBeast'
        return 'WeaponType.None'

    # --- 2. SkillType Mapping ---
    skill_type_map = {
        '武器': 'SkillType.Weapon',
        'サポート': 'SkillType.Support',
        '奥義': 'SkillType.Special',
        'パッシブA': 'SkillType.PassiveA',
        'パッシブB': 'SkillType.PassiveB',
        'パッシブC': 'SkillType.PassiveC',
        '聖印': 'SkillType.PassiveS',
        '響心': 'SkillType.PassiveX',
        '隊長': 'SkillType.Captain'
    }

    def get_skill_type(jp_type):
        return skill_type_map.get(jp_type, 'SkillType.Weapon')

    # --- 3. EffectiveType Mapping ---
    def get_effective_types(effective_str):
        if not effective_str: return "[]"
        effects = []
        if '重装' in effective_str: effects.append('EffectiveType.Armor')
        if '騎馬' in effective_str: effects.append('EffectiveType.Cavalry')
        if '歩行' in effective_str: effects.append('EffectiveType.Infantry')
        if '飛行' in effective_str: effects.append('EffectiveType.Flying')
        if '竜' in effective_str: effects.append('EffectiveType.Dragon')
        if '獣' in effective_str: effects.append('EffectiveType.Beast')
        if '剣' in effective_str: effects.append('EffectiveType.Sword')
        if '槍' in effective_str: effects.append('EffectiveType.Lance')
        if '斧' in effective_str: effects.append('EffectiveType.Axe')
        if '魔' in effective_str or '魔法' in effective_str: effects.append('EffectiveType.Tome')
        if '杖' in effective_str: effects.append('EffectiveType.Staff')
        if '弓' in effective_str: effects.append('EffectiveType.Bow')
        if '暗器' in effective_str: effects.append('EffectiveType.Dagger')
        if not effects: return "[]"
        return "[" + ", ".join(effects) + ",]"

    # --- 4. AssistType Mapping ---
    def get_assist_type(assist):
        if not assist: return 'AssistType.None'
        if 'Refresh' in assist: return 'AssistType.Refresh'
        if 'Move' in assist: return 'AssistType.Move'
        if 'Rally' in assist: return 'AssistType.Rally'
        if 'DonorHeal' in assist: return 'AssistType.DonorHeal'
        if 'Heal' in assist: return 'AssistType.Heal'
        if 'Restore' in assist: return 'AssistType.Restore'

        if '再行動' in assist: return 'AssistType.Refresh'
        if '回復' in assist: return 'AssistType.Heal'
        if '献身' in assist or '相互援助' in assist: return 'AssistType.DonorHeal'
        if '応援' in assist: return 'AssistType.Rally'
        if any(x in assist for x in ['移動', '引き寄せ', '引き戻し', '体当たり', 'ぶちかまし', '入れ替え']):
            return 'AssistType.Move'
        if 'レスト' in assist: return 'AssistType.Restore'
        return 'AssistType.None'

    # --- Inheritable MoveType Logic ---
    def get_inheritable_move_types(jp_str):
        if not jp_str: return "[]"
        types = []
        if '歩行' in jp_str: types.append('MoveType.Infantry')
        if '重装' in jp_str: types.append('MoveType.Armor')
        if '騎馬' in jp_str: types.append('MoveType.Cavalry')
        if '飛行' in jp_str: types.append('MoveType.Flying')
        if not types: return "[]"
        return "[" + ",".join(types) + "]"

    def format_bool(val):
        return 'true' if val else 'false'

    # --- Main Processing ---
    # 出力先ごとのリストを用意
    output_groups = {
        'SkillType.Weapon': [],
        'SkillType.Support': [],
        'SkillType.Special': [],
        'SkillType.PassiveA': [],
        'SkillType.PassiveB': [],
        'SkillType.PassiveC': [],
        'SkillType.PassiveX': [],
        'SkillType.PassiveS': [],
        'SkillType.Captain': []
    }

    # 変数名とのマッピング
    variable_names = {
        'SkillType.Weapon': 'const weaponInfos',
        'SkillType.Support': 'const supportInfos',
        'SkillType.Special': 'const specialInfos',
        'SkillType.PassiveA': 'const passiveAInfos',
        'SkillType.PassiveB': 'const passiveBInfos',
        'SkillType.PassiveC': 'const passiveCInfos',
        'SkillType.PassiveX': 'const passiveXInfos',
        'SkillType.PassiveS': 'const passiveSInfos',
        'SkillType.Captain': 'const captainInfos'
    }

    try:
        cursor.execute("SELECT * FROM skills")
        skills = cursor.fetchall()

        for row in skills:
            s_id = row['id']
            name = row['name']

            hp = row['hp'] if row['hp'] else 0
            atk = row['atk'] if row['atk'] else 0
            spd = row['spd'] if row['spd'] else 0
            defense = row['def'] if row['def'] else 0
            res = row['res'] if row['res'] else 0

            might = row['might'] if row['might'] else 0
            might_refine = row['might_refine'] if row['might_refine'] else might

            special_count = row['count'] if row['count'] is not None else 0
            cd_count = row['cooldown_count'] if row['cooldown_count'] is not None else 0

            atk_count = row['atk_count'] if row['atk_count'] else 1
            counter_atk_count = row['counteratk_count'] if row['counteratk_count'] else 1

            effectives = get_effective_types(row['effective'])
            invalidated = get_effective_types(row['invalidate_effective'])

            all_dist = format_bool(row['all_dist_counter'])
            sacred_seal = format_bool(row['sacred_seal'])
            disable_counter = format_bool(row['disable_counter'])
            wrathful = format_bool(row['wrathful_staff'])

            assist_type = get_assist_type(row['assist_type'])
            w_type = get_weapon_type(row['weapon_type'])
            s_type = get_skill_type(row['type'])

            has_status_refine = format_bool(row['can_status_refine'])
            has_special_refine = 'true' if row['special_refine_description'] else 'false'
            special_refine_hp = row['special_refine_hp'] if row['special_refine_hp'] else 0

            can_inherit = format_bool(row['inherit'])
            if row['inherit'] and not row['inheritable_move_type']:
                inh_move = "[MoveType.Infantry,MoveType.Armor,MoveType.Flying,MoveType.Cavalry]"
            else:
                inh_move = get_inheritable_move_types(row['inheritable_move_type'])

            inh_weapon = "[WeaponType.All]" if row['inherit'] else "[]"

            no_add_impl = format_bool(row['no_impl_required'])
            sp = row['sp'] if row['sp'] else 0
            icon_name = ''

            line = (
                f"  new SkillInfo({s_id}, '{name}', {might}, {special_count}, {hp}, {atk}, {spd}, {defense}, {res}, "
                f"{effectives}, {invalidated}, {cd_count}, {atk_count}, {counter_atk_count}, "
                f"{all_dist}, {sacred_seal}, {might_refine}, {disable_counter}, {wrathful}, "
                f"{assist_type}, {no_add_impl}, {special_refine_hp}, {w_type}, {sp}, "
                f"{can_inherit}, {inh_weapon}, {inh_move}, {has_special_refine}, {has_status_refine}, "
                f"'{icon_name}', {s_type})")

            # タイプ別リストに追加
            if s_type in output_groups:
                output_groups[s_type].append(line)
            else:
                # 定義外のタイプが万が一あればWeaponに入れるなどの処理（現状は起きないはず）
                output_groups['SkillType.Weapon'].append(line)

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

    # 出力
    # 定義順に出力
    order = [
        'SkillType.Weapon', 'SkillType.Support', 'SkillType.Special',
        'SkillType.PassiveA', 'SkillType.PassiveB', 'SkillType.PassiveC',
        'SkillType.PassiveX', 'SkillType.PassiveS', 'SkillType.Captain'
    ]

    for stype in order:
        var_name = variable_names[stype]
        lines = output_groups[stype]
        print(f"{var_name} = [")
        if lines:
            print(",\n".join(lines))
        print("];\n")


if __name__ == "__main__":
    create_skill_info_split('feh-skills.sqlite3')
