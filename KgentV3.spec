# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('daily_reporter/web/static', 'daily_reporter/web/static'), ('daily_reporter/web/templates', 'daily_reporter/web/templates'), ('ai_report_prompt.md', '.')],
    hiddenimports=['daily_reporter', 'daily_reporter.web', 'daily_reporter.web.app', 'daily_reporter.web.routes', 'daily_reporter.web.routes.snapshots', 'daily_reporter.web.routes.reports', 'daily_reporter.web.routes.compare', 'daily_reporter.ai', 'daily_reporter.config', 'daily_reporter.diff', 'daily_reporter.reporter', 'daily_reporter.snapshot', 'daily_reporter.tasks', 'daily_reporter.ui', 'uvicorn', 'uvicorn.logging', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KgentV3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
