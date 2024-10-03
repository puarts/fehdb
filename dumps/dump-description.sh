#!/usr/bin/env bash

sqlite3 ./../feh-skills.sqlite3 <<EOF
.headers ON
.mode csv
.output feh-skills-description.csv
SELECT id, name, description, refine_description, special_refine_description FROM skills;
EOF
