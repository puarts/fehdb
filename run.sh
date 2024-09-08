#!/bin/bash

# 新スキル
SKILL_DIR=skill-desc
TARGET=8-9-6
python replace.py $SKILL_DIR/$TARGET-orig/ $SKILL_DIR/$TARGET/
bash update-skill-desc.sh $SKILL_DIR/$TARGET description
bash select.sh $SKILL_DIR/$TARGET

# 武器錬成
TARGET=2024
# 通常錬成
SKILL_DIR=skill-refine-desc
python replace.py $SKILL_DIR/$TARGET-orig $SKILL_DIR/$TARGET
bash update-skill-desc.sh $SKILL_DIR/$TARGET refine_description
bash select.sh $SKILL_DIR/$TARGET

# 特殊錬成
SKILL_DIR=skill-special-refine-desc
python replace.py $SKILL_DIR/$TARGET-orig $SKILL_DIR/$TARGET
bash update-skill-desc.sh $SKILL_DIR/$TARGET special_refine_description
bash select.sh $SKILL_DIR/$TARGET
