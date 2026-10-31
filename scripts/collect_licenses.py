"""Collect installed dependency and Python/Tcl/Tk distribution notices for packaging."""
import importlib.metadata
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dest = root / 'licenses'
dest.mkdir(exist_ok=True)
for name in ('pypdf','tzdata','pyinstaller','altgraph','packaging','pefile','pyinstaller-hooks-contrib','pywin32-ctypes'):
    dist = importlib.metadata.distribution(name)
    for item in dist.files or []:
        path = Path(str(item))
        if any(x in path.name.lower() for x in ('license','copying','notice')) and dist.locate_file(item).is_file():
            shutil.copyfile(dist.locate_file(item), dest / (name + '-' + path.name))
base = Path(sys.base_prefix)
for name in ('LICENSE.txt','LICENSE'):
    if (base / name).exists():
        shutil.copyfile(base / name,dest / 'Python-LICENSE.txt')
for module in ('tcl8.6','tk8.6'):
    path = base / 'tcl' / module / 'license.terms'
    if path.exists():
        shutil.copyfile(path,dest / (module + '-license.terms'))
if not (dest / 'Python-LICENSE.txt').exists():
    raise RuntimeError('Python distribution license must be included.')
print('Collected notices:',len(list(dest.iterdir())))
