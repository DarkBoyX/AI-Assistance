# PyInstaller spec - run via build.bat
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hidden = [("assets", "assets")], [], []
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "edge_tts", "sounddevice",
            "_sounddevice_data", "keyring", "certifi", "pyautogui", "pyscreeze", "pytweening", "pymsgbox", "mouseinfo"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass
hidden += collect_submodules("vega") + ["win32timezone", "pythoncom", "pywintypes", "win32com.client",
                                         "keyring.backends.Windows", "PySide6.QtMultimedia"]

a = Analysis(["main.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Vega", console=False, icon="assets/vega.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Vega")
