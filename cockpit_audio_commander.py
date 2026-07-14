# -*- coding: utf-8 -*-
"""
COCKPIT COMMANDER
Управление звуком и медиа с геймпада для симрейсинга.
Запуск: python cockpit_commander.py   |   Зависимости: requirements.txt
"""

import os
import sys
import json
import copy
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QRectF,
                            QPropertyAnimation, QEvent)
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QToolButton, QComboBox,
    QSlider, QVBoxLayout, QHBoxLayout, QFrame, QStackedWidget, QScrollArea,
    QSpinBox, QButtonGroup, QAbstractButton, QGraphicsOpacityEffect,
    QSystemTrayIcon, QMenu, QInputDialog
)

APP_VERSION = "3.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_FILE = os.path.join(APP_DIR, "icon.ico")
RESIZE_MARGIN = 6

BG       = "#0B0E13"
SURFACE  = "#141922"
SURFACE2 = "#1C232E"
SURFACE3 = "#232C38"
LINE     = "#2A3340"
TEXT     = "#E6EDF3"
MUTED    = "#8391A0"
CYAN     = "#35E0C8"
LED_GREEN = "#38E06A"
LED_AMBER = "#FFB020"
LED_RED   = "#FF3B47"

ACCENTS = {
    "Amber":   ("#FFB020", "#FFC24D", "rgba(255,176,32,0.14)"),
    "Cyan":    ("#35E0C8", "#5CEAD6", "rgba(53,224,200,0.14)"),
    "Crimson": ("#FF3B47", "#FF6169", "rgba(255,59,71,0.14)"),
    "Lime":    ("#9BE850", "#B4EF77", "rgba(155,232,80,0.14)"),
}
CURRENT_ACCENT = ACCENTS["Amber"][0]

ACTIONS = [
    ("media_play_pause",  "Play / Pause",          False),
    ("media_next",        "Следующий трек",         False),
    ("media_prev",        "Предыдущий трек",        False),
    ("media_stop",        "Стоп",                   False),
    ("master_vol_up",     "Общая громкость  +",     False),
    ("master_vol_down",   "Общая громкость  −",     False),
    ("master_mute",       "Общий mute",             False),
    ("master_vol_smooth", "Общая громкость (стик)", False),
    ("app_vol_up",        "Громкость прил.  +",     True),
    ("app_vol_down",      "Громкость прил.  −",     True),
    ("app_mute",          "Mute приложения",        True),
    ("app_vol_smooth",    "Громкость прил. (стик)", True),
    ("next_profile",      "Следующий профиль",      False),
]
ACTION_NEEDS_TARGET = {a[0]: a[2] for a in ACTIONS}
SMOOTH_ACTIONS = {"master_vol_smooth", "app_vol_smooth"}

POSITIONS = [
    ("Сверху слева", "top-left"), ("Сверху по центру", "top-center"),
    ("Сверху справа", "top-right"), ("По центру слева", "center-left"),
    ("По центру", "center-center"), ("По центру справа", "center-right"),
    ("Снизу слева", "bottom-left"), ("Снизу по центру", "bottom-center"),
    ("Снизу справа", "bottom-right"),
]

# Рули/педали по умолчанию не открываем, чтобы не забирать Force Feedback у игры.
WHEEL_KEYWORDS = ("wheel", "moza", "fanatec", "thrustmaster", "logitech g",
                  "simucube", "simagic", "cammus", "asetek", "racing",
                  "pedal", "shifter", "handbrake", "sim ", "ks ", "r5", "r9", "r16")


def is_wheelish(name):
    n = (name or "").lower()
    return any(k in n for k in WHEEL_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
#  Конфиг
# ─────────────────────────────────────────────────────────────────────────────
def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "CockpitCommander")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")


def _starter_bindings():
    return [
        {"token": "button:0", "action": "media_play_pause", "target": "", "layer": "base"},
        {"token": "button:1", "action": "media_next",       "target": "", "layer": "base"},
        {"token": "button:2", "action": "media_prev",       "target": "", "layer": "base"},
        {"token": "hat:0:up",   "action": "master_vol_up",   "target": "", "layer": "base"},
        {"token": "hat:0:down", "action": "master_vol_down", "target": "", "layer": "base"},
    ]


def _empty_profile():
    return {"bindings": [], "shift_token": "", "device_guid": "", "device_name": ""}


def default_config():
    prof = _empty_profile()
    prof["bindings"] = _starter_bindings()
    return {
        "version": 3,
        "accent": "Amber",
        "volume_step": 5,
        "minimize_to_tray": False,
        "autostart": False,
        "toast_enabled": True,
        "toast_scale": 100,
        "toast_pos": "top-center",
        "toast_duration": 1400,
        "toast_color": "",   # пусто = использовать акцентный цвет приложения
        "disabled_devices": [],
        "known_devices": [],
        "active_profile": "По умолчанию",
        "profiles": {"По умолчанию": prof},
    }


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default_config()

    base = default_config()
    for k, v in base.items():
        data.setdefault(k, v)

    if not isinstance(data.get("profiles"), dict) or not data["profiles"]:
        old = data.get("bindings", _starter_bindings())
        prof = _empty_profile()
        prof["bindings"] = old
        data["profiles"] = {"По умолчанию": prof}
        data["active_profile"] = "По умолчанию"
    data.pop("bindings", None)

    for prof in data["profiles"].values():
        for k, v in _empty_profile().items():
            prof.setdefault(k, v)
        for b in prof["bindings"]:
            b.setdefault("target", "")
            b.setdefault("layer", "base")
            b.setdefault("device", "")

    if data["active_profile"] not in data["profiles"]:
        data["active_profile"] = next(iter(data["profiles"]))
    return data


def save_config(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Не удалось сохранить конфиг:", e)


def token_label(token):
    if not token:
        return "—"
    inp = token.split("|", 1)[1] if "|" in token else token
    parts = inp.split(":")
    if parts[0] == "button":
        return f"КНОПКА {parts[1]}"
    if parts[0] == "hat":
        arrows = {"up": "↑", "down": "↓", "left": "←", "right": "→"}
        return f"D-PAD {arrows.get(parts[2], parts[2])}"
    if parts[0] == "axis":
        return f"СТИК {parts[1]} {'＋' if parts[2] == '+' else '－'}"
    return inp


def pct(v):
    return f"{int(round(v * 100))}%" if v is not None else "—"


# ─────────────────────────────────────────────────────────────────────────────
#  Аудио (Windows / pycaw)
# ─────────────────────────────────────────────────────────────────────────────
class Audio:
    def __init__(self):
        self.ok = False
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import (AudioUtilities, ISimpleAudioVolume,
                                     IAudioEndpointVolume)
            self._cast, self._PTR, self._CLSCTX = cast, POINTER, CLSCTX_ALL
            self._AU, self._ISAV, self._IEV = AudioUtilities, ISimpleAudioVolume, IAudioEndpointVolume
            self.ok = True
        except Exception:
            pass

    def _endpoint(self):
        spk = self._AU.GetSpeakers()
        itf = spk.Activate(self._IEV._iid_, self._CLSCTX, None)
        return self._cast(itf, self._PTR(self._IEV))

    def bump_master(self, delta):
        if not self.ok:
            return None
        try:
            ep = self._endpoint()
            new = max(0.0, min(1.0, ep.GetMasterVolumeLevelScalar() + delta))
            ep.SetMasterVolumeLevelScalar(new, None)
            return new
        except Exception:
            return None

    def toggle_master_mute(self):
        if not self.ok:
            return None
        try:
            ep = self._endpoint()
            muted = not ep.GetMute()
            ep.SetMute(1 if muted else 0, None)
            return muted
        except Exception:
            return None

    def _sessions(self):
        try:
            return self._AU.GetAllSessions()
        except Exception:
            return []

    def _session_name(self, s):
        try:
            if s.Process:
                n = s.Process.name()
                return n[:-4] if n.lower().endswith(".exe") else n
        except Exception:
            pass
        return "System"

    def list_sessions(self):
        out, seen = [], set()
        for s in self._sessions():
            try:
                if not s.Process:
                    continue
                name = self._session_name(s)
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                vol = s._ctl.QueryInterface(self._ISAV)
                out.append((name, vol.GetMasterVolume()))
            except Exception:
                continue
        return sorted(out, key=lambda x: x[0].lower())

    def list_app_names(self):
        return [n for n, _ in self.list_sessions()]

    def _for_app(self, name):
        name = (name or "").lower()
        res = []
        for s in self._sessions():
            try:
                if s.Process and name and name in s.Process.name().lower():
                    res.append(s._ctl.QueryInterface(self._ISAV))
            except Exception:
                continue
        return res

    def set_app_volume(self, name, value):
        for v in self._for_app(name):
            try:
                v.SetMasterVolume(max(0.0, min(1.0, value)), None)
            except Exception:
                pass

    def bump_app(self, name, delta):
        new = None
        for v in self._for_app(name):
            try:
                new = max(0.0, min(1.0, v.GetMasterVolume() + delta))
                v.SetMasterVolume(new, None)
            except Exception:
                pass
        return new

    def toggle_app_mute(self, name):
        vols = self._for_app(name)
        if not vols:
            return None
        muted = not vols[0].GetMute()
        for v in vols:
            try:
                v.SetMute(1 if muted else 0, None)
            except Exception:
                pass
        return muted

    def media(self, vk):
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        except Exception:
            pass


def run_action(audio, action, target, step):
    VK = {"play": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2}
    if action == "media_play_pause":
        audio.media(VK["play"]);  return "Play / Pause"
    if action == "media_next":
        audio.media(VK["next"]);  return "Следующий трек"
    if action == "media_prev":
        audio.media(VK["prev"]);  return "Предыдущий трек"
    if action == "media_stop":
        audio.media(VK["stop"]);  return "Стоп"
    if action == "master_vol_up":
        return f"Общий звук  {pct(audio.bump_master(step))}"
    if action == "master_vol_down":
        return f"Общий звук  {pct(audio.bump_master(-step))}"
    if action == "master_mute":
        m = audio.toggle_master_mute()
        return "Звук выключен" if m else "Звук включён"
    if action == "app_vol_up":
        v = audio.bump_app(target, step)
        return f"{target}  {pct(v)}" if v is not None else f"{target}: не играет"
    if action == "app_vol_down":
        v = audio.bump_app(target, -step)
        return f"{target}  {pct(v)}" if v is not None else f"{target}: не играет"
    if action == "app_mute":
        m = audio.toggle_app_mute(target)
        if m is None:
            return f"{target}: не играет"
        return f"{target}: без звука" if m else f"{target}: звук включён"
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Поток геймпада
# ─────────────────────────────────────────────────────────────────────────────
class InputThread(QThread):
    pressed = Signal(str)                  # "{guid}|button:3"
    released = Signal(str)
    status = Signal(bool, str)
    axisValue = Signal(str, int, float)    # guid, ось, значение
    newDevice = Signal(str, str, bool)     # guid, имя, выключено?

    ACT, REL = 0.6, 0.35

    def __init__(self):
        super().__init__()
        self._running = True
        self.disabled = set()
        self.known = set()
        self.rescan = False

    def stop(self):
        self._running = False

    @staticmethod
    def _hat_token(h, value):
        x, y = value
        if y == 1:    return f"hat:{h}:up"
        if y == -1:   return f"hat:{h}:down"
        if x == 1:    return f"hat:{h}:right"
        if x == -1:   return f"hat:{h}:left"
        return None

    def run(self):
        import pygame
        pygame.init()
        pygame.joystick.init()
        sticks, hat_dir, axis_zone = {}, {}, {}

        while self._running:
            if self.rescan:
                self.rescan = False
                try:
                    pygame.joystick.quit()
                    pygame.joystick.init()
                except Exception:
                    pass
                sticks.clear(); hat_dir.clear(); axis_zone.clear()
                self.status.emit(False, "")

            try:
                events = pygame.event.get()
            except Exception:
                pygame.time.wait(50)
                continue

            for ev in events:
                t = ev.type
                if t == pygame.JOYDEVICEADDED:
                    try:
                        js = pygame.joystick.Joystick(ev.device_index)
                        guid, name = js.get_guid(), js.get_name()
                    except Exception:
                        continue
                    if guid not in self.known:
                        self.known.add(guid)
                        if is_wheelish(name):
                            self.disabled.add(guid)
                    self.newDevice.emit(guid, name, guid in self.disabled)
                    if guid in self.disabled:
                        try:
                            js.quit()   # не держим устройство — FFB остаётся у игры
                        except Exception:
                            pass
                        continue
                    sticks[js.get_instance_id()] = (js, guid)
                    self.status.emit(True, name)
                    continue
                if t == pygame.JOYDEVICEREMOVED:
                    iid = getattr(ev, "instance_id", None)
                    sticks.pop(iid, None)
                    for d in (hat_dir, axis_zone):
                        for k in [k for k in d if k[0] == iid]:
                            d.pop(k, None)
                    if not sticks:
                        self.status.emit(False, "")
                    continue

                iid = getattr(ev, "instance_id", None)
                if iid not in sticks:
                    continue
                guid = sticks[iid][1]

                if t == pygame.JOYBUTTONDOWN:
                    self.pressed.emit(f"{guid}|button:{ev.button}")
                elif t == pygame.JOYBUTTONUP:
                    self.released.emit(f"{guid}|button:{ev.button}")
                elif t == pygame.JOYHATMOTION:
                    key = (iid, ev.hat)
                    new = self._hat_token(ev.hat, ev.value)
                    old = hat_dir.get(key)
                    if new != old:
                        if old:
                            self.released.emit(f"{guid}|{old}")
                        if new:
                            self.pressed.emit(f"{guid}|{new}")
                        hat_dir[key] = new
                elif t == pygame.JOYAXISMOTION:
                    self.axisValue.emit(guid, ev.axis, ev.value)
                    key = (iid, ev.axis)
                    v = ev.value
                    if v >= self.ACT:
                        zone = "pos"
                    elif v <= -self.ACT:
                        zone = "neg"
                    elif -self.REL <= v <= self.REL:
                        zone = "neutral"
                    else:
                        zone = axis_zone.get(key) or "neutral"
                    prev = axis_zone.get(key)
                    if prev is None:
                        axis_zone[key] = zone
                    elif zone != prev:
                        if prev == "pos":
                            self.released.emit(f"{guid}|axis:{ev.axis}:+")
                        elif prev == "neg":
                            self.released.emit(f"{guid}|axis:{ev.axis}:-")
                        if prev == "neutral" and zone == "pos":
                            self.pressed.emit(f"{guid}|axis:{ev.axis}:+")
                        elif prev == "neutral" and zone == "neg":
                            self.pressed.emit(f"{guid}|axis:{ev.axis}:-")
                        axis_zone[key] = zone

            pygame.time.wait(10)

        try:
            pygame.quit()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Базовые виджеты
# ─────────────────────────────────────────────────────────────────────────────
class ShiftLights(QWidget):
    CELLS = 15

    def __init__(self):
        super().__init__()
        self.setFixedHeight(16)
        self.setMinimumWidth(200)
        self._level = -1
        self._timer = QTimer(self)
        self._timer.setInterval(28)
        self._timer.timeout.connect(self._step)

    def sweep(self):
        self._level = 0
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _step(self):
        self._level += 1
        if self._level >= self.CELLS + 4:
            self._level = -1
            self._timer.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n, gap = self.CELLS, 4
        w = (self.width() - gap * (n - 1)) / n
        for i in range(n):
            if i < n * 0.5:
                c = QColor(LED_GREEN)
            elif i < n * 0.8:
                c = QColor(LED_AMBER)
            else:
                c = QColor(LED_RED)
            c.setAlpha(255 if 0 <= self._level and i <= self._level else 40)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(i * (w + gap), 0, w, self.height()), 2, 2)
        p.end()


class StatusDot(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(10, 10)
        self._on = False

    def set_on(self, on):
        self._on = on
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(LED_GREEN if self._on else "#4A5563"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 10, 10)
        p.end()


class ToggleSwitch(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        p.setBrush(QColor(CURRENT_ACCENT) if on else QColor(SURFACE3))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 13, 13)
        r = 20
        x = self.width() - r - 3 if on else 3
        p.setBrush(QColor(BG) if on else QColor(TEXT))
        p.drawEllipse(QRectF(x, 3, r, r))
        p.end()


class Dropdown(QComboBox):
    """Открывается кликом; колесо мыши не меняет значение. Если задан
    open_provider — пункты перечитываются при каждом открытии."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setMaxVisibleItems(14)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.open_provider = None

    def wheelEvent(self, e):
        e.ignore()

    def showPopup(self):
        if callable(self.open_provider):
            cur_text, cur_data = self.currentText(), self.currentData()
            self.blockSignals(True)
            self.clear()
            for label, data in self.open_provider():
                self.addItem(label, data)
            i = self.findData(cur_data)
            if i < 0:
                i = self.findText(cur_text)
            if i >= 0:
                self.setCurrentIndex(i)
            elif self.isEditable():
                self.setCurrentText(cur_text)
            self.blockSignals(False)
        super().showPopup()


# ─────────────────────────────────────────────────────────────────────────────
#  Плашка (десктоп)
# ─────────────────────────────────────────────────────────────────────────────
class Toast(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint |
            Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.enabled = True
        self.scale = 1.0
        self.pos_key = "top-center"
        self.duration = 1400
        self.color = ""   # пусто = акцентный цвет приложения

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(350)
        self._fade.finished.connect(self._after_fade)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._begin_fade)

    def configure(self, enabled, scale, pos_key, duration=1400, color=""):
        self.enabled, self.scale, self.pos_key = enabled, scale, pos_key
        self.duration, self.color = duration, color

    def show_toast(self, text):
        if not self.enabled or not text:
            return
        s = self.scale
        accent = self.color or CURRENT_ACCENT
        self.label.setStyleSheet(
            f"background:{SURFACE}; color:{TEXT};"
            f"border:1px solid {LINE}; border-left:{max(2, int(3*s))}px solid {accent};"
            f"border-radius:{int(10*s)}px; padding:{int(9*s)}px {int(18*s)}px;"
            f"font-size:{int(15*s)}px; font-weight:600;")
        self.label.setText(text)

        scr = QApplication.primaryScreen().geometry()
        self.adjustSize()
        m = int(46 * s)
        v, h = self.pos_key.split("-")
        x = (scr.left() + m if h == "left"
             else scr.right() - self.width() - m if h == "right"
             else scr.center().x() - self.width() // 2)
        y = (scr.top() + m if v == "top"
             else scr.bottom() - self.height() - m if v == "bottom"
             else scr.center().y() - self.height() // 2)
        self.move(x, y)

        self._fade.stop()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start(self.duration)

    def _begin_fade(self):
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self):
        if self._effect.opacity() < 0.05:
            self.hide()


# ─────────────────────────────────────────────────────────────────────────────
#  Строка привязки
# ─────────────────────────────────────────────────────────────────────────────
class BindingRow(QFrame):
    changed = Signal()
    bindRequested = Signal(object)
    deleteRequested = Signal(object)

    def __init__(self, binding, app_names_provider):
        super().__init__()
        self.setObjectName("card")
        self.binding = binding

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)

        self.badge = QLabel(token_label(binding.get("token", "")))
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedWidth(100)
        lay.addWidget(self.badge)

        self.dev = QLabel("")
        self.dev.setObjectName("devtag")
        self.dev.setFixedWidth(78)
        lay.addWidget(self.dev)
        self._set_dev(binding.get("device", ""))

        self.action = Dropdown()
        for aid, label, _ in ACTIONS:
            self.action.addItem(label, aid)
        self.action.setCurrentIndex(max(0, self.action.findData(
            binding.get("action", "media_play_pause"))))
        self.action.currentIndexChanged.connect(self._on_action)
        self.action.setMinimumWidth(140)
        lay.addWidget(self.action, 3)

        self.target = Dropdown()
        self.target.setEditable(True)
        self.target.setMinimumWidth(110)
        self.target.open_provider = lambda: [(n, n) for n in app_names_provider()]
        for n in app_names_provider():
            self.target.addItem(n, n)
        self.target.setCurrentText(binding.get("target", ""))
        self.target.currentTextChanged.connect(self._on_target)
        self.target.lineEdit().setPlaceholderText("имя .exe, напр. spotify")
        lay.addWidget(self.target, 1)

        self.bindBtn = QPushButton("НАЗНАЧИТЬ")
        self.bindBtn.setObjectName("bindBtn")
        self.bindBtn.setCursor(Qt.PointingHandCursor)
        self.bindBtn.clicked.connect(lambda: self.bindRequested.emit(self))
        lay.addWidget(self.bindBtn)

        self.delBtn = QToolButton()
        self.delBtn.setText("✕")
        self.delBtn.setObjectName("delBtn")
        self.delBtn.setCursor(Qt.PointingHandCursor)
        self.delBtn.clicked.connect(lambda: self.deleteRequested.emit(self))
        lay.addWidget(self.delBtn)

        self._sync_target_visibility()

    def _set_dev(self, name):
        short = name or "любое устройство"
        self.dev.setText(short if len(short) <= 14 else short[:13] + "…")
        self.dev.setToolTip(name or "срабатывает на любом устройстве")

    def _on_action(self):
        self.binding["action"] = self.action.currentData()
        self._sync_target_visibility()
        self.changed.emit()

    def _on_target(self, txt):
        self.binding["target"] = txt
        self.changed.emit()

    def _sync_target_visibility(self):
        self.target.setVisible(ACTION_NEEDS_TARGET.get(self.action.currentData(), False))

    def set_token(self, token, device=""):
        self.binding["token"] = token
        self.binding["device"] = device
        self.badge.setText(token_label(token))
        self._set_dev(device)
        self.changed.emit()

    def set_listening(self, on):
        self.bindBtn.setText("НАЖМИ / ТОЛКНИ…" if on else "НАЗНАЧИТЬ")
        self.setProperty("listening", "1" if on else "")
        self.badge.setProperty("listening", "1" if on else "")
        for w in (self, self.badge):
            w.style().unpolish(w); w.style().polish(w)

    def flash(self):
        self.setProperty("fired", "1")
        self.style().unpolish(self); self.style().polish(self)
        QTimer.singleShot(220, self._unflash)

    def _unflash(self):
        self.setProperty("fired", "")
        self.style().unpolish(self); self.style().polish(self)


class MixerRow(QFrame):
    def __init__(self, name, volume, audio):
        super().__init__()
        self.setObjectName("card")
        self.name = name
        self.audio = audio
        self._dragging = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 16, 8)
        lay.setSpacing(12)

        nm = QLabel(name)
        nm.setObjectName("mixName")
        nm.setFixedWidth(150)
        lay.addWidget(nm)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setObjectName("mixSlider")
        self.slider.setRange(0, 100)
        self.slider.setValue(int(round(volume * 100)))
        self.slider.valueChanged.connect(self._on_change)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.slider.sliderReleased.connect(lambda: setattr(self, "_dragging", False))
        lay.addWidget(self.slider, 1)

        self.pct = QLabel(f"{int(round(volume*100))}%")
        self.pct.setObjectName("mixPct")
        self.pct.setFixedWidth(46)
        self.pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.pct)

    def _on_change(self, v):
        self.pct.setText(f"{v}%")
        self.audio.set_app_volume(self.name, v / 100.0)

    def set_volume_external(self, volume):
        if self._dragging:
            return
        v = int(round(volume * 100))
        if v == self.slider.value():
            return
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.pct.setText(f"{v}%")


class TitleBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(48)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(10)

        self.dot = StatusDot()
        lay.addWidget(self.dot)

        self.title = QLabel()
        self.title.setObjectName("winTitle")
        lay.addWidget(self.title)
        lay.addStretch(1)

        mn = QToolButton(); mn.setText("—"); mn.setObjectName("winBtn")
        mn.clicked.connect(self.win.showMinimized)
        mx = QToolButton(); mx.setText("▢"); mx.setObjectName("winBtn")
        mx.clicked.connect(self._toggle_max)
        cl = QToolButton(); cl.setText("✕"); cl.setObjectName("winClose")
        cl.clicked.connect(self.win.close)
        for b in (mn, mx, cl):
            b.setCursor(Qt.PointingHandCursor)
            lay.addWidget(b)

    def _toggle_max(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def set_accent(self, accent):
        self.title.setText(
            f"<span style='color:{TEXT}'>COCKPIT</span>"
            f"&nbsp;<span style='color:{accent}'>COMMANDER</span>")

    def set_status(self, on, _name):
        self.dot.set_on(on)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._toggle_max()


class NavButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


class Segment(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("seg")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


# ─────────────────────────────────────────────────────────────────────────────
#  Главное окно
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.audio = Audio()
        self.capture_target = None       # BindingRow | "shift" | None
        self.binding_rows = []
        self.current_layer = "base"
        self.held = set()
        self.axis_values = {}
        self.device_names = {}
        self.device_rows = {}
        self._quitting = False
        self._last_toast_ms = 0
        self.tray = None

        self.toast = Toast()
        self._sync_toast()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setMinimumSize(860, 620)
        self.resize(980, 700)
        self.setObjectName("win")
        if os.path.exists(ICON_FILE):
            self.setWindowIcon(QIcon(ICON_FILE))

        root = QVBoxLayout(self)
        root.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)
        root.setSpacing(0)
        self.setMouseTracking(True)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        led_wrap = QWidget(); led_wrap.setObjectName("ledWrap")
        led_lay = QHBoxLayout(led_wrap)
        led_lay.setContentsMargins(16, 6, 16, 10)
        self.leds = ShiftLights()
        led_lay.addWidget(self.leds)
        root.addWidget(led_wrap)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        side = QWidget(); side.setObjectName("sidebar")
        side.setFixedWidth(180)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(12, 16, 12, 14)
        side_lay.setSpacing(6)
        self.nav_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        for name in ("Назначения", "Микшер", "Настройки"):
            b = NavButton(name)
            self.nav_group.addButton(b)
            side_lay.addWidget(b)
        side_lay.addStretch(1)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("ver")
        side_lay.addWidget(ver)
        body.addWidget(side)

        content = QWidget(); content.setObjectName("content")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.addWidget(self.stack, 1)
        body.addWidget(content, 1)

        self._build_bindings_page()
        self._build_mixer_page()
        self._build_settings_page()

        for i, b in enumerate(self.nav_group.buttons()):
            b.clicked.connect(lambda _=False, idx=i: self.stack.setCurrentIndex(idx))
        self.nav_group.buttons()[0].setChecked(True)

        self.apply_theme()
        self._setup_tray()

        self.smooth_timer = QTimer(self)
        self.smooth_timer.setInterval(50)
        self.smooth_timer.timeout.connect(self._smooth_tick)
        self.smooth_timer.start()

        self.thread = InputThread()
        self.thread.disabled = set(self.cfg.get("disabled_devices", []))
        self.thread.known = set(self.cfg.get("known_devices", []))
        self.thread.pressed.connect(self.on_press)
        self.thread.released.connect(self.on_release)
        self.thread.status.connect(lambda on, n: self.title_bar.set_status(on, n))
        self.thread.axisValue.connect(self._on_axis)
        self.thread.newDevice.connect(self._on_new_device)
        self.thread.start()

    def profile(self):
        return self.cfg["profiles"][self.cfg["active_profile"]]

    # ── страница «Назначения» ──
    def _build_bindings_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)

        prow = QHBoxLayout()
        prow.setSpacing(8)
        pl = QLabel("ПРОФИЛЬ")
        pl.setObjectName("field")
        prow.addWidget(pl)
        self.profile_box = Dropdown()
        self.profile_box.setMinimumWidth(170)
        self.profile_box.currentIndexChanged.connect(self._on_profile_change)
        prow.addWidget(self.profile_box)

        dl = QLabel("Устройство:")
        dl.setObjectName("field")
        prow.addWidget(dl)
        self.profile_dev = Dropdown()
        self.profile_dev.setMinimumWidth(170)
        self.profile_dev.open_provider = self._device_options
        self.profile_dev.currentIndexChanged.connect(self._on_profile_device)
        prow.addWidget(self.profile_dev)

        pmenu_btn = QToolButton()
        pmenu_btn.setText("⋯")
        pmenu_btn.setObjectName("menuBtn")
        pmenu_btn.setCursor(Qt.PointingHandCursor)
        pmenu_btn.setPopupMode(QToolButton.InstantPopup)
        pmenu = QMenu(pmenu_btn)
        pmenu.addAction("Новый профиль…").triggered.connect(self._profile_new)
        pmenu.addAction("Переименовать…").triggered.connect(self._profile_rename)
        pmenu.addAction("Дублировать").triggered.connect(self._profile_dup)
        pmenu.addSeparator()
        pmenu.addAction("Удалить").triggered.connect(self._profile_delete)
        pmenu_btn.setMenu(pmenu)
        prow.addWidget(pmenu_btn)
        prow.addStretch(1)
        lay.addLayout(prow)

        srow = QHBoxLayout()
        srow.setSpacing(8)
        self.seg_base = Segment("Базовый слой")
        self.seg_shift = Segment("Слой Shift")
        seg_group = QButtonGroup(self)
        seg_group.addButton(self.seg_base)
        seg_group.addButton(self.seg_shift)
        self.seg_base.setChecked(True)
        self.seg_base.clicked.connect(lambda: self._set_layer("base"))
        self.seg_shift.clicked.connect(lambda: self._set_layer("shift"))
        srow.addWidget(self.seg_base)
        srow.addWidget(self.seg_shift)

        srow.addSpacing(14)
        skl = QLabel("Кнопка Shift:")
        skl.setObjectName("field")
        srow.addWidget(skl)
        self.shift_badge = QLabel("—")
        self.shift_badge.setObjectName("badge")
        self.shift_badge.setAlignment(Qt.AlignCenter)
        self.shift_badge.setFixedWidth(112)
        srow.addWidget(self.shift_badge)
        self.shift_btn = QPushButton("НАЗНАЧИТЬ")
        self.shift_btn.setObjectName("bindBtn")
        self.shift_btn.setCursor(Qt.PointingHandCursor)
        self.shift_btn.clicked.connect(self.start_shift_capture)
        srow.addWidget(self.shift_btn)
        shift_clear = QToolButton()
        shift_clear.setText("✕"); shift_clear.setObjectName("delBtn")
        shift_clear.setCursor(Qt.PointingHandCursor)
        shift_clear.clicked.connect(self._clear_shift)
        srow.addWidget(shift_clear)

        srow.addStretch(1)
        add = QPushButton("+  Добавить")
        add.setObjectName("primary")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.add_binding)
        srow.addWidget(add)
        lay.addLayout(srow)

        hint = QLabel("«Назначить» → нажми кнопку, крестовину или толкни стик. "
                      "Для плавной громкости выбери действие «…(стик)» и толкни стик в сторону «громче».")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        if not self.audio.ok:
            warn = QLabel("⚠  Управление звуком доступно только на Windows.")
            warn.setObjectName("warn")
            warn.setWordWrap(True)
            lay.addWidget(warn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scroll")
        holder = QWidget()
        self.bindings_lay = QVBoxLayout(holder)
        self.bindings_lay.setContentsMargins(0, 0, 8, 0)
        self.bindings_lay.setSpacing(8)
        self.bindings_lay.addStretch(1)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

        self.stack.addWidget(page)

        self._reload_profile_box()
        self._reload_profile_dev()
        self.rebuild_binding_rows()
        self.refresh_shift_badge()

    def _device_options(self):
        opts = [("Любое устройство", "")]
        for guid, name in self.device_names.items():
            opts.append((name, guid))
        prof = self.profile()
        if prof.get("device_guid") and prof["device_guid"] not in self.device_names:
            opts.append((prof.get("device_name") or "…(не подключено)", prof["device_guid"]))
        return opts

    def _reload_profile_dev(self):
        self.profile_dev.blockSignals(True)
        self.profile_dev.clear()
        for label, data in self._device_options():
            self.profile_dev.addItem(label, data)
        i = self.profile_dev.findData(self.profile().get("device_guid", ""))
        self.profile_dev.setCurrentIndex(max(0, i))
        self.profile_dev.blockSignals(False)

    def _on_profile_device(self, _):
        guid = self.profile_dev.currentData() or ""
        prof = self.profile()
        prof["device_guid"] = guid
        prof["device_name"] = self.device_names.get(guid, prof.get("device_name", "")) if guid else ""
        save_config(self.cfg)

    def _reload_profile_box(self):
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        for name in self.cfg["profiles"]:
            self.profile_box.addItem(name)
        i = self.profile_box.findText(self.cfg["active_profile"])
        self.profile_box.setCurrentIndex(max(0, i))
        self.profile_box.blockSignals(False)

    def _activate_profile(self, name):
        if name not in self.cfg["profiles"]:
            return
        self.cfg["active_profile"] = name
        self.held.clear()
        self._reload_profile_box()
        self._reload_profile_dev()
        self.rebuild_binding_rows()
        self.refresh_shift_badge()
        save_config(self.cfg)

    def _on_profile_change(self, _):
        name = self.profile_box.currentText()
        if name and name != self.cfg["active_profile"]:
            self._activate_profile(name)

    def _profile_new(self):
        name, ok = QInputDialog.getText(self, "Новый профиль", "Название профиля:")
        name = (name or "").strip()
        if ok and name and name not in self.cfg["profiles"]:
            self.cfg["profiles"][name] = _empty_profile()
            self._activate_profile(name)

    def _profile_rename(self):
        cur = self.cfg["active_profile"]
        name, ok = QInputDialog.getText(self, "Переименовать", "Новое название:", text=cur)
        name = (name or "").strip()
        if ok and name and name not in self.cfg["profiles"]:
            self.cfg["profiles"][name] = self.cfg["profiles"].pop(cur)
            self._activate_profile(name)

    def _profile_dup(self):
        cur = self.cfg["active_profile"]
        base = cur + " (копия)"
        name, n = base, 2
        while name in self.cfg["profiles"]:
            name = f"{base} {n}"; n += 1
        self.cfg["profiles"][name] = copy.deepcopy(self.cfg["profiles"][cur])
        self._activate_profile(name)

    def _profile_delete(self):
        if len(self.cfg["profiles"]) <= 1:
            return
        del self.cfg["profiles"][self.cfg["active_profile"]]
        self._activate_profile(next(iter(self.cfg["profiles"])))

    def cycle_profile(self):
        names = list(self.cfg["profiles"])
        if len(names) < 2:
            return
        i = names.index(self.cfg["active_profile"])
        self._activate_profile(names[(i + 1) % len(names)])

    # ── слои ──
    def _set_layer(self, layer):
        self.current_layer = layer
        self._apply_layer_visibility()

    def _apply_layer_visibility(self):
        for r in self.binding_rows:
            r.setVisible(r.binding.get("layer", "base") == self.current_layer)

    # ── строки привязок ──
    def _add_row_widget(self, binding):
        provider = (lambda: self.audio.list_app_names()) if self.audio.ok else (lambda: [])
        row = BindingRow(binding, provider)
        row.changed.connect(self.persist)
        row.bindRequested.connect(self.start_capture)
        row.deleteRequested.connect(self.remove_binding)
        self.bindings_lay.insertWidget(self.bindings_lay.count() - 1, row)
        self.binding_rows.append(row)

    def rebuild_binding_rows(self):
        for r in self.binding_rows:
            r.setParent(None); r.deleteLater()
        self.binding_rows = []
        for b in self.profile()["bindings"]:
            self._add_row_widget(b)
        self._apply_layer_visibility()

    def add_binding(self):
        b = {"token": "", "action": "media_play_pause", "target": "",
             "layer": self.current_layer, "device": ""}
        self.profile()["bindings"].append(b)
        self._add_row_widget(b)
        self._apply_layer_visibility()
        self.persist()

    def remove_binding(self, row):
        if row in self.binding_rows:
            self.binding_rows.remove(row)
        if row.binding in self.profile()["bindings"]:
            self.profile()["bindings"].remove(row.binding)
        row.setParent(None); row.deleteLater()
        if self.capture_target is row:
            self.capture_target = None
        self.persist()

    # ── захват ввода ──
    def _end_capture(self):
        t = self.capture_target
        if isinstance(t, BindingRow):
            t.set_listening(False)
        elif t == "shift":
            self.shift_btn.setText("НАЗНАЧИТЬ")
        self.capture_target = None

    def start_capture(self, row):
        was = self.capture_target
        self._end_capture()
        if was is row:
            return
        self.capture_target = row
        row.set_listening(True)

    def start_shift_capture(self):
        was = self.capture_target
        self._end_capture()
        if was == "shift":
            return
        self.capture_target = "shift"
        self.shift_btn.setText("НАЖМИ…")

    def _clear_shift(self):
        self.profile()["shift_token"] = ""
        self.refresh_shift_badge()
        save_config(self.cfg)

    def refresh_shift_badge(self):
        self.shift_badge.setText(token_label(self.profile().get("shift_token", "")))

    def _assign_capture(self, token):
        guid = token.split("|", 1)[0] if "|" in token else ""
        dev_name = self.device_names.get(guid, "")
        t = self.capture_target
        if t == "shift":
            self.profile()["shift_token"] = token
            self.refresh_shift_badge()
        elif isinstance(t, BindingRow):
            layer = t.binding.get("layer", "base")
            for r in self.binding_rows:
                if r is not t and r.binding.get("layer", "base") == layer \
                        and r.binding.get("token") == token:
                    r.set_token("")
            t.set_token(token, dev_name)
        self._end_capture()
        self.leds.sweep()
        self.persist()

    # ── обработка ввода ──
    @staticmethod
    def _matches(binding_tok, event_tok, prof_dev=""):
        """Токен с GUID совпадает только со своим устройством. Токен без GUID —
        с любым устройством (или только с устройством профиля, если оно задано)."""
        if not binding_tok:
            return False
        if binding_tok == event_tok:
            return True
        if "|" not in binding_tok:
            guid, _, inp = event_tok.partition("|")
            if prof_dev and guid != prof_dev:
                return False
            return binding_tok == inp
        return False

    def _shift_held(self, shift_tok, prof_dev):
        return bool(shift_tok) and any(
            self._matches(shift_tok, h, prof_dev) for h in self.held)

    def on_press(self, token):
        if self.capture_target is not None:
            self._assign_capture(token)
            return

        self.held.add(token)
        prof = self.profile()
        prof_dev = prof.get("device_guid", "")
        shift_tok = prof.get("shift_token", "")
        if self._matches(shift_tok, token, prof_dev):
            return

        active_layer = "shift" if self._shift_held(shift_tok, prof_dev) else "base"
        step = self.cfg["volume_step"] / 100.0

        match = None
        for row in self.binding_rows:
            b = row.binding
            if b.get("layer", "base") == active_layer and \
                    self._matches(b.get("token", ""), token, prof_dev):
                match = row
                break
        if match is None:
            return

        act = match.binding["action"]
        if act in SMOOTH_ACTIONS:
            return
        if act == "next_profile":
            self.cycle_profile()
            self.leds.sweep()
            self._toast("Профиль: " + self.cfg["active_profile"])
            return

        msg = run_action(self.audio, act, match.binding.get("target", ""), step)
        match.flash()
        self.leds.sweep()
        self._toast(msg)

    def on_release(self, token):
        self.held.discard(token)

    def _on_axis(self, guid, idx, value):
        self.axis_values[(guid, idx)] = value

    def _smooth_tick(self):
        if not self.audio.ok:
            return
        prof = self.profile()
        prof_dev = prof.get("device_guid", "")
        shift_tok = prof.get("shift_token", "")
        active_layer = "shift" if self._shift_held(shift_tok, prof_dev) else "base"
        DZ, RATE, dt = 0.15, 0.9, 0.05
        moved_msg = None
        for row in self.binding_rows:
            b = row.binding
            if b.get("action") not in SMOOTH_ACTIONS:
                continue
            if b.get("layer", "base") != active_layer:
                continue
            tok = b.get("token", "")
            if "|" not in tok:
                continue
            dev, inp = tok.split("|", 1)
            if not inp.startswith("axis:"):
                continue
            try:
                _, sidx, sign = inp.split(":")
                idx = int(sidx)
            except Exception:
                continue
            s = self.axis_values.get((dev, idx), 0.0) * (1.0 if sign == "+" else -1.0)
            a = abs(s)
            if a <= DZ:
                continue
            mag = (a - DZ) / (1 - DZ)
            delta = (1 if s > 0 else -1) * mag * RATE * dt
            if b["action"] == "master_vol_smooth":
                moved_msg = f"Общий звук  {pct(self.audio.bump_master(delta))}"
            else:
                nv = self.audio.bump_app(b.get("target", ""), delta)
                moved_msg = f"{b.get('target','')}  {pct(nv)}" if nv is not None else None
        if moved_msg:
            now = int(time.monotonic() * 1000)
            if now - self._last_toast_ms >= 120:
                self._last_toast_ms = now
                self._toast(moved_msg)

    # ── плашка на экране ──
    def _toast(self, msg):
        if not msg:
            return
        if self.cfg.get("toast_enabled", True):
            self.toast.show_toast(msg)
        # если открыт микшер — обновляем его сразу, не дожидаясь тикера
        if self.stack.currentIndex() == 1:
            self.refresh_mixer()

    # ── страница «Микшер» ──
    def _build_mixer_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("МИКШЕР")
        t.setObjectName("h1")
        head.addWidget(t)
        head.addStretch(1)
        live = QLabel("● live")
        live.setObjectName("live")
        head.addWidget(live)
        lay.addLayout(head)

        hint = QLabel("Приложения, которые сейчас проигрывают звук. Обновляется автоматически.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scroll")
        holder = QWidget()
        self.mixer_lay = QVBoxLayout(holder)
        self.mixer_lay.setContentsMargins(0, 0, 8, 0)
        self.mixer_lay.setSpacing(8)
        self.mixer_lay.addStretch(1)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

        self.mixer_empty = QLabel("")
        self.mixer_empty.setObjectName("hint")
        self.mixer_empty.setWordWrap(True)
        self.mixer_lay.insertWidget(0, self.mixer_empty)
        self.mixer_rows = {}

        self.mixer_timer = QTimer(self)
        self.mixer_timer.setInterval(1000)
        self.mixer_timer.timeout.connect(self.refresh_mixer)

        self.stack.addWidget(page)
        self.stack.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, i):
        if i == 1:
            self.refresh_mixer()
            self.mixer_timer.start()
        else:
            self.mixer_timer.stop()

    def refresh_mixer(self):
        if not self.audio.ok:
            self.mixer_empty.setText("Управление звуком доступно только на Windows.")
            self.mixer_empty.setVisible(True)
            return

        sessions = dict(self.audio.list_sessions())
        for name in list(self.mixer_rows):
            if name not in sessions:
                row = self.mixer_rows.pop(name)
                row.setParent(None); row.deleteLater()
        for name, vol in sessions.items():
            row = self.mixer_rows.get(name)
            if row is None:
                row = MixerRow(name, vol, self.audio)
                self.mixer_lay.insertWidget(self.mixer_lay.count() - 1, row)
                self.mixer_rows[name] = row
            else:
                row.set_volume_external(vol)

        self.mixer_empty.setVisible(not sessions)
        if not sessions:
            self.mixer_empty.setText("Сейчас ничего не играет — включи музыку или игру.")

    # ── страница «Настройки» ──
    def _build_settings_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scroll")
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(14)

        lay.addWidget(self._h1("НАСТРОЙКИ"))

        c = self._card()
        c.addWidget(self._field("Громкость"))
        r = QHBoxLayout()
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 25)
        self.step_spin.setSuffix(" %")
        self.step_spin.setValue(self.cfg["volume_step"])
        self.step_spin.setFixedWidth(96)
        self.step_spin.valueChanged.connect(lambda v: self._save("volume_step", v))
        r.addWidget(self.step_spin)
        r.addWidget(QLabel("на одно нажатие"))
        r.addStretch(1)
        c.addLayout(r)
        lay.addWidget(c.frame)

        c = self._card()
        c.addWidget(self._field("Акцентный цвет"))
        sw = QHBoxLayout(); sw.setSpacing(10)
        self.accent_group = QButtonGroup(self)
        for key, (hex_, _, _) in ACCENTS.items():
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(34, 34)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton{{border-radius:17px;background:{hex_};border:2px solid {LINE};}}"
                f"QToolButton:checked{{border:2px solid {TEXT};}}")
            b.setChecked(key == self.cfg["accent"])
            b.clicked.connect(lambda _=False, k=key: self._on_accent(k))
            self.accent_group.addButton(b)
            sw.addWidget(b)
        sw.addStretch(1)
        c.addLayout(sw)
        lay.addWidget(c.frame)

        c = self._card()
        c.addWidget(self._field("Плашка на экране"))
        row, self.toast_switch = self._toggle_row(
            "Показывать при командах", self.cfg["toast_enabled"], self._on_toast_enabled)
        c.addLayout(row)
        sr = QHBoxLayout()
        sr.addWidget(QLabel("Размер"))
        self.toast_scale = QSlider(Qt.Horizontal)
        self.toast_scale.setRange(50, 200)
        self.toast_scale.setValue(self.cfg["toast_scale"])
        self.toast_scale.setFixedWidth(200)
        self.toast_scale_lbl = QLabel(f"{self.cfg['toast_scale']}%")
        self.toast_scale_lbl.setObjectName("mixPct")
        self.toast_scale_lbl.setFixedWidth(52)
        self.toast_scale.valueChanged.connect(self._on_toast_scale)
        sr.addWidget(self.toast_scale)
        sr.addWidget(self.toast_scale_lbl)
        sr.addStretch(1)
        c.addLayout(sr)

        dr = QHBoxLayout()
        dr.addWidget(QLabel("Длительность"))
        self.toast_duration = QSlider(Qt.Horizontal)
        self.toast_duration.setRange(600, 4000)
        self.toast_duration.setSingleStep(100)
        self.toast_duration.setValue(self.cfg["toast_duration"])
        self.toast_duration.setFixedWidth(200)
        self.toast_duration_lbl = QLabel(f"{self.cfg['toast_duration']/1000:.1f} с")
        self.toast_duration_lbl.setObjectName("mixPct")
        self.toast_duration_lbl.setFixedWidth(52)
        self.toast_duration.valueChanged.connect(self._on_toast_duration)
        dr.addWidget(self.toast_duration)
        dr.addWidget(self.toast_duration_lbl)
        dr.addStretch(1)
        c.addLayout(dr)

        cr = QHBoxLayout()
        cr.addWidget(QLabel("Цвет"))
        self.toast_color_group = QButtonGroup(self)
        auto_btn = QToolButton()
        auto_btn.setCheckable(True)
        auto_btn.setFixedSize(34, 34)
        auto_btn.setCursor(Qt.PointingHandCursor)
        auto_btn.setToolTip("Как акцент приложения")
        auto_btn.setText("A")
        auto_btn.setStyleSheet(
            f"QToolButton{{border-radius:17px;background:{SURFACE3};border:2px solid {LINE};color:{MUTED};font-weight:700;}}"
            f"QToolButton:checked{{border:2px solid {TEXT};color:{TEXT};}}")
        auto_btn.setChecked(not self.cfg["toast_color"])
        auto_btn.clicked.connect(lambda: self._on_toast_color(""))
        self.toast_color_group.addButton(auto_btn)
        cr.addWidget(auto_btn)
        for key, (hex_, _, _) in ACCENTS.items():
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(34, 34)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton{{border-radius:17px;background:{hex_};border:2px solid {LINE};}}"
                f"QToolButton:checked{{border:2px solid {TEXT};}}")
            b.setChecked(self.cfg["toast_color"] == hex_)
            b.clicked.connect(lambda _=False, h=hex_: self._on_toast_color(h))
            self.toast_color_group.addButton(b)
            cr.addWidget(b)
        cr.addStretch(1)
        c.addLayout(cr)

        pr = QHBoxLayout()
        pr.addWidget(QLabel("Позиция"))
        self.toast_pos = Dropdown()
        self.toast_pos.setMinimumWidth(180)
        for label, key in POSITIONS:
            self.toast_pos.addItem(label, key)
        self.toast_pos.setCurrentIndex(max(0, self.toast_pos.findData(self.cfg["toast_pos"])))
        self.toast_pos.currentIndexChanged.connect(self._on_toast_pos)
        pr.addWidget(self.toast_pos)
        test = QPushButton("Тест")
        test.setObjectName("ghost")
        test.setCursor(Qt.PointingHandCursor)
        test.clicked.connect(lambda: self._toast("Cockpit Commander  100%"))
        pr.addWidget(test)
        pr.addStretch(1)
        c.addLayout(pr)
        note = QLabel("Плашка видна поверх игр в оконном и безрамочном режиме; "
                      "в эксклюзивном полноэкранном режиме Windows поверх неё ничего не рисует.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        c.addWidget(note)
        lay.addWidget(c.frame)

        c = self._card()
        c.addWidget(self._field("Устройства ввода"))
        dnote = QLabel("Рули и педали по умолчанию выключены, чтобы не отбирать "
                       "Force Feedback у игры. Включай только то, чем хочешь управлять.")
        dnote.setObjectName("hint")
        dnote.setWordWrap(True)
        c.addWidget(dnote)
        self.dev_list_lay = QVBoxLayout()
        self.dev_list_lay.setSpacing(8)
        self.dev_empty = QLabel("Устройства не обнаружены. Подключи геймпад.")
        self.dev_empty.setObjectName("hint")
        self.dev_list_lay.addWidget(self.dev_empty)
        c.addLayout(self.dev_list_lay)
        lay.addWidget(c.frame)

        c = self._card()
        c.addWidget(self._field("Система"))
        row, self.tray_switch = self._toggle_row(
            "Сворачивать в трей (не закрывать)", self.cfg["minimize_to_tray"],
            lambda on: self._save("minimize_to_tray", on))
        c.addLayout(row)
        row, self.autostart_switch = self._toggle_row(
            "Запускать при старте Windows", self.cfg["autostart"], self._on_autostart_toggle)
        c.addLayout(row)
        lay.addWidget(c.frame)

        about = QLabel("COCKPIT COMMANDER — управление звуком и медиа с геймпада. "
                       "Настройки сохраняются автоматически.")
        about.setObjectName("about")
        about.setWordWrap(True)
        lay.addWidget(about)
        lay.addStretch(1)

        scroll.setWidget(holder)
        outer.addWidget(scroll)
        self.stack.addWidget(page)

    def _h1(self, text):
        l = QLabel(text); l.setObjectName("h1"); return l

    def _field(self, text):
        l = QLabel(text); l.setObjectName("field"); return l

    def _card(self):
        frame = QFrame(); frame.setObjectName("card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        v.frame = frame
        return v

    def _toggle_row(self, label, checked, slot):
        row = QHBoxLayout()
        lbl = QLabel(label); lbl.setObjectName("about")
        row.addWidget(lbl); row.addStretch(1)
        sw = ToggleSwitch()
        sw.setChecked(checked)
        sw.toggled.connect(slot)
        row.addWidget(sw)
        return row, sw

    def _save(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)

    def _on_accent(self, key):
        self.cfg["accent"] = key
        self.apply_theme()
        save_config(self.cfg)

    def _sync_toast(self):
        self.toast.configure(self.cfg.get("toast_enabled", True),
                             self.cfg.get("toast_scale", 100) / 100.0,
                             self.cfg.get("toast_pos", "top-center"),
                             self.cfg.get("toast_duration", 1400),
                             self.cfg.get("toast_color", ""))

    def _on_toast_enabled(self, on):
        self.cfg["toast_enabled"] = on
        self._sync_toast()
        save_config(self.cfg)

    def _on_toast_scale(self, v):
        self.toast_scale_lbl.setText(f"{v}%")
        self.cfg["toast_scale"] = v
        self._sync_toast()
        save_config(self.cfg)

    def _on_toast_pos(self, _):
        self.cfg["toast_pos"] = self.toast_pos.currentData()
        self._sync_toast()
        save_config(self.cfg)
        self.toast.show_toast("Позиция плашки")

    def _on_toast_duration(self, v):
        self.toast_duration_lbl.setText(f"{v/1000:.1f} с")
        self.cfg["toast_duration"] = v
        self._sync_toast()
        save_config(self.cfg)

    def _on_toast_color(self, hex_):
        self.cfg["toast_color"] = hex_
        self._sync_toast()
        save_config(self.cfg)
        self.toast.show_toast("Cockpit Commander  100%")

    # ── устройства ──
    def _on_new_device(self, guid, name, disabled):
        self.device_names[guid] = name
        kd = self.cfg.setdefault("known_devices", [])
        if guid not in kd:
            kd.append(guid)
        dd = self.cfg.setdefault("disabled_devices", [])
        if disabled and guid not in dd:
            dd.append(guid)
        save_config(self.cfg)

        if guid in self.device_rows:
            _, sw = self.device_rows[guid]
            sw.blockSignals(True); sw.setChecked(not disabled); sw.blockSignals(False)
        else:
            self.dev_empty.setVisible(False)
            row = QHBoxLayout()
            lbl = QLabel(name)
            lbl.setObjectName("about")
            row.addWidget(lbl); row.addStretch(1)
            sw = ToggleSwitch()
            sw.setChecked(not disabled)
            sw.toggled.connect(lambda on, g=guid: self._toggle_device(g, on))
            row.addWidget(sw)
            wrap = QWidget(); wrap.setLayout(row)
            self.dev_list_lay.addWidget(wrap)
            self.device_rows[guid] = (wrap, sw)

        # профиль, привязанный к этому устройству, активируется сам
        if not disabled:
            for pname, prof in self.cfg["profiles"].items():
                if prof.get("device_guid") == guid and pname != self.cfg["active_profile"]:
                    self._activate_profile(pname)
                    self._toast("Профиль: " + pname)
                    break

    def _toggle_device(self, guid, enabled):
        dd = self.cfg.setdefault("disabled_devices", [])
        if enabled and guid in dd:
            dd.remove(guid)
        elif not enabled and guid not in dd:
            dd.append(guid)
        save_config(self.cfg)
        self.thread.disabled = set(dd)
        self.thread.rescan = True

    # ── трей / автозапуск ──
    def _app_icon(self):
        if os.path.exists(ICON_FILE):
            return QIcon(ICON_FILE)
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(CURRENT_ACCENT))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(6, 6, 52, 52), 14, 14)
        p.setPen(QColor(BG))
        f = p.font(); f.setBold(True); f.setPixelSize(34)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, "»")
        p.end()
        return QIcon(pm)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self._app_icon(), self)
        self.tray.setToolTip("Cockpit Commander")
        menu = QMenu()
        menu.addAction("Показать").triggered.connect(self._restore)
        menu.addSeparator()
        menu.addAction("Выход").triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._restore() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def _restore(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def _quit_app(self):
        self._quitting = True
        self.close()

    def _on_autostart_toggle(self, on):
        self.cfg["autostart"] = on
        self._apply_autostart(on)
        save_config(self.cfg)

    def _apply_autostart(self, enabled):
        if sys.platform != "win32":
            return
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            name = "CockpitCommander"
            if enabled:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}"'
                else:
                    py = sys.executable
                    pyw = py[:-10] + "pythonw.exe" if py.lower().endswith("python.exe") else py
                    if not os.path.exists(pyw):
                        pyw = py
                    cmd = f'"{pyw}" "{os.path.abspath(__file__)}"'
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print("Автозапуск:", e)

    # ── тема ──
    def apply_theme(self):
        global CURRENT_ACCENT
        accent, accent_hover, accent_soft = ACCENTS[self.cfg["accent"]]
        CURRENT_ACCENT = accent
        repl = {
            "@BG@": BG, "@SURFACE@": SURFACE, "@SURFACE2@": SURFACE2,
            "@SURFACE3@": SURFACE3, "@LINE@": LINE, "@TEXT@": TEXT,
            "@MUTED@": MUTED, "@CYAN@": CYAN, "@ACCENT@": accent,
            "@ACCENT_HOVER@": accent_hover, "@ACCENT_SOFT@": accent_soft,
        }
        qss = QSS_TEMPLATE
        for k, v in repl.items():
            qss = qss.replace(k, v)
        self.setStyleSheet(qss)
        self.title_bar.set_accent(accent)
        if self.tray:
            self.tray.setIcon(self._app_icon())

    # ── события окна ──
    def _edge_at(self, pos):
        m = RESIZE_MARGIN + 2
        r = self.rect()
        e = Qt.Edges()
        if pos.x() <= m:
            e |= Qt.LeftEdge
        if pos.x() >= r.width() - m:
            e |= Qt.RightEdge
        if pos.y() <= m:
            e |= Qt.TopEdge
        if pos.y() >= r.height() - m:
            e |= Qt.BottomEdge
        return e

    def mouseMoveEvent(self, e):
        if self.isMaximized():
            self.unsetCursor()
            return
        edge = self._edge_at(e.position().toPoint())
        if edge in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edge & (Qt.LeftEdge | Qt.RightEdge):
            self.setCursor(Qt.SizeHorCursor)
        elif edge & (Qt.TopEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.isMaximized():
            edge = self._edge_at(e.position().toPoint())
            if edge and self.windowHandle():
                self.windowHandle().startSystemResize(edge)
                return
        super().mousePressEvent(e)

    def changeEvent(self, e):
        if (e.type() == QEvent.Type.WindowStateChange and self.cfg.get("minimize_to_tray")
                and self.tray and self.isMinimized()):
            QTimer.singleShot(0, self.hide)
        super().changeEvent(e)

    def closeEvent(self, e):
        if self.cfg.get("minimize_to_tray") and self.tray and not self._quitting:
            e.ignore()
            self.hide()
            return
        try:
            self.thread.stop(); self.thread.wait(1500)
        except Exception:
            pass
        for t in (self.smooth_timer, self.mixer_timer):
            try:
                t.stop()
            except Exception:
                pass
        if self.tray:
            self.tray.hide()
        e.accept()

    def persist(self):
        self.profile()["bindings"] = [r.binding for r in self.binding_rows]
        save_config(self.cfg)


# ─────────────────────────────────────────────────────────────────────────────
#  Стиль
# ─────────────────────────────────────────────────────────────────────────────
QSS_TEMPLATE = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; color: @TEXT@; }

#win { background: @BG@; border: 1px solid @LINE@; }
#winTitle { font-size: 14px; font-weight: 800; letter-spacing: 3px; }
#winBtn, #winClose {
    background: transparent; border: none; color: @MUTED@;
    font-size: 15px; width: 32px; height: 32px; border-radius: 7px;
}
#winBtn:hover { background: @SURFACE2@; color: @TEXT@; }
#winClose:hover { background: #E5484D; color: white; }

#ledWrap { background: @BG@; border-bottom: 1px solid @LINE@; }

#sidebar { background: @SURFACE@; border-right: 1px solid @LINE@; }
QPushButton#nav {
    text-align: left; padding: 11px 14px; border: none;
    border-left: 3px solid transparent; border-radius: 8px;
    background: transparent; color: @MUTED@; font-size: 13px; font-weight: 600;
}
QPushButton#nav:hover { background: @SURFACE2@; color: @TEXT@; }
QPushButton#nav:checked {
    background: @ACCENT_SOFT@; color: @ACCENT@;
    border-left: 3px solid @ACCENT@;
}
#ver { color: #4A5563; font-family: 'Consolas', monospace; font-size: 11px; padding-left: 6px; }

#content { background: @BG@; }

#h1 { font-size: 13px; font-weight: 800; letter-spacing: 3px; color: @TEXT@; }
#hint { color: @MUTED@; font-size: 12px; }
#live { color: @CYAN@; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
#warn { color: #FFB020; font-size: 12px; background: rgba(255,176,32,0.10);
        border: 1px solid rgba(255,176,32,0.30); border-radius: 8px; padding: 10px 12px; }
#field { color: @MUTED@; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
#about { color: @MUTED@; font-size: 12px; }

QScrollArea#scroll { border: none; background: transparent; }
QScrollArea#scroll > QWidget > QWidget { background: transparent; }

#card { background: @SURFACE@; border: 1px solid @LINE@; border-radius: 12px; }
#card:hover { border-color: #343F4E; }
#card[listening="1"] { border: 1px solid @ACCENT@; }
#card[fired="1"] { border: 1px solid @CYAN@; background: @SURFACE2@; }

#badge {
    background: @SURFACE3@; border: 1px solid @LINE@; border-radius: 6px;
    padding: 6px 4px; font-family: 'Consolas', monospace; font-size: 11px;
    font-weight: 700; letter-spacing: 1px; color: @TEXT@;
}
#badge[listening="1"] { border: 1px solid @ACCENT@; color: @ACCENT@; }
#devtag { color: @MUTED@; font-size: 10px; font-weight: 600; }

QPushButton#bindBtn {
    background: transparent; border: 1px solid @LINE@; border-radius: 7px;
    padding: 7px 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: @MUTED@;
}
QPushButton#bindBtn:hover { border-color: @ACCENT@; color: @ACCENT@; }

QToolButton#delBtn {
    background: transparent; border: none; color: @MUTED@;
    font-size: 14px; width: 28px; height: 28px; border-radius: 6px;
}
QToolButton#delBtn:hover { background: rgba(255,59,71,0.15); color: #FF3B47; }

QPushButton#primary {
    background: @ACCENT@; color: @BG@; border: none; border-radius: 8px;
    padding: 9px 18px; font-size: 12px; font-weight: 800; letter-spacing: 1px;
}
QPushButton#primary:hover { background: @ACCENT_HOVER@; }

QPushButton#ghost {
    background: @SURFACE2@; border: 1px solid @LINE@; border-radius: 7px;
    padding: 7px 12px; font-size: 12px; color: @TEXT@;
}
QPushButton#ghost:hover { border-color: @ACCENT@; color: @ACCENT@; }

QPushButton#seg {
    background: @SURFACE2@; border: 1px solid @LINE@; border-radius: 7px;
    padding: 7px 14px; font-size: 12px; font-weight: 600; color: @MUTED@;
}
QPushButton#seg:hover { color: @TEXT@; }
QPushButton#seg:checked { background: @ACCENT_SOFT@; border-color: @ACCENT@; color: @ACCENT@; }

QComboBox, QSpinBox {
    background: @SURFACE2@; border: 1px solid @LINE@; border-radius: 7px;
    padding: 7px 10px; font-size: 12px; color: @TEXT@;
}
QComboBox:hover, QSpinBox:hover { border-color: #384352; }
QComboBox:focus, QSpinBox:focus { border-color: @ACCENT@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid @MUTED@; margin-right: 8px; }
QComboBox QAbstractItemView {
    background: @SURFACE2@; border: 1px solid @LINE@; border-radius: 8px;
    selection-background-color: @ACCENT_SOFT@; selection-color: @ACCENT@;
    outline: none; padding: 4px;
}
QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 10px; border-radius: 6px; }

QSpinBox { padding-right: 24px; }
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border; width: 20px; background: @SURFACE3@; border: none;
    border-left: 1px solid @LINE@;
}
QSpinBox::up-button { subcontrol-position: top right; height: 50%; border-top-right-radius: 6px; }
QSpinBox::down-button { subcontrol-position: bottom right; height: 50%;
    border-bottom-right-radius: 6px; border-top: 1px solid @LINE@; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: @LINE@; }
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed { background: @ACCENT@; }
QSpinBox::up-arrow { image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid @MUTED@; }
QSpinBox::down-arrow { image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid @MUTED@; }

#mixName { font-size: 13px; font-weight: 600; }
#mixPct { font-family: 'Consolas', monospace; font-size: 12px; color: @CYAN@; font-weight: 700; }

QSlider::groove:horizontal { height: 6px; background: @SURFACE3@; border-radius: 3px; }
QSlider::sub-page:horizontal { background: @ACCENT@; border-radius: 3px; }
QSlider#mixSlider::sub-page:horizontal { background: @CYAN@; border-radius: 3px; }
QSlider::handle:horizontal {
    background: @TEXT@; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}
QSlider::handle:horizontal:hover { background: @ACCENT@; }
QSlider#mixSlider::handle:horizontal:hover { background: @CYAN@; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @SURFACE3@; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3A4656; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Cockpit Commander")
    if os.path.exists(ICON_FILE):
        app.setWindowIcon(QIcon(ICON_FILE))
    w = MainWindow()
    w.show()
    if w.cfg.get("autostart"):
        w._apply_autostart(True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()