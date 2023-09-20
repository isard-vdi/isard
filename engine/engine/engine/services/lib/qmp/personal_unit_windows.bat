REM We use 'more' to ensure the encoding is ansi and it can be executed
set scriptPath="C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp/isard_personal_unit.vbs"

REM Start the WebClient service (in order to be able to mount)
net start WebClient

REM Remove the file right when the execution starts, so there are less changes of leaked credentials
echo Set oFS = CreateObject("Scripting.FileSystemObject") | more > %scriptPath%
echo oFS.DeleteFile(WScript.ScriptFullName) | more >> %scriptPath%

REM Wait for a network connection to the server and make the mount afterwards
echo Set oShell = CreateObject("Wscript.Shell") | more >> %scriptPath%
echo Return = oShell.Run("powershell -Command do {{ $url = [uri]'http{protocol}://{host}'; $ping = test-connection -comp $url.Host -count 1 -Quiet }} until ($ping)", 0, true) | more >> %scriptPath%
echo Return = oShell.Run("net use Z: http{protocol}://{host}/ {password} /user:{user} /persistent:no", 0, true) | more >> %scriptPath%
