# -*- mode: python ; coding: utf-8 -*-
"""GpuTempFloat 单文件打包配置：精简 Qt 运行时 + UPX 压缩。

用法（由 打包exe.bat 调用）：
    python -m PyInstaller --noconfirm --clean GpuTempFloat.spec
可选环境变量 UPX_DIR：指向 upx.exe 所在目录，缺省用 tools/upx。
"""
import os

HERE = os.path.dirname(os.path.abspath(SPEC)) if "SPEC" in globals() else os.getcwd()

EXCLUDES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner", "PySide6.Qt3DCore",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSerialPort", "PySide6.QtPositioning",
    "PySide6.QtSensors", "PySide6.QtWebSockets", "PySide6.QtHttpServer", "PySide6.QtStateMachine",
    "PySide6.QtXml", "PySide6.QtDBus", "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtSvgWidgets",
    "tkinter", "unittest", "email", "http", "xml", "pydoc", "doctest", "pdb", "distutils",
    "sqlite3", "test", "lib2to3", "asyncio", "multiprocessing", "concurrent",
]

# 需要剔除的运行时文件（按 dest 路径关键词匹配，全部小写比较）
DROP_PATTERNS = [
    "opengl32sw.dll",            # 20MB 软件 OpenGL 兜底，本程序完全不用 GL
    "d3dcompiler_",              # 同上，给软件 GL 用的
    "qt6network.dll",            # 无任何网络访问
    "qtnetwork.pyd",
    "plugins/tls/",              # 网络插件
    "plugins/networkinformation/",
    "qt6svg.dll",                # 图标/图形全用 QPainter 绘制，不读 svg
    "qsvgicon.dll",
    "qsvg.dll",
    "plugins/imageformats/",     # 不加载任何图片文件（PNG 编解码内建于 QtGui）
    "plugins/generic/",          # tuio 触摸插件
    "qdirect2d.dll",             # 备选 QPA 后端，默认用 qwindows
    "qminimal.dll",
    "qoffscreen.dll",
]


def _name(entry):
    return str(entry[0]).replace("\\", "/").lower()


a = Analysis(
    ["gpu_temp_float.py"],
    pathex=[HERE],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

bins = [b for b in a.binaries if not any(p in _name(b) for p in DROP_PATTERNS)]
dropped = len(a.binaries) - len(bins)
print(f"[spec] binaries kept {len(bins)}, dropped {dropped}")

pyz = PYZ(a.pure)

upx_dir = os.environ.get("UPX_DIR") or os.path.join(HERE, "tools", "upx")
use_upx = os.path.isfile(os.path.join(upx_dir, "upx.exe"))
print(f"[spec] upx: {use_upx} ({upx_dir})")

exe = EXE(
    pyz,
    a.scripts,
    bins,
    a.datas,
    [],
    name="GpuTempFloat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=use_upx,
    upx_exclude=["vcruntime140.dll", "msvcp140.dll", "python3", "pyside6.abi3.dll"],
    upx_dir=upx_dir,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(HERE, "assets", "app.ico"),
)
