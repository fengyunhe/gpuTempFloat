# -*- coding: utf-8 -*-
"""
GpuTempFloat —— 桌面悬浮显卡温度监测小窗

设计参考 VocabFloat 的悬浮卡片实现：
  - Qt.FramelessWindowHint + WA_TranslucentBackground 做无边框圆角透明卡片
  - WindowStaysOnTopHint 置顶
  - ctypes 设置 WS_EX_TOOLWINDOW（不进任务栏、不参与 Aero Snap）
  - ctypes 设置 WS_EX_NOACTIVATE（点击悬浮窗不会把焦点从游戏抢走）
  - 额外提供 WS_EX_TRANSPARENT 点击穿透模式，方便游戏内不挡操作

温度数据来源：
  1) AMD ADL2 PMLog（atiadlxx.dll）—— RX 6000/7000 系列可用，免管理员权限
  2) 老卡回退 ADL2 Overdrive5 温度
  3) NVIDIA 回退 nvidia-smi
"""

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time

from PySide6.QtCore import Qt, QPoint, QTimer, QRectF, Signal, QObject
from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen, QAction,
                           QGuiApplication, QCursor, QIcon, QPixmap)
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QMenu, QFrame, QSystemTrayIcon)

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
APP_NAME = "GpuTempFloat"
CONFIG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "x": None,
    "y": None,
    "opacity": 0.88,
    "no_bg": False,        # 无背景模式：只留文字（带描边），适合叠在游戏画面上
    "size_mode": "compact",  # mini / compact / normal
    "lang": "zh",          # zh = 中文界面，en = English UI
    "interval": 1000,      # 毫秒
    "click_through": False,
    "always_on_top": True,
    "show_detail": True,   # 显示热点/显存/功耗/频率
}

# 中英双语文案（code 里只写 key，界面按 config["lang"] 取）
I18N = {
    "zh": {
        "app_tip": "GPU 温度悬浮窗",
        "reading": "核心温度 · 读取中",
        "adl_no_gpu": "未找到 AMD 显卡",
        "lang_name": "语言",
        "lang_zh": "中文",
        "lang_en": "English",
        "menu_click_through": "点击穿透（Ctrl+Alt+G）",
        "menu_top": "始终置顶",
        "menu_bg": "背景与透明度",
        "menu_no_bg": "无背景模式（仅文字）",
        "menu_opacity": "调节透明度（滑块）…  当前 {p}%",
        "menu_size": "尺寸",
        "size_mini": "迷你（单行 {w}×{h}）",
        "size_compact": "紧凑（{w}×{h}）",
        "size_normal": "标准（{w}×{h}）",
        "menu_interval": "刷新间隔",
        "sec": "{v} 秒",
        "menu_quit": "退出（Ctrl+Alt+Q）",
        "flash_no_bg_on": "无背景模式（仅文字）",
        "flash_no_bg_off": "已恢复背景",
        "flash_mini": "迷你单行",
        "flash_compact": "紧凑尺寸",
        "flash_normal": "标准尺寸",
        "flash_switched": "已切换",
        "opacity_title": "背景不透明度",
        "opacity_tip": "拖动即时生效，松开即保存",
        "fan": "风扇 ",
        "hotspot": "热点 ",
        "hotspot_short": "热点 ",
        "mem": "显存 ",
        "mem_short": "显存 ",
        "load": "负载 ",
        "pass_on": "穿透中 · Ctrl+Alt+G 解除",
        "pass_off": "已退出穿透",
        "pass_suffix": " · 穿透中",
        "read_fail": "读取失败：{e}",
        "read_error": "读取异常：{e}",
        "tray_show": "隐藏悬浮窗",
        "tray_hide": "显示悬浮窗",
        "tray_ct_on": "解除鼠标穿透",
        "tray_ct_off": "开启鼠标穿透",
        "tray_top": "始终置顶",
        "tray_quit": "退出",
        "tray_live": "GPU {t}°C{s}\nCtrl+Alt+G 穿透 / Ctrl+Alt+H 显隐 / 右键托盘退出",
    },
    "en": {
        "app_tip": "GPU temperature overlay",
        "reading": "Core temp · reading…",
        "adl_no_gpu": "No AMD GPU found",
        "lang_name": "Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "menu_click_through": "Click-through (Ctrl+Alt+G)",
        "menu_top": "Always on top",
        "menu_bg": "Background && opacity",   # QAction 里 "&&" 才显示为 &，单个 & 会被当成助记符
        "menu_no_bg": "Text only (no background)",
        "menu_opacity": "Opacity slider…  now {p}%",
        "menu_size": "Size",
        "size_mini": "Mini (single line {w}×{h})",
        "size_compact": "Compact ({w}×{h})",
        "size_normal": "Standard ({w}×{h})",
        "menu_interval": "Refresh interval",
        "sec": "{v} s",
        "menu_quit": "Quit (Ctrl+Alt+Q)",
        "flash_no_bg_on": "Text-only mode",
        "flash_no_bg_off": "Background restored",
        "flash_mini": "Mini single line",
        "flash_compact": "Compact size",
        "flash_normal": "Standard size",
        "flash_switched": "Size changed",
        "opacity_title": "Background opacity",
        "opacity_tip": "Live preview · saved on release",
        "fan": "Fan ",
        "hotspot": "Hotspot ",
        "hotspot_short": "Hot ",
        "mem": "VRAM ",
        "mem_short": "VRAM ",
        "load": "Load ",
        "pass_on": "Ctrl+Alt+G to release",
        "pass_off": "Click-through off",
        "pass_suffix": " · click-through",
        "read_fail": "Read failed: {e}",
        "read_error": "Read error: {e}",
        "tray_show": "Hide overlay",
        "tray_hide": "Show overlay",
        "tray_ct_on": "Disable click-through",
        "tray_ct_off": "Enable click-through",
        "tray_top": "Always on top",
        "tray_quit": "Quit",
        "tray_live": "GPU {t}°C{s}\nCtrl+Alt+G click-through / Ctrl+Alt+H hide / right-click tray to quit",
    },
}


def tr(cfg, key, **kw):
    """按当前语言取文案，缺 key 时回落到中文，再回落到 key 本身"""
    lang = (cfg or {}).get("lang", "zh")
    table = I18N.get(lang) or I18N["zh"]
    text = table.get(key)
    if text is None:
        text = I18N["zh"].get(key, key)
    if kw:
        try:
            text = text.format(**kw)
        except Exception:
            pass
    return text

# 三种尺寸的参数：mini 单行 / compact 小卡片 / normal 标准卡片
SIZE_MODES = {
    "mini": {
        "size": (172, 34),
        "margins": (7, 0, 8, 0),
        "spacing": 0,
        "temp_pt": 15,
        "deg_px": 8,
        "fan_px": 9,
        "detail_px": 9,
        "bar_h": 0,
        "outline_px": 1,
        "radius": 9,
        "fields": ("hotspot", "mem"),
        "short_fan": True,
        "single_row": True,
    },
    "compact": {
        "size": (168, 58),
        "margins": (7, 5, 7, 4),
        "spacing": 1,
        "temp_pt": 19,
        "deg_px": 9,
        "fan_px": 9,
        "detail_px": 10,
        "bar_h": 2,
        "outline_px": 1,
        "radius": 9,
        "fields": ("hotspot", "mem", "power"),
        "short_fan": True,
        "single_row": False,
    },
    "normal": {
        "size": (212, 100),
        "margins": (12, 9, 12, 9),
        "spacing": 2,
        "temp_pt": 26,
        "deg_px": 12,
        "fan_px": 12,
        "detail_px": 10,
        "bar_h": 3,
        "outline_px": 2,
        "radius": 12,
        "fields": ("hotspot", "mem", "power", "load"),
        "short_fan": False,
        "single_row": False,
    },
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# AMD ADL 读取
# --------------------------------------------------------------------------- #
ADL_MAX_PMLOG_SENSORS = 256

ADL_PMLOG_CLK_GFXCLK = 1
ADL_PMLOG_CLK_MEMCLK = 2
ADL_PMLOG_TEMPERATURE_EDGE = 8
ADL_PMLOG_TEMPERATURE_MEM = 9
ADL_PMLOG_FAN_RPM = 14
ADL_PMLOG_FAN_PERCENTAGE = 15
ADL_PMLOG_INFO_ACTIVITY_GFX = 19
ADL_PMLOG_ASIC_POWER = 23
ADL_PMLOG_TEMPERATURE_HOTSPOT = 27
ADL_PMLOG_BOARD_POWER = 73


class ADLSingleSensorData(ctypes.Structure):
    _fields_ = [("supported", ctypes.c_int), ("value", ctypes.c_int)]


class ADLPMLogDataOutput(ctypes.Structure):
    _fields_ = [("size", ctypes.c_int),
                ("sensors", ADLSingleSensorData * ADL_MAX_PMLOG_SENSORS)]


class ADLAdapterInfo(ctypes.Structure):
    _fields_ = [("iSize", ctypes.c_int),
                ("iAdapterIndex", ctypes.c_int),
                ("strUDID", ctypes.c_char * 256),
                ("iBusNumber", ctypes.c_int),
                ("iDeviceNumber", ctypes.c_int),
                ("iFunctionNumber", ctypes.c_int),
                ("iVendorID", ctypes.c_int),
                ("strAdapterName", ctypes.c_char * 256),
                ("strDisplayName", ctypes.c_char * 256),
                ("iPresent", ctypes.c_int),
                ("iExist", ctypes.c_int),
                ("strDriverPath", ctypes.c_char * 256),
                ("strDriverPathExt", ctypes.c_char * 256),
                ("strPNPString", ctypes.c_char * 256),
                ("iOSDisplayIndex", ctypes.c_int)]


class ADLTemperature(ctypes.Structure):
    _fields_ = [("iSize", ctypes.c_int), ("iTemperature", ctypes.c_int)]


ALLOC_CB = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_int)


def _adl_alloc(size):
    return ctypes.cast(ctypes.create_string_buffer(size), ctypes.c_void_p)


class AdlReader:
    """AMD ADL2 PMLog 传感器读取器"""

    name = "AMD ADL PMLog"

    def __init__(self):
        self.dll = ctypes.CDLL("atiadlxx.dll")
        self.ctx = ctypes.c_void_p()
        self._keep = ALLOC_CB(_adl_alloc)  # 保持回调引用，防止被 GC

        self.dll.ADL2_Main_Control_Create.argtypes = [
            ALLOC_CB, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.ADL2_Main_Control_Create.restype = ctypes.c_int
        rc = self.dll.ADL2_Main_Control_Create(self._keep, 1, ctypes.byref(self.ctx))
        if rc != 0:
            raise RuntimeError(f"ADL2_Main_Control_Create failed: {rc}")

        self.adapter_index = self._find_adapter()
        self.model = self.adapter_name

        self._pmlog = getattr(self.dll, "ADL2_New_QueryPMLogData_Get", None)
        if self._pmlog is not None:
            self._pmlog.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                    ctypes.POINTER(ADLPMLogDataOutput)]
            self._pmlog.restype = ctypes.c_int
        self._od5 = getattr(self.dll, "ADL2_Overdrive5_Temperature_Get", None)
        if self._od5 is not None:
            self._od5.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                  ctypes.POINTER(ADLTemperature)]
            self._od5.restype = ctypes.c_int

    def _find_adapter(self):
        num = ctypes.c_int(0)
        self.dll.ADL2_Adapter_NumberOfAdapters_Get.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.dll.ADL2_Adapter_NumberOfAdapters_Get(self.ctx, ctypes.byref(num))
        n = max(0, num.value)
        infos = (ADLAdapterInfo * max(n, 1))()
        self.dll.ADL2_Adapter_AdapterInfo_Get.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ADLAdapterInfo), ctypes.c_int]
        for i in range(n):
            infos[i].iSize = ctypes.sizeof(ADLAdapterInfo)
        self.dll.ADL2_Adapter_AdapterInfo_Get(self.ctx, infos, ctypes.sizeof(infos))

        self.dll.ADL2_Adapter_Active_Get.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]

        candidates = []
        for i in range(n):
            if not infos[i].iPresent:
                continue
            active = ctypes.c_int(0)
            try:
                self.dll.ADL2_Adapter_Active_Get(self.ctx, i, ctypes.byref(active))
            except Exception:
                pass
            name = infos[i].strAdapterName.decode("mbcs", "ignore").strip()
            candidates.append((0 if active.value else 1, int(infos[i].iOSDisplayIndex), i, name))

        candidates.sort()
        if not candidates:
            raise RuntimeError("未找到 AMD 显卡")
        _, _, idx, name = candidates[0]
        self.adapter_name = name or "AMD Radeon"
        return idx

    # ---- 单值读取 ----
    def _read_pmlog(self):
        data = ADLPMLogDataOutput()
        data.size = ctypes.sizeof(ADLPMLogDataOutput)
        rc = self._pmlog(self.ctx, self.adapter_index, ctypes.byref(data))
        if rc != 0:
            return None
        return data.sensors

    def read(self):
        out = {"edge": None, "hotspot": None, "mem": None, "fan_pct": None,
               "fan_rpm": None, "power": None, "load": None, "gfx_clk": None,
               "mem_clk": None}

        sensors = None
        if self._pmlog is not None:
            sensors = self._read_pmlog()

        if sensors is not None:
            def val(i):
                s = sensors[i]
                return int(s.value) if s.supported else None

            out["edge"] = val(ADL_PMLOG_TEMPERATURE_EDGE)
            out["hotspot"] = val(ADL_PMLOG_TEMPERATURE_HOTSPOT)
            out["mem"] = val(ADL_PMLOG_TEMPERATURE_MEM)
            out["fan_pct"] = val(ADL_PMLOG_FAN_PERCENTAGE)
            out["fan_rpm"] = val(ADL_PMLOG_FAN_RPM)
            out["load"] = val(ADL_PMLOG_INFO_ACTIVITY_GFX)
            out["gfx_clk"] = val(ADL_PMLOG_CLK_GFXCLK)
            out["mem_clk"] = val(ADL_PMLOG_CLK_MEMCLK)
            power = val(ADL_PMLOG_BOARD_POWER)
            if power is None:
                power = val(ADL_PMLOG_ASIC_POWER)
            out["power"] = power

        # 边缘温度缺失时回退 Overdrive5
        if out["edge"] is None and self._od5 is not None:
            t = ADLTemperature()
            t.iSize = ctypes.sizeof(ADLTemperature)
            rc = self._od5(self.ctx, self.adapter_index, 0, ctypes.byref(t))
            if rc == 0:
                out["edge"] = int(round(t.iTemperature / 1000.0))
        return out

    def close(self):
        try:
            self.dll.ADL2_Main_Control_Destroy.argtypes = [ctypes.c_void_p]
            self.dll.ADL2_Main_Control_Destroy(self.ctx)
        except Exception:
            pass


class NvmlReader:
    """NVIDIA 回退：nvidia-smi"""

    name = "NVIDIA nvidia-smi"

    def __init__(self):
        self.model = "NVIDIA GPU"
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            creationflags=0x08000000, timeout=5).decode("utf-8", "ignore")
        self.model = out.strip().splitlines()[0] if out.strip() else self.model

    def read(self):
        csv = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,fan.speed,power.draw,clocks.gr,clocks.mem,utilization.gpu",
             "--format=csv,noheader,nounits"],
            creationflags=0x08000000, timeout=5).decode("utf-8", "ignore")
        parts = [p.strip() for p in csv.strip().splitlines()[0].split(",")]
        def num(s):
            try:
                return int(float(s))
            except Exception:
                return None
        return {"edge": num(parts[0]), "hotspot": None, "mem": None,
                "fan_pct": num(parts[1]), "fan_rpm": None, "power": num(parts[2]),
                "load": num(parts[5]), "gfx_clk": num(parts[3]),
                "mem_clk": num(parts[4])}

    def close(self):
        pass


def make_reader():
    errors = []
    for cls in (AdlReader, NvmlReader):
        try:
            return cls(), None
        except Exception as e:
            errors.append(f"{cls.name}: {e}")
    return None, " | ".join(errors)


# --------------------------------------------------------------------------- #
# 全局热键（RegisterHotKey + 独立消息循环线程）
# --------------------------------------------------------------------------- #
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312


class HotkeyMSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_size_t),
                ("time", ctypes.c_uint), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]


class HotkeyThread(threading.Thread):
    """在独立线程里注册全局热键并跑消息循环，只投递热键 id"""

    def __init__(self, bindings, out_queue):
        super().__init__(daemon=True)
        self.bindings = bindings          # {id: (mods, vk)}
        self.out_queue = out_queue

    def run(self):
        user32 = ctypes.windll.user32
        ok = []
        for hid, (mods, vk) in self.bindings.items():
            if user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk):
                ok.append(hid)
        msg = HotkeyMSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
                if msg.message == WM_HOTKEY:
                    self.out_queue.put(int(msg.wParam))
        except Exception:
            pass
        finally:
            for hid in ok:
                user32.UnregisterHotKey(None, hid)


# --------------------------------------------------------------------------- #
# Win32 窗口样式工具
# --------------------------------------------------------------------------- #
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020


def apply_win32_styles(hwnd, click_through):
    user32 = ctypes.windll.user32
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    if click_through:
        ex |= WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)


def set_no_activate(hwnd):
    user32 = ctypes.windll.user32
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)


# --------------------------------------------------------------------------- #
# 悬浮卡片
# --------------------------------------------------------------------------- #
def temp_color(t):
    if t is None:
        return "#9aa0a6"
    if t < 65:
        return "#48c78e"
    if t < 80:
        return "#f5a524"
    return "#f0483f"


class RoundedPanel(QWidget):
    """深色圆角弹出面板（用于透明度滑块）"""

    def __init__(self, flags=Qt.WindowType.Popup):
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(27, 28, 32, 244))
        p.setPen(QPen(QColor(74, 78, 88), 1))
        p.drawRoundedRect(rect, 10, 10)


class OutlineLabel(QLabel):
    """无背景模式下用「黑描边 + 实心字」绘制，保证在任意游戏画面上都读得清"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.outline = False
        self.outline_px = 1
        self.text_color = QColor(255, 255, 255, 230)

    def set_text_color(self, color):
        self.text_color = QColor(color)
        self.setStyleSheet(f"color: {color}; background: transparent;")

    def paintEvent(self, e):
        if not self.outline:
            super().paintEvent(e)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setFont(self.font())
        align = self.alignment()
        rect = self.rect()
        txt = self.text()
        p.setPen(QColor(0, 0, 0, 255))
        for dx in range(-self.outline_px, self.outline_px + 1):
            for dy in range(-self.outline_px, self.outline_px + 1):
                if dx or dy:
                    p.drawText(rect.translated(dx, dy), align, txt)
        p.setPen(self.text_color)
        p.drawText(rect, align, txt)


class OverlayCard(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._drag_offset = None
        self._data = {}
        self._reader_name = ""
        self.on_interval_change = None
        self.on_lang_change = None

        self.setWindowTitle("GPU Temp")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlags(self._flags())
        self.setFixedSize(*self._mode()["size"])
        self.setMouseTracking(True)

        self._build_ui()
        self._apply_visual_mode()
        self._restore_pos()

        QTimer.singleShot(0, lambda: apply_win32_styles(int(self.winId()), self.cfg["click_through"]))

    def _mode(self):
        return SIZE_MODES.get(self.cfg.get("size_mode", "compact"), SIZE_MODES["compact"])

    def _flags(self):
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        if self.cfg.get("always_on_top", True):
            f |= Qt.WindowType.WindowStaysOnTopHint
        f |= Qt.WindowType.WindowDoesNotAcceptFocus
        return f

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 4, 7, 3)
        root.setSpacing(1)

        row1 = QHBoxLayout()
        row1.setSpacing(3)
        self.lbl_temp = OutlineLabel("--")
        self.lbl_temp.set_text_color("#9aa0a6")
        self.lbl_deg = OutlineLabel("°C")
        self.lbl_deg.setAlignment(Qt.AlignmentFlag.AlignBottom)
        row1.addWidget(self.lbl_temp)
        row1.addWidget(self.lbl_deg)

        # 迷你模式专用：把热点/显存塞进同一行
        self.lbl_inline = OutlineLabel("")
        self.lbl_inline.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self.lbl_inline)

        row1.addStretch(1)
        self.lbl_fan = OutlineLabel("--%")
        self.lbl_fan.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self.lbl_fan)
        root.addLayout(row1)

        self.lbl_detail = OutlineLabel(tr(self.cfg, "reading"))
        self.lbl_detail.setWordWrap(False)
        root.addWidget(self.lbl_detail)

        self.lbl_bar = QLabel("")
        self.lbl_bar.setFixedHeight(2)
        root.addWidget(self.lbl_bar)

        # 状态气泡（开启/关闭穿透时短暂提示，避免“困在穿透模式”）
        self.hint = QLabel("", self)
        self.hint.setStyleSheet(
            "background: rgba(0,0,0,0.82); color: #ffc857; border-radius: 6px;"
            "padding: 3px 8px; font-size: 11px;")
        self.hint.setVisible(False)
        self.hint_timer = QTimer(self)
        self.hint_timer.setSingleShot(True)
        self.hint_timer.timeout.connect(lambda: self.hint.setVisible(False))

    def _flash(self, text):
        self.hint.setText(text)
        # 卡片窄 / 英文提示较长时自动缩字号，避免被窗口裁掉
        px = 11
        for _ in range(5):
            self.hint.setStyleSheet(
                "background: rgba(0,0,0,0.82); color: #ffc857; border-radius: 6px;"
                f"padding: 2px 7px; font-size: {px}px;")
            self.hint.adjustSize()
            if self.hint.width() <= self.width() - 6:
                break
            px -= 1
        # 卡片很矮时贴底会溢出，改为垂直居中
        if self.height() - self.hint.height() - 6 < 2:
            y = max(0, (self.height() - self.hint.height()) // 2)
        else:
            y = self.height() - self.hint.height() - 4
        self.hint.move(max(2, (self.width() - self.hint.width()) // 2), y)
        self.hint.raise_()
        self.hint.setVisible(True)
        self.hint_timer.start(2600)

    # ---- 绘制圆角半透明背景 ----
    def paintEvent(self, e):
        mode = self._mode()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, mode["radius"], mode["radius"])

        accent = QColor(temp_color(self._data.get("edge")))

        if not self.cfg.get("no_bg"):
            bg = QColor(14, 15, 18)
            bg.setAlphaF(self.cfg.get("opacity", 0.88))
            p.fillPath(path, bg)

            # 左侧温度色标（裁切在圆角内，避免露角）
            accent.setAlpha(230)
            p.setClipPath(path)
            p.fillRect(QRectF(0, 0, 2.2, self.height()), accent)
            p.setClipping(False)

            p.setPen(QPen(QColor(255, 255, 255, 28), 1))
            p.drawPath(path)

        # 右上角橙点：表示当前处于鼠标穿透状态（此时点不到窗口，只能靠热键/托盘解除）
        if self.cfg.get("click_through"):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 200, 87, 235))
            p.drawEllipse(QPoint(self.width() - 8, 8), 2.6, 2.6)

    # ---- 尺寸 / 背景 / 纯文字，统一在这里应用 ----
    def _apply_visual_mode(self):
        mode = self._mode()
        no_bg = self.cfg.get("no_bg", False)
        single = mode.get("single_row", False)

        lay = self.layout()
        lay.setContentsMargins(*mode["margins"])
        lay.setSpacing(mode["spacing"])

        f = QFont("Segoe UI", mode["temp_pt"])
        f.setBold(True)
        self.lbl_temp.setFont(f)
        for lb, px in ((self.lbl_deg, mode["deg_px"]), (self.lbl_fan, mode["fan_px"]),
                       (self.lbl_detail, mode["detail_px"]), (self.lbl_inline, mode["detail_px"])):
            fb = lb.font()
            fb.setPixelSize(px)
            lb.setFont(fb)

        # 文字颜色：无背景时全实色，有背景时略淡
        deg_a = 1.0 if no_bg else 0.62
        fan_a = 1.0 if no_bg else 0.78
        detail_a = 0.94 if no_bg else 0.62
        for lb, a in ((self.lbl_deg, deg_a), (self.lbl_fan, fan_a),
                      (self.lbl_detail, detail_a), (self.lbl_inline, detail_a)):
            lb.setStyleSheet(f"color: rgba(255,255,255,{a}); background: transparent;")

        # 统一使用「黑描边 + 实心字」：背景透明或有背景都清晰
        for lb in (self.lbl_temp, self.lbl_deg, self.lbl_fan, self.lbl_detail, self.lbl_inline):
            lb.outline = True
            lb.outline_px = mode["outline_px"]
            lb.update()
        self.lbl_deg.text_color = QColor(255, 255, 255, 225)
        self.lbl_fan.text_color = QColor(255, 255, 255, 245)
        self.lbl_detail.text_color = QColor(255, 255, 255, 235)
        self.lbl_inline.text_color = QColor(255, 255, 255, 225)

        show_detail = self.cfg.get("show_detail", True)
        self.lbl_deg.setAlignment(Qt.AlignmentFlag.AlignVCenter if single
                                  else Qt.AlignmentFlag.AlignBottom)
        self.lbl_inline.setVisible(single and show_detail)
        self.lbl_detail.setVisible((not single) and show_detail)

        self.lbl_bar.setFixedHeight(max(1, mode["bar_h"]))
        # 迷你模式没有第二行，也没有占用条；无背景模式下也不画
        self.lbl_bar.setVisible(mode["bar_h"] > 0 and not no_bg and show_detail)

        self.setFixedSize(*mode["size"])
        if hasattr(self, "hint") and self.hint.isVisible():
            self._flash(self.hint.text())
        self.update()

    def _toggle_no_bg(self):
        self.cfg["no_bg"] = not self.cfg.get("no_bg", False)
        save_config(self.cfg)
        self._apply_visual_mode()
        self._flash(tr(self.cfg, "flash_no_bg_on") if self.cfg["no_bg"] else tr(self.cfg, "flash_no_bg_off"))

    def _set_size_mode(self, mode_name):
        if mode_name == self.cfg.get("size_mode"):
            return
        self.cfg["size_mode"] = mode_name
        save_config(self.cfg)
        self._apply_visual_mode()
        self.update_data(self._data, self._reader_name)
        # 换尺寸后保持右下角不外溢
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = min(self.x(), screen.right() - self.width())
        y = min(self.y(), screen.bottom() - self.height())
        self.move(max(screen.left(), x), max(screen.top(), y))
        self._save_pos()
        self._flash(tr(self.cfg, {"mini": "flash_mini", "compact": "flash_compact",
                                  "normal": "flash_normal"}.get(mode_name, "flash_switched")))

    def _set_lang(self, lang):
        if lang == self.cfg.get("lang"):
            return
        self.cfg["lang"] = lang
        save_config(self.cfg)
        self.lbl_detail.setText(tr(self.cfg, "reading"))
        self.update_data(self._data, self._reader_name)
        self._flash(tr(self.cfg, "lang_en") if lang == "en" else tr(self.cfg, "lang_zh"))
        if self.on_lang_change:
            self.on_lang_change(lang)

    # ---- 透明度滑块（不预设固定档位，30%~100% 连续可调）----
    def _show_opacity_popup(self):
        pop = getattr(self, "_opac_popup", None)
        if pop is not None and pop.isVisible():
            pop.close()
            return

        from PySide6.QtWidgets import QSlider
        pop = RoundedPanel()
        pop.setFixedWidth(206)

        box = QVBoxLayout(pop)
        box.setContentsMargins(12, 9, 12, 10)
        box.setSpacing(6)

        lbl = QLabel(f"{tr(self.cfg, 'opacity_title')}  {int(round(self.cfg.get('opacity', 0.88) * 100))}%")
        lbl.setStyleSheet("color: #eaeaea; font-size: 12px; background: transparent;")
        box.addWidget(lbl)

        sld = QSlider(Qt.Orientation.Horizontal, pop)
        sld.setRange(0, 100)
        sld.setValue(int(round(self.cfg.get("opacity", 0.88) * 100)))
        sld.setStyleSheet(
            "QSlider::groove:horizontal{height:6px;background:#3a3d45;border-radius:3px;}"
            "QSlider::sub-page:horizontal{background:#48c78e;border-radius:3px;}"
            "QSlider::handle:horizontal{width:14px;margin:-5px 0;border-radius:7px;"
            "background:#ffffff;}")
        box.addWidget(sld)

        tip = QLabel(tr(self.cfg, "opacity_tip"))
        tip.setStyleSheet("color: #8b9097; font-size: 10px; background: transparent;")
        box.addWidget(tip)

        def on_move(v):
            self.cfg["opacity"] = v / 100.0
            lbl.setText(f"{tr(self.cfg, 'opacity_title')}  {v}%")
            self.repaint()

        def on_commit():
            save_config(self.cfg)

        sld.valueChanged.connect(on_move)
        sld.sliderReleased.connect(on_commit)

        pop._lbl = lbl
        pop._sld = sld
        self._opac_popup = pop
        pop.adjustSize()

        # 贴在卡片下方（下面放不下就放到上面）
        g = self.frameGeometry()
        sp = QGuiApplication.primaryScreen().availableGeometry()
        h = pop.height()
        y = g.bottom() + 6
        if y + h > sp.bottom():
            y = max(sp.top(), g.top() - h - 6)
        x = min(max(sp.left(), g.left()), sp.right() - pop.width())
        pop.move(x, y)
        pop.show()
        pop.raise_()

    # ---- 更新显示 ----
    def update_data(self, data, reader_name=None):
        self._data = data
        if reader_name:
            self._reader_name = reader_name

        edge = data.get("edge")
        self.lbl_temp.setText("--" if edge is None else str(edge))
        self.lbl_temp.set_text_color(temp_color(edge))

        fan = data.get("fan_pct")
        short = self._mode().get("short_fan", False)
        prefix = "" if short else tr(self.cfg, "fan")
        if fan is not None:
            self.lbl_fan.setText(f"{prefix}{fan}%")
        elif data.get("fan_rpm") is not None:
            self.lbl_fan.setText(f"{prefix}{data['fan_rpm']}rpm")
        else:
            self.lbl_fan.setText(f"{prefix}--")

        bits = []
        fields = self._mode()["fields"]
        single = self._mode().get("single_row", False)
        if self.cfg.get("show_detail", True):
            if "hotspot" in fields and data.get("hotspot") is not None:
                bits.append(f"{tr(self.cfg, 'hotspot_short' if single else 'hotspot')}{data['hotspot']}°")
            if "mem" in fields and data.get("mem") is not None:
                bits.append(f"{tr(self.cfg, 'mem_short' if single else 'mem')}{data['mem']}°")
            if "power" in fields and data.get("power") is not None:
                bits.append(f"{data['power']}W")
            if "load" in fields and data.get("load") is not None:
                bits.append(f"{tr(self.cfg, 'load')}{data['load']}%")
        text = "  ".join(bits) if bits else (self._reader_name or tr(self.cfg, "reading"))
        self.lbl_detail.setText(text)
        self.lbl_inline.setText(text.replace("  ", " "))
        self.lbl_inline.setVisible(self._mode().get("single_row", False)
                                   and self.cfg.get("show_detail", True))

        load = data.get("load") or 0
        w = int(self.width() * min(load, 100) / 100.0)
        self.lbl_bar.setStyleSheet(
            f"background: rgba(255,255,255,0.10); border-radius:1px;"
            f"border-left: {w}px solid {temp_color(edge)};")
        self.repaint()

    # ---- 拖动 ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.RightButton:
            self._show_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, e):
        if self._drag_offset is not None:
            self._drag_offset = None
            self._save_pos()

    def mouseDoubleClickEvent(self, e):
        self.cfg["show_detail"] = not self.cfg.get("show_detail", True)
        save_config(self.cfg)
        self._apply_visual_mode()

    def _save_pos(self):
        self.cfg["x"], self.cfg["y"] = self.x(), self.y()
        save_config(self.cfg)

    def _restore_pos(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = self.cfg.get("x")
        y = self.cfg.get("y")
        if x is None or y is None:
            self.move(screen.right() - self.width() - 24, screen.top() + 90)
        else:
            if not screen.contains(QPoint(x + self.width() // 2, y + self.height() // 2)):
                self.move(screen.right() - self.width() - 24, screen.top() + 90)
            else:
                self.move(x, y)

    def _show_menu(self, pos):
        menu = self.build_menu()
        menu.exec(pos)

    def build_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1b1c20;color:#eaeaea;border:1px solid #333;padding:4px;}"
            "QMenu::item{padding:6px 18px;}QMenu::item:selected{background:#2d2f36;}")

        ct = QAction(("✔ " if self.cfg["click_through"] else "") + tr(self.cfg, "menu_click_through"), menu)
        ct.triggered.connect(lambda: self.toggle_click_through())
        menu.addAction(ct)

        top = QAction(("✔ " if self.cfg["always_on_top"] else "") + tr(self.cfg, "menu_top"), menu)
        top.triggered.connect(self._toggle_top)
        menu.addAction(top)

        op = menu.addMenu(tr(self.cfg, "menu_bg"))
        nb = QAction(("✔ " if self.cfg.get("no_bg") else "") + tr(self.cfg, "menu_no_bg"), menu)
        nb.triggered.connect(self._toggle_no_bg)
        op.addAction(nb)
        op.addSeparator()
        sl = QAction(tr(self.cfg, "menu_opacity",
                        p=int(round(self.cfg.get("opacity", 0.88) * 100))), menu)
        sl.triggered.connect(self._show_opacity_popup)
        op.addAction(sl)

        sm = menu.addMenu(tr(self.cfg, "menu_size"))
        cur_mode = self.cfg.get("size_mode", "compact")
        for key, label_key in (("mini", "size_mini"), ("compact", "size_compact"), ("normal", "size_normal")):
            m = SIZE_MODES[key]
            label = tr(self.cfg, label_key, w=m["size"][0], h=m["size"][1])
            a = QAction(("✔ " if cur_mode == key else "") + label, menu)
            a.triggered.connect(lambda _=False, k=key: self._set_size_mode(k))
            sm.addAction(a)

        it = menu.addMenu(tr(self.cfg, "menu_interval"))
        for label, v in ((tr(self.cfg, "sec", v="0.5"), 500),
                         (tr(self.cfg, "sec", v="1"), 1000),
                         (tr(self.cfg, "sec", v="2"), 2000)):
            a = QAction(("✔ " if self.cfg["interval"] == v else "") + label, menu)
            a.triggered.connect(lambda _=False, vv=v: self._set_interval(vv))
            it.addAction(a)

        lm = menu.addMenu("语言 / Language")
        for label, key in (("中文", "zh"), ("English", "en")):
            a = QAction(("✔ " if self.cfg.get("lang", "zh") == key else "") + label, menu)
            a.triggered.connect(lambda _=False, k=key: self._set_lang(k))
            lm.addAction(a)

        menu.addSeparator()
        quit_a = QAction(tr(self.cfg, "menu_quit"), menu)
        quit_a.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_a)

        return menu

    def _toggle_top(self):
        self.cfg["always_on_top"] = not self.cfg["always_on_top"]
        save_config(self.cfg)
        self.setWindowFlags(self._flags())
        self.show()
        QTimer.singleShot(0, lambda: apply_win32_styles(int(self.winId()), self.cfg["click_through"]))

    def _set_opacity(self, v):
        self.cfg["opacity"] = v
        save_config(self.cfg)
        self.repaint()

    def _set_interval(self, v):
        self.cfg["interval"] = v
        save_config(self.cfg)
        if self.on_interval_change:
            self.on_interval_change(v)

    def toggle_click_through(self):
        self.cfg["click_through"] = not self.cfg["click_through"]
        save_config(self.cfg)
        apply_win32_styles(int(self.winId()), self.cfg["click_through"])
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self.cfg["click_through"])
        if self.cfg["click_through"]:
            self._flash(tr(self.cfg, "pass_on"))
        else:
            self._flash(tr(self.cfg, "pass_off"))
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        set_no_activate(int(self.winId()))
        self.raise_()


# --------------------------------------------------------------------------- #
# 主程序
# --------------------------------------------------------------------------- #
def make_tray_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(72, 199, 142), 2))
    p.setBrush(QColor(20, 22, 26))
    p.drawRoundedRect(3, 3, 58, 58, 16, 16)
    p.setPen(QColor(72, 199, 142))
    f = QFont("Segoe UI", 26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "G")
    p.end()
    return QIcon(pm)


class Monitor(QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.card = OverlayCard(self.cfg)
        self.card.on_interval_change = lambda v: self.timer.start(v)
        self.card.on_lang_change = lambda _l: self._apply_lang_to_tray()

        self.reader, self.error = make_reader()

        # 热键队列
        self.hk_queue = queue.Queue()
        self.hk = HotkeyThread({1: (MOD_CONTROL | MOD_ALT, ord("G")),
                                2: (MOD_CONTROL | MOD_ALT, ord("H")),
                                3: (MOD_CONTROL | MOD_ALT, ord("Q"))}, self.hk_queue)
        self.hk.start()
        self.hk_timer = QTimer(self)
        self.hk_timer.timeout.connect(self._poll_hotkeys)
        self.hk_timer.start(150)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.cfg["interval"])

        self.top_timer = QTimer(self)
        self.top_timer.timeout.connect(self._keep_top)
        self.top_timer.start(3000)

        self._tray = None
        self._tray_menu = None
        self._setup_tray()

        if self.reader is None:
            self.card.update_data({}, tr(self.card.cfg, "read_fail", e=self.error))
        self.card.show()
        self.refresh()

    def _apply_lang_to_tray(self):
        """语言切换后刷新托盘文案"""
        if self._tray is None:
            return
        cfg = self.card.cfg
        self._tray.setToolTip(tr(cfg, "app_tip"))
        if self._a_show is not None:
            self._a_show.setText(tr(cfg, "tray_show") if self.card.isVisible() else tr(cfg, "tray_hide"))
        if self._a_ct is not None:
            self._a_ct.setText(tr(cfg, "tray_ct_on") if cfg.get("click_through") else tr(cfg, "tray_ct_off"))
        if self._a_top is not None:
            self._a_top.setText(tr(cfg, "tray_top"))
        if self._a_quit is not None:
            self._a_quit.setText(tr(cfg, "tray_quit"))
        self.refresh()

    def _setup_tray(self):
        """托盘图标：穿透模式下窗口点不到，这里始终留一条退路"""
        cfg = self.card.cfg
        self._tray = QSystemTrayIcon(make_tray_icon(), self)
        self._tray.setToolTip(tr(cfg, "app_tip"))

        menu = QMenu()
        self._a_show = QAction(tr(cfg, "tray_show"), menu)
        self._a_show.triggered.connect(self._toggle_card)
        menu.addAction(self._a_show)

        self._a_ct = QAction(tr(cfg, "tray_ct_on"), menu)
        self._a_ct.triggered.connect(self.card.toggle_click_through)
        menu.addAction(self._a_ct)

        self._a_top = QAction(tr(cfg, "tray_top"), menu)
        self._a_top.setCheckable(True)
        self._a_top.setChecked(self.cfg.get("always_on_top", True))
        self._a_top.triggered.connect(self._toggle_top)
        menu.addAction(self._a_top)

        menu.addSeparator()
        self._a_quit = QAction(tr(cfg, "tray_quit"), menu)
        self._a_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(self._a_quit)

        menu.aboutToShow.connect(self._refresh_tray_menu)
        self._tray_menu = menu
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _refresh_tray_menu(self):
        cfg = self.card.cfg
        ct = cfg.get("click_through", False)
        self._a_ct.setText(tr(cfg, "tray_ct_on") if ct else tr(cfg, "tray_ct_off"))
        self._a_show.setText(tr(cfg, "tray_show") if self.card.isVisible() else tr(cfg, "tray_hide"))
        self._a_top.setText(tr(cfg, "tray_top"))
        self._a_top.setChecked(cfg.get("always_on_top", True))

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._toggle_card()

    def _toggle_card(self):
        self.card.setVisible(not self.card.isVisible())
        if self.card.isVisible():
            self.card.show()

    def _toggle_top(self, checked):
        self._set_top(bool(checked))

    def _set_top(self, on):
        self.card.cfg["always_on_top"] = on
        save_config(self.card.cfg)
        self.card.setWindowFlags(self.card._flags())
        self.card.show()
        QTimer.singleShot(0, lambda: apply_win32_styles(
            int(self.card.winId()), self.card.cfg["click_through"]))

    def _keep_top(self):
        if self.cfg.get("always_on_top"):
            try:
                self.card.raise_()
            except Exception:
                pass

    def _poll_hotkeys(self):
        while True:
            try:
                hid = self.hk_queue.get_nowait()
            except queue.Empty:
                break
            if hid == 1:
                self.card.toggle_click_through()
            elif hid == 2:
                self.card.setVisible(not self.card.isVisible())
            elif hid == 3:
                QApplication.instance().quit()

    def refresh(self):
        if self.reader is None:
            return
        try:
            data = self.reader.read()
            self.card.update_data(data, None)
            if self._tray is not None:
                cfg = self.card.cfg
                ct = tr(cfg, "pass_suffix") if cfg.get("click_through") else ""
                self._tray.setToolTip(tr(cfg, "tray_live", t=data.get("edge"), s=ct))
        except Exception as e:
            self.card.update_data({}, tr(self.card.cfg, "read_error", e=e))


def main():
    if sys.platform != "win32":
        print("Windows only")
        return
    # DPI 感知交给 Qt 自己处理（默认 Per-Monitor V2），不要提前调用 SetProcessDpiAwareness
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationName(APP_NAME)
    monitor = Monitor()

    # 自检用：--shot <png> 渲染一张卡片截图后退出
    if "--shot" in sys.argv:
        path = sys.argv[sys.argv.index("--shot") + 1]

        def snap():
            monitor.refresh()
            monitor.card.grab().save(path)
            print("saved", path)
            app.quit()

        QTimer.singleShot(1200, snap)

    app.exec()


if __name__ == "__main__":
    main()
