# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

env = "C:\\Users\\VGDC\\Downloads\\env6\\Lib\\site-packages\\"
path = "onnxruntime\\capi"
files = [
    #"onnxruntime_providers_cuda.dll",
    "onnxruntime_providers_shared.dll",
    #"onnxruntime_providers_tensorrt.dll",
]
binaries = [(env + path + "\\" + file, path) for file in files]

a = Analysis(
    ['background_remove.pyw'],
    pathex=[],
    binaries=[],
    datas=binaries,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='background_remove',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='background_remove',
)
