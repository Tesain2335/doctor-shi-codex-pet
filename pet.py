"""Local Windows Codex companion. No credentials or chat text are stored."""
import ctypes
from ctypes import wintypes
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import uuid

APP = Path(__file__).resolve().parent
SESSIONS = Path.home() / '.codex' / 'sessions'
DATA = Path(os.environ.get('LOCALAPPDATA', str(APP))) / 'CodexPet'
TRANSPARENT = '#ff00ff'
CREATE_NO_WINDOW = 0x08000000


def codex_running():
    """Match the packaged Codex executable, not the similarly named ChatGPT app."""
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k.CreateToolhelp32Snapshot(2, 0)
    if snap == wintypes.HANDLE(-1).value:
        return False
    try:
        entry = PROCESSENTRY32W(); entry.dwSize = ctypes.sizeof(entry)
        more = k.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() == 'chatgpt.exe':
                handle = k.OpenProcess(0x1000, False, entry.th32ProcessID)
                if handle:
                    try:
                        buf = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(buf))
                        if k.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                            path = buf.value.lower().replace('/', '\\')
                            if '\\windowsapps\\openai.codex_' in path and path.endswith('\\app\\chatgpt.exe'):
                                return True
                    finally: k.CloseHandle(handle)
            more = k.Process32NextW(snap, ctypes.byref(entry))
        return False
    finally: k.CloseHandle(snap)


def find_codex():
    """Windows sign-in does not inherit the Codex app's added PATH entry."""
    exe = shutil.which('codex.exe') or shutil.which('codex')
    if exe:return exe
    cache=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'OpenAI/Codex/bin'
    try:
        candidates=[path for path in cache.glob('*/codex.exe') if path.is_file()]
        if candidates:return str(max(candidates,key=lambda path:path.parent.stat().st_mtime))
    except OSError:pass
    return None


def fetch_limits(timeout=18):
    exe = find_codex()
    if not exe: raise RuntimeError('找不到 Codex 命令')
    proc = subprocess.Popen([exe, 'app-server'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                            creationflags=CREATE_NO_WINDOW)
    lines = queue.Queue()
    def read_lines():
        try:
            for line in proc.stdout: lines.put(line)
        finally: lines.put(None)
    threading.Thread(target=read_lines, daemon=True).start()
    def send(obj):
        proc.stdin.write(json.dumps(obj) + '\n'); proc.stdin.flush()
    def response(id_):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError('额度读取超时')
            try: line = lines.get(timeout=remaining)
            except queue.Empty: raise TimeoutError('额度读取超时')
            if line is None: raise RuntimeError('Codex 服务意外退出')
            try: msg = json.loads(line)
            except (ValueError, TypeError): continue
            if msg.get('id') == id_:
                if 'error' in msg: raise RuntimeError('Codex 暂时无法读取额度')
                return msg.get('result', {})
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {
            'name': 'local_codex_companion', 'title': 'Local Codex Companion', 'version': '0.1.0'}}})
        response(1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        return response(2)
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()


def parse_limits(result):
    limits = (result.get('rateLimitsByLimitId') or {}).get('codex') or result.get('rateLimits') or {}
    windows = [limits.get('primary'), limits.get('secondary')]
    five = next((w for w in windows if isinstance(w, dict) and w.get('windowDurationMins') == 300), None)
    used = five.get('usedPercent') if five else None
    left = max(0, min(100, 100-used)) if isinstance(used, (int, float)) and not isinstance(used, bool) else None
    credits = limits.get('credits')
    balance = None
    if isinstance(credits, dict):
        if credits.get('unlimited') is not True and credits.get('balance') is not None:
            try:
                candidate = Decimal(str(credits['balance']))
                if candidate.is_finite() and candidate >= 0: balance = candidate
            except (InvalidOperation, ValueError): pass
    return left, balance, result.get('accountId')


class CreditTracker:
    """Accumulate observed decreases between displayed completion notices."""
    def __init__(self):
        self.last = None; self.account = None; self.decrease = Decimal(0)

    def observe(self, balance, account):
        if account and self.account and account != self.account:
            self.last = None; self.decrease = Decimal(0)
        if account: self.account = account
        if balance is not None:
            if self.last is not None and balance < self.last:
                self.decrease += self.last - balance
            self.last = balance

    def notice(self, left):
        lines = [f'五小时剩余  {left:g}%' if left is not None else '五小时额度暂不可用']
        if self.decrease > 0 and self.last is not None:
            lines.append(f'Credits 剩余  {self.last:,.2f}')
            self.decrease = Decimal(0)
        return '\n'.join(lines)


class SessionEvents:
    """Tail new event records only; never retain chat content or read old history."""
    def __init__(self, root):
        self.root = root
        self.offsets = {}
        self.first = True

    def check(self):
        return bool(self.poll())

    def poll(self):
        """Return completion metadata for precise per-thread/per-turn usage."""
        found = []
        try: files = list(self.root.rglob('*.jsonl'))
        except OSError: return []
        for path in files:
            try:
                size = path.stat().st_size
                if path not in self.offsets:
                    self.offsets[path] = size if self.first else 0
                offset = self.offsets[path]
                if size < offset: offset = 0
                if size > offset:
                    with path.open('rb') as f:
                        f.seek(offset)
                        while True:
                            start = f.tell(); line = f.readline()
                            if not line: break
                            if not line.endswith(b'\n'):
                                f.seek(start); break
                            try:
                                record = json.loads(line)
                                if record.get('type') == 'event_msg' and (record.get('payload') or {}).get('type') == 'task_complete':
                                    try: thread = str(uuid.UUID(path.stem[-36:]))
                                    except ValueError: thread = None
                                    turn = record['payload'].get('turn_id')
                                    found.append({'thread_id': thread, 'turn_id': turn,
                                                  'timestamp': record.get('timestamp')})
                            except (ValueError, TypeError, AttributeError): pass
                        self.offsets[path] = f.tell()
            except OSError: pass
        self.first = False
        return found


class Pet:
    def __init__(self, root):
        self.root = root; self.busy = False; self.visible = False; self.pending = False; self.pending_notice = False
        try: self.native_mode = json.loads((APP/'settings.json').read_text(encoding='utf-8')).get('native_pet', False)
        except (OSError, ValueError, AttributeError): self.native_mode = False
        self.last_refresh = 0; self.last_status = ''; self.events = SessionEvents(SESSIONS)
        self.credit = CreditTracker(); self.bubble_visible = False; self.bubble_timer = None; self.expression = 0
        self.events.check()
        root.title('Codex 额度提示' if self.native_mode else 'Codex 桌宠'); root.overrideredirect(True); root.attributes('-topmost', True)
        root.configure(bg=TRANSPARENT); root.attributes('-transparentcolor', TRANSPARENT)
        height = 100 if self.native_mode else 270
        root.geometry(f'270x{height}+' + str(max(0,root.winfo_screenwidth()-300)) + '+' + str(max(0,root.winfo_screenheight()-height-60)))
        self.frames = [tk.PhotoImage(file=str(APP / 'assets' / f'doctor_{i}.png')).zoom(3).subsample(2)
                       for i in ('01', '02', '04', '05', '06', '08')]
        self.canvas = tk.Canvas(root, width=270, height=270, bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack(); self.draw()
        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label='刷新额度', command=lambda: self.refresh(True))
        self.menu.add_command(label='切换表情', command=self.next_expression)
        self.menu.add_command(label='退出桌宠（本次）', command=root.destroy)
        self.canvas.bind('<ButtonPress-1>', self.start_drag)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<Button-3>', lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        root.withdraw(); root.after(100, self.tick)

    def draw(self):
        c = self.canvas; c.delete('all')
        if self.bubble_visible:
            c.create_polygon(10, 9, 10, 5, 18, 5, 251, 5, 260, 5, 260, 14,
                             260, 68, 260, 77, 251, 77, 165, 77, 145, 90, 148, 77,
                             18, 77, 10, 77, 10, 68, fill='#fcfdff', outline='#64788c',
                             width=2, smooth=True, tags='bubble')
            c.create_rectangle(23, 18, 26, 38, fill='#3b96bd', outline='', tags='bubble')
            first, _, second = self.last_status.partition('\n')
            if first.startswith('五小时剩余  '):
                value = first.split('  ', 1)[1]
                c.create_text(35, 28, text='五小时剩余', anchor='w', fill='#45586b',
                              font=('Microsoft YaHei UI', 10), tags='bubble')
                c.create_text(242, 29, text=value, anchor='e', fill='#183b52',
                              font=('Segoe UI', 17, 'bold'), tags='bubble')
            else:
                c.create_text(35, 28, text=first, anchor='w', fill='#45586b',
                              font=('Microsoft YaHei UI', 10), tags='bubble')
            if second:
                c.create_line(24, 47, 246, 47, fill='#dce8ee', tags='bubble')
                c.create_text(25, 60, text=second, anchor='w', fill='#33617a',
                              font=('Microsoft YaHei UI', 9), tags='bubble')
        if not self.native_mode: c.create_image(135, 174, image=self.frames[self.expression])

    def next_expression(self):
        self.expression = (self.expression + 1) % len(self.frames); self.draw()

    def show_notice(self, text):
        self.last_status = text; self.bubble_visible = True
        self.root.deiconify()
        if self.bubble_timer is not None: self.root.after_cancel(self.bubble_timer)
        self.bubble_timer = self.root.after(5000, self.hide_notice)
        self.draw()

    def hide_notice(self):
        self.bubble_timer = None; self.bubble_visible = False; self.draw()
        if self.native_mode: self.root.withdraw()

    def start_drag(self, e): self.drag_origin = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y()); self.moved = False
    def drag(self, e):
        x,y,wx,wy = self.drag_origin; dx=e.x_root-x; dy=e.y_root-y
        if abs(dx)+abs(dy)>4: self.moved=True
        self.root.geometry(f'+{max(0,wx+dx)}+{max(0,wy+dy)}')
    def release(self, e):
        if not self.moved: self.next_expression(); self.refresh(True)

    def refresh(self, show=False):
        if self.busy:
            self.pending = True; self.pending_notice |= show; return
        self.busy = True
        def work():
            try: value = parse_limits(fetch_limits())
            except Exception: value = None
            try: self.root.after(0, lambda: self.finished(value, show))
            except RuntimeError: pass
        threading.Thread(target=work, daemon=True).start()

    def finished(self, value, show):
        self.busy = False; self.last_refresh = time.monotonic()
        if value is not None:
            left, balance, account = value; self.credit.observe(balance, account)
            if show: self.show_notice(self.credit.notice(left))
        elif show: self.show_notice('五小时额度暂不可用')
        if self.pending:
            show_next = self.pending_notice; self.pending = False; self.pending_notice = False
            self.root.after(1000, lambda: self.refresh(show_next))

    def tick(self):
        running = codex_running()
        if running and not self.visible:
            self.visible = True
            if not self.native_mode: self.root.deiconify()
            self.refresh(not self.native_mode)
        elif not running and self.visible:
            self.visible = False; self.root.withdraw()
        if self.events.check() and running:
            self.next_expression(); self.root.after(3000, lambda: self.refresh(True))
        if running and not self.busy and time.monotonic() - self.last_refresh > 60:
            self.refresh(False)
        self.root.after(3000, self.tick)


def main():
    # A local named mutex prevents duplicate startup watchers.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, 'Local\\CodexPetCompanionV1')
    if ctypes.get_last_error() == 183: return
    root = tk.Tk(); Pet(root); root.mainloop()
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]; kernel.CloseHandle(mutex)


if __name__ == '__main__': main()
