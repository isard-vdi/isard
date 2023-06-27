REM We use 'more' to ensure the encoding is ansi and it can be executed
echo Set oShell = CreateObject("Wscript.Shell") | more > "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp/personal_unit.vbs"
echo Return =  oShell.Run("net use Z: http{protocol}://{host}/ {password} /user:{user} /persistent:no", 0, true) | more >> "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp/personal_unit.vbs"
