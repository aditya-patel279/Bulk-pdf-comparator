# -*- mode: python ; coding: utf-8 -*-
"""
run_app.spec
PyInstaller build specification for Bulk PDF Comparator.

Produces a --onedir build (a folder containing BulkPDFComparator.exe).
onedir is strongly preferred over onefile for Streamlit apps because:
  - Startup is instant (no temp-dir extraction on every run)
  - Streamlit's static assets (JS/CSS/fonts) load reliably from disk
  - Total size on disk is the same either way

Distribute the entire  dist/BulkPDFComparator/  folder to end-users.
They double-click  BulkPDFComparator.exe  inside that folder.
"""

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
)

datas: list        = []
binaries: list     = []
hiddenimports: list = []

# ── Streamlit  ──────────────────────────────────────────────────────────────
# Must use collect_all — Streamlit ships thousands of static asset files
# (JS bundles, fonts, images) that are served to the browser at runtime.
_st_d, _st_b, _st_h = collect_all("streamlit")
datas         += _st_d
binaries      += _st_b
hiddenimports += _st_h

# ── Altair  (Streamlit's built-in chart library) ────────────────────────────
try:
    _a_d, _a_b, _a_h = collect_all("altair")
    datas         += _a_d
    binaries      += _a_b
    hiddenimports += _a_h
except Exception:
    pass

# ── PyMuPDF (fitz)  ─────────────────────────────────────────────────────────
try:
    _f_d, _f_b, _f_h = collect_all("fitz")
    datas         += _f_d
    binaries      += _f_b
    hiddenimports += _f_h
except Exception:
    pass

# ── Data files for the remaining runtime packages ───────────────────────────
for _pkg in [
    "pandas", "pdfplumber", "pdfminer",
    "PIL", "openpyxl", "rapidfuzz",
    "pytesseract", "reportlab", "pyarrow",
]:
    try:
        datas         += collect_data_files(_pkg)
        hiddenimports += collect_submodules(_pkg)
    except Exception:
        pass

# ── App source files  ────────────────────────────────────────────────────────
# These land at the root of _MEIPASS, mirroring the source tree layout
# so that  resource_path("streamlit_app.py")  resolves correctly.
datas += [
    ("streamlit_app.py", "."),
    ("engine",           "engine"),
    ("utils",            "utils"),
    ("reports",          "reports"),
]

# ── Extra hidden imports PyInstaller commonly misses ─────────────────────────
hiddenimports += [
    # Streamlit internals
    "streamlit.runtime.scriptrunner.magic_funcs",
    "streamlit.runtime.caching",
    "streamlit.runtime.caching.storage",
    "streamlit.runtime.legacy_caching",
    "streamlit.components.v1",
    # Arrow / pandas
    "pyarrow",
    "pyarrow.vendored.version",
    # PDF parsing
    "pdfminer.high_level",
    "pdfminer.layout",
    "pdfminer.converter",
    "pdfminer.pdfpage",
    "pdfminer.pdfinterp",
    # Image processing
    "PIL._tkinter_finder",
]

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ["run_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Strip heavy packages that are definitely not used
    excludes=["matplotlib", "scipy", "sklearn", "tensorflow", "torch", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BulkPDFComparator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # Keep console window — gives users a "Close this window to stop" prompt
    icon=None,      # Swap in a .ico path here if you have one: icon="app.ico"
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BulkPDFComparator",
)
