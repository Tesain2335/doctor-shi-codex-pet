"""Register the interactive sign-in task, then run that exact task now."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import winreg
from launch import base_pythonw

base = Path(__file__).resolve().parent
data=Path(os.environ['LOCALAPPDATA'])/'CodexPet';data.mkdir(parents=True,exist_ok=True)
run_key=r'Software\Microsoft\Windows\CurrentVersion\Run'
previous=None
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,run_key) as key:previous=winreg.QueryValueEx(key,'CodexPetCompanion')[0]
except FileNotFoundError:pass
if previous:
    backup=data/('startup-before-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
    backup.write_text(json.dumps({'run_command':previous},indent=2),encoding='utf-8')
powershell=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
env=dict(os.environ);env['CODEXPET_APP_DIRECTORY']=str(base);env['CODEXPET_BASE_PYTHONW']=str(base_pythonw())
result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',(base/'register_startup.ps1').read_text(encoding='utf-8')],
                      env=env,capture_output=True,creationflags=0x08000000)
if result.returncode:
    sys.stderr.write(result.stderr.decode('utf-8',errors='replace'))
    raise SystemExit(result.returncode)
print(result.stdout.decode('utf-8',errors='replace').strip())
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,run_key,0,winreg.KEY_SET_VALUE) as key:winreg.DeleteValue(key,'CodexPetCompanion')
except FileNotFoundError:pass
subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',"Start-ScheduledTask -TaskName 'CodexPetCompanion' -ErrorAction Stop"],check=True,creationflags=0x08000000)
print('Interactive sign-in task installed and started; log: '+str(data/'startup.log'))
