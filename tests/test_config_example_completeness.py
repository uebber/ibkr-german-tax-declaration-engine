"""
Guard: a fresh clone configured by copying src/config_example.py must support
EVERY config read in the application — no AttributeError lurking behind a
developer's richer local src/config.py.

legal_basis: infrastructure — this masked real breakage once: the Vorabpauschale
code read the since-retired config.BASISZINS_BY_YEAR, every test stayed green
against a local config that still had the table, and only a clean-clone run
would have failed.
"""
import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _names_assigned_in_config_example():
    tree = ast.parse((SRC / "config_example.py").read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _config_attributes_read_in_src():
    reads = {}
    pattern = re.compile(r"\bconfig\.([A-Z][A-Z0-9_]*)")
    for py in SRC.rglob("*.py"):
        if py.name in ("config.py", "config_example.py"):
            continue
        for attr in pattern.findall(py.read_text()):
            reads.setdefault(attr, set()).add(str(py.relative_to(SRC)))
    return reads


def test_every_config_read_is_defined_in_config_example():
    defined = _names_assigned_in_config_example()
    missing = {attr: sorted(files)
               for attr, files in _config_attributes_read_in_src().items()
               if attr not in defined}
    assert not missing, (
        "src/ reads config attributes that src/config_example.py does not "
        f"define — a clean clone would crash: {missing}")
