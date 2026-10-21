# generated package init — loads every user map module
from pathlib import Path as _P
import importlib.util as _iu

FRACS = []
for _f in sorted(_P(__file__).parent.glob("*.py")):
    if _f.stem.startswith("_"):
        continue
    _sp = _iu.spec_from_file_location("usermaps." + _f.stem, _f)
    assert _sp is not None and _sp.loader is not None
    _m = _iu.module_from_spec(_sp)
    _sp.loader.exec_module(_m)
    FRACS.append(_m.make())
