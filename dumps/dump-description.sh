#!/usr/bin/env bash

sqlite3 ./../feh-skills.sqlite3 <<EOF
.headers ON
.mode csv
.output feh-skills-description.csv
SELECT * FROM skills;
EOF
