set sqlite3=%~dp0externals\sqlite3\sqlite3.exe

%sqlite3% feh-story.sqlite3 < update-story-dialogs.query

pause
