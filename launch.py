"""Log and supervise the GUI child; Task Scheduler owns failure retries."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

APP=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LOCALAPPDATA',str(APP)))/'CodexPet'


def base_pythonw():
    config=APP/'runtime/pyvenv.cfg'
    if not config.is_file():raise FileNotFoundError('Desktop-pet Python runtime is missing')
    values={key.strip():value.strip() for line in config.read_text(encoding='utf-8').splitlines() if '=' in line for key,value in [line.split('=',1)]}
    home=values.get('home','').strip()
    executable=Path(home)/'pythonw.exe'
    if not home or not executable.is_file():raise FileNotFoundError('Desktop-pet Python runtime is missing')
    return executable


def main():
    DATA.mkdir(parents=True,exist_ok=True)
    log_path=DATA/'startup.log'
    with log_path.open('ab',buffering=0) as log:
        def note(message):
            log.write((datetime.now().astimezone().isoformat()+' '+message+'\n').encode('utf-8'))
        try:
            executable=base_pythonw()
            env=dict(os.environ)
            for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QML_IMPORT_PATH','QML2_IMPORT_PATH'):
                env.pop(key,None)
            env['QT_QPA_PLATFORM']='windows'
            launch_id=uuid.uuid4().hex;env['CODEXPET_LAUNCH_ID']=launch_id
            note(f'launcher_start pid={os.getpid()} cwd={Path.cwd()}')
            child=subprocess.Popen([str(executable),str(APP/'gui_entry.py')],cwd=str(APP),env=env,
                                   stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=0x08000000)
            note(f'gui_child_start pid={child.pid}')
            # Do not keep a live-but-invisible process indefinitely at login.
            deadline=time.monotonic()+60
            while child.poll() is None and time.monotonic()<deadline:
                try:
                    state=json.loads((DATA/'companion-status.json').read_text(encoding='utf-8'))
                    if state.get('launch_id')==launch_id and state.get('visible') and state.get('within_screen'):
                        note(f'gui_ready pid={state.get("pid")} child_pid={child.pid} geometry={state.get("geometry")}')
                        break
                except (OSError,ValueError):pass
                time.sleep(.25)
            else:
                if child.poll() is None:
                    note('gui_start_timeout: no visible on-screen window after 60 seconds')
                    child.terminate();child.wait(timeout=5)
                    return 1
            code=child.wait()
            note(f'gui_child_exit pid={child.pid} code={code}')
            return 0 if code==0 else 1
        except Exception:
            note(traceback.format_exc())
            return 1


if __name__=='__main__':sys.exit(main())
