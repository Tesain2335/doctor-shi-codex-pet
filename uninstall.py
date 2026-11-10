"""Remove only this companion's per-user startup entries."""
import os
from pathlib import Path
import subprocess
import winreg
powershell=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',
    "$t=Get-ScheduledTask -TaskName 'CodexPetCompanion' -ErrorAction SilentlyContinue; if ($t) {Stop-ScheduledTask -TaskName 'CodexPetCompanion' -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName 'CodexPetCompanion' -Confirm:$false -ErrorAction Stop}"],check=True,creationflags=0x08000000)
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run',0,winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key,'CodexPetCompanion')
except FileNotFoundError:pass
print('Startup task and legacy Run entry removed. Exit any remaining pet using its menu.')
