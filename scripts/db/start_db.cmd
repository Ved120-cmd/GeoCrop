@echo off
REM Start the local GeoCrop PostgreSQL (portable, data on E:, binaries on D:)
"D:\geocrop_work\pgsql\bin\pg_ctl.exe" -D "E:\projects\soil\db\pgdata" -l "E:\projects\soil\db\postgres.log" -w start
