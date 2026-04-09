# -*- mode: python ; coding: utf-8 -*-
"""
veo3_mac.spec — Build para Mac
Uso: pyinstaller veo3_mac.spec --clean -y
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

BASE = Path(SPECPATH)

# Coleta playwright completo (driver Node.js + dados)
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

a = Analysis(
    [str(BASE / "launcher.py")],
    pathex=[str(BASE)],
    binaries=pw_binaries,
    datas=[
        (str(BASE / "templates"), "templates"),
        (str(BASE / "prompts"),   "prompts"),
        (str(BASE / "img_base"),  "img_base"),
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
    console=True,       # Mantém terminal para ver logs (mude para False versão final)
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# .app bundle para Mac
app = BUNDLE(
    exe,
    name="VEO3.app",
    icon=None,
    bundle_identifier="com.veo3.automator",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleDisplayName": "VEO3 Automator",
        "CFBundleVersion": "1.0.0",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
