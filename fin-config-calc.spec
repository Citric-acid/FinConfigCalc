import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


hidden_imports = collect_submodules("fin_config_calc")
data_files = collect_data_files(
    "fin_config_calc",
    includes=["ui/user_guide.html"],
) + copy_metadata("fin-config-calc")
binary_files = [(str(Path(sys.prefix) / "Library" / "bin" / "libexpat.dll"), ".")]

analysis = Analysis(
    ["src/fin_config_calc/ui/__main__.py"],
    pathex=["src"],
    binaries=binary_files,
    datas=data_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "beartype",
        "certifi",
        "charset_normalizer",
        "cryptography",
        "duckdb",
        "fastparquet",
        "numpy",
        "oss2",
        "pandas",
        "pydantic",
        "requests",
        "setuptools",
        "xlsxwriter",
    ],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="FinConfigCalc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

distribution = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FinConfigCalc",
)