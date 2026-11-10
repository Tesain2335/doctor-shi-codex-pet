"""博士士 desktop companion: 16-way pointer gaze and a five-second VOICE panel."""
import ctypes
from ctypes import wintypes
import json
import logging
import math
import os
from pathlib import Path
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal, qVersion
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QIcon, QImage,
                          QPainter, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QLabel, QMenu,
                              QPushButton, QSlider, QSystemTrayIcon, QVBoxLayout, QWidget)

from gaze import gaze_sector
from deepseek_usage import DeepSeekUsage
from pet import CreditTracker, SessionEvents, codex_running, fetch_limits, parse_limits

APP=Path(__file__).resolve().parent
SETTINGS=APP/'settings.json'
ATLAS=APP/'assets/doctor-v2.webp'
STATES=[('idle',6),('running-right',8),('running-left',8),('waving',4),
        ('jumping',5),('failed',8),('waiting',6),('running',6),('review',6)]
FLAGS=Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool
CURRENT_COMPLETION=object()
DATA=Path(os.environ.get('LOCALAPPDATA',str(APP)))/'CodexPet'
LOG=logging.getLogger('CodexPet')


def load_settings():
    try: value=json.loads(SETTINGS.read_text(encoding='utf-8'))
    except (OSError,ValueError): value={}
    if not isinstance(value,dict): value={}
    try:scale=float(value.get('pet_scale',.85))
    except (ValueError,TypeError):scale=.85
    if not math.isfinite(scale):scale=.85
    value['pet_scale']=max(.55,min(1.8,scale))
    value.setdefault('follow_cursor',True)
    return value


def save_settings(value):
    temp=SETTINGS.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(SETTINGS)


def font(family,size,weight=QFont.Weight.Normal):
    f=QFont(family);f.setPixelSize(size);f.setWeight(weight)
    return f


def fit_position(x,y,width,height,bounds):
    return (max(bounds.left(),min(x,bounds.right()-width+1)),
            max(bounds.top(),min(y,bounds.bottom()-height+1)))


def native_window_visible(view):
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.IsWindowVisible.argtypes=[wintypes.HWND];user32.IsWindowVisible.restype=wintypes.BOOL
    return bool(user32.IsWindowVisible(int(view.winId())))


def record_runtime_status(view):
    native_visible=native_window_visible(view)
    state={'pid':os.getpid(),'launch_id':os.environ.get('CODEXPET_LAUNCH_ID'),
           'recorded_at':datetime.now().astimezone().isoformat(),
           'visible':view.isVisible() and native_visible,
           'within_screen':any(s.availableGeometry().contains(view.frameGeometry()) for s in QApplication.screens()),
           'geometry':[view.x(),view.y(),view.width(),view.height()],
           'screens':[[s.availableGeometry().x(),s.availableGeometry().y(),s.availableGeometry().width(),s.availableGeometry().height()] for s in QApplication.screens()]}
    DATA.mkdir(parents=True,exist_ok=True)
    temp=DATA/'companion-status.tmp';temp.write_text(json.dumps(state),encoding='utf-8')
    temp.replace(DATA/'companion-status.json')
    LOG.info('window_status %s',json.dumps(state))


class VoicePanel(QWidget):
    def __init__(self):
        super().__init__(None,FLAGS)
        self.setWindowTitle('博士士 · VOICE 额度提示')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.lines=[];self.timeout=QTimer(self);self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.hide)
        self.hide_deadline=0
        self.resize(490,146)

    def set_notice(self,notice,tokens=None,usage_incomplete=False):
        raw=notice.splitlines()
        self.lines=[]
        if raw and raw[0].startswith('五小时剩余  '):
            self.lines.append('五小时额度还剩 '+raw[0].split('  ',1)[1]+'。')
        else: self.lines.append('五小时额度暂不可用。')
        if tokens is None:
            self.lines.append('DeepSeek 消耗：暂无本轮记录')
        elif usage_incomplete:
            self.lines.append(f'DeepSeek 消耗 ≥ {tokens:,} tokens')
        else:
            self.lines.append(f'DeepSeek 消耗 {tokens:,} tokens')
        if len(raw)>1: self.lines.append(raw[1].replace('  ',' ')+'。')
        self.resize(490,176 if len(self.lines)>2 else 146)
        self.hide_deadline=time.monotonic()+5
        self.timeout.start(5000)
        self.show();self.raise_();self.update()

    def place_near(self,pet):
        screen=QApplication.screenAt(pet.frameGeometry().center()) or QApplication.primaryScreen()
        bounds=screen.availableGeometry();w=min(490,max(280,bounds.width()-32))
        self.resize(w,self.height())
        x=pet.x()+pet.width()-w
        y=pet.y()-self.height()+10
        if y<bounds.top()+8: y=pet.y()+pet.height()-10
        x=max(bounds.left()+8,min(x,bounds.right()-self.width()-8))
        y=max(bounds.top()+8,min(y,bounds.bottom()-self.height()-8))
        self.move(x,y)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height()
        p.setPen(Qt.PenStyle.NoPen)
        # The dark slanted panel retains real per-pixel transparency.
        p.setBrush(QColor(18,24,29,222))
        p.drawPolygon(QPolygonF([QPointF(15,30),QPointF(w-7,16),QPointF(w-17,h-15),QPointF(9,h-2)]))
        p.setBrush(QColor(38,47,54,86))
        p.drawPolygon(QPolygonF([QPointF(w-91,19),QPointF(w-49,18),QPointF(w-113,h-10),QPointF(w-155,h-9)]))
        p.setPen(QPen(QColor(197,205,69,155),1))
        p.drawLine(QPointF(15,h-4),QPointF(w-21,h-17))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#c4ce47'))
        p.drawPolygon(QPolygonF([QPointF(5,11),QPointF(152,6),QPointF(151,31),QPointF(6,36)]))
        # Compact voice mark and the exact, persistent VOICE label.
        p.setPen(QPen(QColor('#eff2dc'),2))
        p.drawLine(22,12,22,31);p.drawLine(13,22,31,22)
        p.drawLine(16,14,16,18);p.drawLine(28,25,28,30)
        p.setPen(QColor('#283020'));p.setFont(font('Bahnschrift',19,QFont.Weight.DemiBold))
        p.drawText(QRect(40,8,106,26),Qt.AlignmentFlag.AlignVCenter,'VOICE')
        p.setFont(font('Microsoft YaHei UI',19,QFont.Weight.Medium));p.setPen(QColor('#f5f6f4'))
        y=52
        for line in self.lines:
            p.drawText(QRectF(32,y,self.width()-65,32),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,line)
            y+=31
        p.setBrush(QColor('#f6f7f4'));p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(w-49,h-31),QPointF(w-29,h-31),QPointF(w-39,h-21)]))
        p.end()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.hide();self.timeout.stop()


class PetView(QWidget):
    clicked=Signal()
    def __init__(self,settings):
        super().__init__(None,FLAGS)
        self.setWindowTitle('博士士 · 鼠标跟随桌宠')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.settings=settings;self.scale=settings['pet_scale']
        image=QImage(str(ATLAS))
        if image.isNull() or image.size().width()!=1536 or image.size().height()!=2288:
            raise RuntimeError('博士士图集缺失或格式不正确')
        self.frames={state:[QPixmap.fromImage(image.copy(col*192,row*208,192,208))
                            for col in range(count)] for row,(state,count) in enumerate(STATES)}
        self.look=[QPixmap.fromImage(image.copy((i%8)*192,(9+i//8)*208,192,208)) for i in range(16)]
        self.frame=self.frames['idle'][0];self.current_sector=None;self.drag_origin=None
        self.transient_until=0;self.frame_clock=time.monotonic();self.last_direction=1
        self.panel=VoicePanel();self.menu=QMenu()
        self.menu.addAction('显示剩余额度',self.clicked.emit)
        self.follow_action=self.menu.addAction('跟随普通鼠标')
        self.follow_action.setCheckable(True);self.follow_action.setChecked(settings['follow_cursor'])
        self.follow_action.toggled.connect(self.set_follow)
        self.menu.addAction('自定义大小…',self.customize)
        self.menu.addAction('重置位置',self.reset_position)
        self.menu.addSeparator();self.menu.addAction('退出桌宠（本次）',QApplication.instance().quit)
        self.resize(round(192*self.scale),round(208*self.scale))
        self.reset_position()
        pos=settings.get('position')
        if isinstance(pos,list) and len(pos)==2:
            try:self.move(QPoint(int(pos[0]),int(pos[1])))
            except (ValueError,TypeError,OverflowError):pass
        self.clamp_to_screen()
        self.screen_hooks=set();self.hook_screens()
        QApplication.instance().screenAdded.connect(self.hook_screens)
        QApplication.instance().screenRemoved.connect(self.hook_screens)
        self.timer=QTimer(self);self.timer.timeout.connect(self.update_gaze);self.timer.start(33)

    def reset_position(self):
        screen=QApplication.primaryScreen()
        if screen is None:return
        b=screen.availableGeometry()
        self.move(b.right()-self.width()-42,b.bottom()-self.height()-45)

    def clamp_to_screen(self):
        screens=QApplication.screens()
        if not screens or self.drag_origin:return
        rect=self.frameGeometry()
        if any(s.availableGeometry().contains(rect) for s in screens):return
        def overlap(screen):
            r=screen.availableGeometry().intersected(rect)
            return max(0,r.width())*max(0,r.height())
        screen=max(screens,key=overlap)
        if overlap(screen)==0:screen=QApplication.primaryScreen() or screen
        self.move(*fit_position(self.x(),self.y(),self.width(),self.height(),screen.availableGeometry()))

    def ensure_visible(self):
        self.clamp_to_screen()
        if not self.isVisible():self.show()
        if QApplication.platformName()=='windows' and not native_window_visible(self):
            self.hide();self.show()
        if hasattr(self,'status_callback'):self.status_callback(self)

    def hook_screens(self,*args):
        for screen in QApplication.screens():
            if id(screen) not in self.screen_hooks:
                self.screen_hooks.add(id(screen));screen.availableGeometryChanged.connect(self.queue_adjust)
        self.queue_adjust()

    def queue_adjust(self,*args):
        QTimer.singleShot(500,self.ensure_visible)

    def set_follow(self,enabled):
        self.settings['follow_cursor']=enabled;save_settings(self.settings)
        self.current_sector=None;self.update_gaze()

    def set_scale(self,value):
        bottom=self.y()+self.height();right=self.x()+self.width()
        self.scale=value/100;self.settings['pet_scale']=self.scale
        self.resize(round(192*self.scale),round(208*self.scale))
        self.move(right-self.width(),bottom-self.height());self.panel.place_near(self)
        save_settings(self.settings)

    def customize(self):
        dialog=QDialog(self);dialog.setWindowTitle('自定义博士士')
        layout=QVBoxLayout(dialog);label=QLabel(f'宠物大小：{round(self.scale*100)}%');layout.addWidget(label)
        slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(55,180);slider.setValue(round(self.scale*100))
        slider.valueChanged.connect(lambda v:(label.setText(f'宠物大小：{v}%'),self.set_scale(v)))
        layout.addWidget(slider);check=QCheckBox('跟随普通鼠标（十六方向）')
        check.setChecked(self.settings['follow_cursor']);check.toggled.connect(self.follow_action.setChecked);layout.addWidget(check)
        button=QPushButton('完成');button.clicked.connect(dialog.accept);layout.addWidget(button)
        dialog.resize(320,145);dialog.exec()

    def update_gaze(self):
        if not self.isVisible(): return
        now=time.monotonic();point=QCursor.pos()
        if self.drag_origin:
            state='running-right' if self.last_direction>=0 else 'running-left'
            frames=self.frames[state];self.frame=frames[int((now-self.frame_clock)/.12)%len(frames)]
        elif now<self.transient_until:
            frames=self.frames['waving'];self.frame=frames[int((now-self.frame_clock)/.16)%len(frames)]
        else:
            center=self.gaze_center()
            self.current_sector=gaze_sector(point.x(),point.y(),center.x(),center.y(),
                                            self.current_sector,24*self.scale) if self.settings['follow_cursor'] else None
            self.frame=self.look[self.current_sector] if self.current_sector is not None else self.frames['idle'][int(now/.22)%6]
        self.update()
        if self.panel.isVisible():self.panel.place_near(self)

    def gaze_center(self):
        return QPointF(self.x()+self.width()/2,self.y()+self.height()*.35)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self.rect(),self.frame);p.end()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:
            self.menu.exec(event.globalPosition().toPoint());return
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag_origin=(event.globalPosition().toPoint(),self.pos());self.moved=False
            self.frame_clock=time.monotonic()

    def mouseMoveEvent(self,event):
        if self.drag_origin:
            delta=event.globalPosition().toPoint()-self.drag_origin[0]
            if delta.manhattanLength()>4:self.moved=True
            self.last_direction=delta.x()
            if self.moved:self.move(self.drag_origin[1]+delta)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.drag_origin:
            was_dragged=self.moved;self.drag_origin=None
            if was_dragged:
                screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
                b=screen.availableGeometry()
                self.move(max(b.left(),min(self.x(),b.right()-self.width())),max(b.top(),min(self.y(),b.bottom()-self.height())))
                self.settings['position']=[self.x(),self.y()];save_settings(self.settings)
            else:self.clicked.emit()

    def react(self):
        self.frame_clock=time.monotonic();self.transient_until=self.frame_clock+.9


class Bus(QObject):
    activity=Signal(bool,object)
    limits=Signal(object,bool,object)


class Controller(QObject):
    def __init__(self,view,watch=True,fetcher=fetch_limits,usage=None):
        super().__init__();self.view=view;self.fetcher=fetcher;self.live=False
        self.bus=Bus();self.bus.activity.connect(self.activity);self.bus.limits.connect(self.received)
        self.credit=CreditTracker();self.busy=False;self.pending=False;self.pending_show=False
        self.usage=usage if usage is not None else DeepSeekUsage()
        self.last_completion=None;self.pending_context=None
        self.stop=threading.Event();self.debounce=QTimer(self);self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(lambda:self.refresh(True))
        self.periodic=QTimer(self);self.periodic.timeout.connect(lambda:self.refresh(False) if self.live else None);self.periodic.start(60000)
        view.clicked.connect(lambda:self.refresh(True))
        QApplication.instance().aboutToQuit.connect(self.stop.set)
        view.show()
        if watch:
            threading.Thread(target=self.watch,daemon=True).start()

    def watch(self):
        events=SessionEvents(Path.home()/'.codex/sessions');events.poll()
        while not self.stop.is_set():
            try:self.bus.activity.emit(codex_running(),events.poll())
            except Exception:pass
            self.stop.wait(2)

    def activity(self,running,completed):
        if running and not self.live:
            self.live=True;self.view.show();self.refresh(False)
        elif not running and self.live:
            self.live=False;self.debounce.stop()
        if completed and running:
            if isinstance(completed,list):self.last_completion=completed[-1]
            self.view.react();self.debounce.start(2500)

    def refresh(self,show,context=CURRENT_COMPLETION):
        context=self.last_completion if context is CURRENT_COMPLETION else context
        if self.busy:
            self.pending=True
            if show:self.pending_show=True;self.pending_context=context
            return
        self.busy=True
        def request():
            try:value=parse_limits(self.fetcher())
            except Exception:value=None
            if not self.stop.is_set():self.bus.limits.emit(value,show,context)
        threading.Thread(target=request,daemon=True).start()

    def received(self,value,show,context=None):
        self.busy=False
        if value is not None:
            left,balance,account=value;self.credit.observe(balance,account)
            if show:
                tokens,incomplete=self.usage.total_for(context)
                self.view.panel.set_notice(self.credit.notice(left),tokens,incomplete);self.view.panel.place_near(self.view)
        elif show:
            tokens,incomplete=self.usage.total_for(context)
            self.view.panel.set_notice('五小时额度暂不可用',tokens,incomplete);self.view.panel.place_near(self.view)
        if self.pending:
            next_show=self.pending_show;next_context=self.pending_context
            self.pending=False;self.pending_show=False;self.pending_context=None
            QTimer.singleShot(500,lambda:self.refresh(next_show,next_context))


def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    LOG.info('gui_start pid=%s interpreter=%s python=%s Qt=%s cwd=%s',os.getpid(),sys.executable,sys.version.split()[0],qVersion(),Path.cwd())
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
    mutex=kernel.CreateMutexW(None,False,'Local\\CodexPetCompanionV2')
    if not mutex:raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error()==183:
        LOG.info('existing_instance: exiting normally');kernel.CloseHandle(mutex);return
    app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False)
    view=PetView(load_settings());controller=Controller(view)
    view.status_callback=record_runtime_status
    for delay in (500,3000,10000,20000):QTimer.singleShot(delay,view.ensure_visible)
    tray=QSystemTrayIcon(QIcon(view.frames['idle'][0]),app)
    tray.setToolTip('博士士 · 右键宠物可自定义与查看额度');tray.setContextMenu(view.menu);tray.show()
    app.exec();controller.stop.set()
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(mutex)


if __name__=='__main__':main()
