set vote_root=%~dp0sources\cyl-vote
set target_cyl=cyl9
pushd %vote_root%
%~dp0externals\sqlite3\sqlite3.exe %~dp0feh-cyl.sqlite3 < %vote_root%\%target_cyl%.query
popd
pause
