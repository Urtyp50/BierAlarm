"""Load the parser modules without importing Home Assistant.

The package __init__ needs Home Assistant, but const/models/sources do not, so
register the package as an empty module and import the submodules directly.
"""

from importlib.machinery import ModuleSpec
from pathlib import Path
import sys
import types

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "bieralarm"

if "bieralarm" not in sys.modules:
    pkg = types.ModuleType("bieralarm")
    pkg.__path__ = [str(PKG_DIR)]
    pkg.__spec__ = ModuleSpec("bieralarm", None, is_package=True)
    sys.modules["bieralarm"] = pkg

FIXTURES = Path(__file__).parent / "fixtures"
