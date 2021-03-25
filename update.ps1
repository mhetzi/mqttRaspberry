<#
.Synopsis
Update and run mqttScripts on windows

.Description
update mqttScript, activate pythons virtual environment, update dependencies and run selected mode

.Notes
On Windows, it may be required to enable this update.ps1 script by setting the
execution policy for the user. You can do this by issuing the following PowerShell
command:

PS C:\> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#>

Write-Output $Args[0]

Write-Output "Betrete virtal-environment..."
..\win32venv\Scripts\Activate.ps1

Write-Output "Aktualisiere mqttScripts"
git pull
git reset --hard origin/master

Write-Output "Aktualisiere python packages (pip)"
pip-review -a --user 

Write-Output "Checke commandline argument"
if ($Args[0] -eq "service") {
    Write-Output "mqttScript wird im service mode gestartet..."
    pythonw.exe .\Launcher.py --config ..\config\mqttra.config --systemd
} elseif ($Args[0] -eq "configure") {
    Write-Output "mqttScript wird im Konfigurationsmode gestartet..."
    pythonw.exe .\Launcher.py --config ..\config\mqttra.config --configure
} elseif ($Args[0] -eq "service-log") {
    Write-Output "mqttScript wird im service mode gestartet (Debug log wird nach R:\Temp gespeichert) ..."
    pythonw.exe .\Launcher.py --config ..\config\mqttra.config --systemd --log R:\Temp\mqttScripts.log
    Start-Sleep -Seconds 5
} else {
    Write-Output "Keine weiteren aktionen angegeben."
}
