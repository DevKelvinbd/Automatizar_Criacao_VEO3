# -*- mode: python ; coding: utf-8 -*-
"""
veo3_windows.spec — Build para Windows
Uso: pyinstaller veo3_windows.spec --clean -y
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

BASE = Path(SPECPATH)

# Coleta playwright completo (driver Node.js + dados)
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

# img_base é opcional (pode estar vazio ou ausente)
extra_datas = []
if (BASE / "img_base").exists():
    extra_datas.append((str(BASE / "img_base"), "img_base"))

a = Analysis(
    [str(BASE / "launcher.py")],
    pathex=[str(BASE)],
    binaries=pw_binaries,
    datas=[
        (str(BASE / "templates"), "templates"),
        (str(BASE / "prompts"),   "prompts"),
        *extra_datas,
        *pw_datas,
    ],
    hiddenimports=[
        # Flask stack
        "flask", "jinja2", "werkzeug", "werkzeug.serving",
        "werkzeug.routing", "werkzeug.exceptions",
        # Charset / HTTP
        "charset_normalizer",
        # Módulos do projeto (importados dinamicamente no bootstrap)
        "app", "bot_flow", "fatiador", "pipeline", "renomear_takes",
        # Playwright
        *pw_hidden,
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "numpy", "pandas", "cv2", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VEO3",
    debug=False,
    strip=False,
    upx=False,          # UPX pode corromper binários Node.js embutidos
    console=True,       # Mantém terminal para ver logs (mude para False na versão final)
    icon=None,
)
