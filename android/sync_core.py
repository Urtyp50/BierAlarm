"""Copy the readers of the Home Assistant integration into android/bieralarm/.

The app uses exactly the same code; only the Home Assistant parts are left out.
Run before building: python android/sync_core.py
"""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "custom_components" / "bieralarm"
DST = Path(__file__).resolve().parent / "bieralarm"
FILES = ["const.py", "models.py"]
SOURCES = ["__init__.py", "billa.py", "hofer.py", "interspar.py", "lidl.py", "mpreis.py", "nuxt.py", "pdf_layout.py", "penny.py"]

if DST.exists():
    shutil.rmtree(DST)
(DST / "sources").mkdir(parents=True)
(DST / "__init__.py").write_text('"""BierAlarm readers, copied from custom_components/bieralarm."""\n', encoding="utf-8")
for name in FILES:
    shutil.copy2(SRC / name, DST / name)
for name in SOURCES:
    shutil.copy2(SRC / "sources" / name, DST / "sources" / name)
print(f"copied {len(FILES) + len(SOURCES)} files to {DST}")
