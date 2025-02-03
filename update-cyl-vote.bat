set vote_root=%~dp0sources\cyl-vote
set target_cyl=cyl9
sqlite3 %~dp0feh-cyl.sqlite3 < %vote_root%\%target_cyl%.query
pause
