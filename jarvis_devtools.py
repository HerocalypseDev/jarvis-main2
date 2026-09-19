"""Repository analysis, unit-test generation and module boilerplate.

Deterministic and local: Python files are parsed with `ast` (never imported or executed here),
no model call is made. Output is only ever written as NEW files; an existing file is never
overwritten. Generated tests are safe skeletons: they check that each public function/class
exists with the expected parameters and leave a skipped TODO for real behaviour. They never
call the code under test, so generating or running them cannot trigger side effects beyond
the module's own import.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SKIP_DIRS = {".git", "venv", ".venv", "env", "node_modules", "__pycache__", "graphify-out", ".cache", "tests_generated", "build", "dist"}
MAX_FILES = 40
MAX_BYTES = 400_000


def _py_files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or p.name.startswith("test_") or p.name.endswith("_test.py"):
            continue
        try:
            if p.stat().st_size <= MAX_BYTES:
                out.append(p)
        except OSError:
            pass
    return out


def _public_api(path: Path) -> list[tuple[str, str, list[str]]]:
    """[(kind, name, params)] for top-level public functions and classes."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return []
    api = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            a = node.args
            params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
            api.append(("function", node.name, params))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            api.append(("class", node.name, []))
    return api


def _existing_tests(root: Path) -> set[str]:
    names = set()
    for p in root.rglob("test_*.py"):
        if not any(part in SKIP_DIRS - {"tests_generated"} for part in p.relative_to(root).parts):
            names.add(p.stem[5:])
    return names


def analyze_repo(repo_path: str) -> str:
    root = Path(repo_path).expanduser()
    if not root.is_dir():
        return f"{repo_path} is not a folder."
    files = _py_files(root)
    tested = _existing_tests(root)
    lines, untested = [], 0
    for p in files[:MAX_FILES]:
        api = _public_api(p)
        has = p.stem in tested
        untested += 0 if has or not api else 1
        lines.append(f"{p.relative_to(root)}: {len(api)} public items, {'has tests' if has else 'no tests'}")
    style = "pytest" if (root / "pytest.ini").exists() or (root / "conftest.py").exists() or tested else "no test setup found"
    return (
        f"{len(files)} Python files ({style}); {untested} with public code but no tests.\n"
        + "\n".join(lines[:25])
    )


def _test_source(rel: Path, mod_name: str, api: list[tuple[str, str, list[str]]]) -> str:
    depth = len(rel.parts)  # tests_generated/ sits one level under the repo root
    out = [
        f'"""Generated skeleton tests for {rel.as_posix()} (Jarvis). Edit freely; never overwritten."""',
        "import importlib.util",
        "import inspect",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        f"_SRC = Path(__file__).resolve().parent.parent.joinpath(*{list(rel.parts)!r})",
        "",
        "",
        "@pytest.fixture(scope='module')",
        "def mod():",
        f"    spec = importlib.util.spec_from_file_location({mod_name!r}, _SRC)",
        "    m = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(m)",
        "    return m",
        "",
    ]
    for kind, name, params in api:
        safe = re.sub(r"\W", "_", name)
        out += ["", f"def test_{safe}_exists(mod):", f"    assert hasattr(mod, {name!r})"]
        if kind == "function":
            out += [
                "",
                f"def test_{safe}_signature(mod):",
                f"    assert list(inspect.signature(mod.{name}).parameters) == {params!r}",
            ]
        out += ["", f"@pytest.mark.skip(reason='TODO: real behaviour of {name}')", f"def test_{safe}_behaviour(mod):", "    ..."]
    return "\n".join(out) + "\n"


def generate_tests(repo_path: str, max_files: int = 10) -> str:
    root = Path(repo_path).expanduser()
    if not root.is_dir():
        return f"{repo_path} is not a folder."
    tested = _existing_tests(root)
    out_dir = root / "tests_generated"
    written, skipped = [], 0
    for p in _py_files(root):
        if len(written) >= max(1, min(int(max_files or 10), MAX_FILES)):
            break
        api = _public_api(p)
        rel = p.relative_to(root)
        target = out_dir / f"test_{'_'.join(rel.with_suffix('').parts)}.py"
        if not api or p.stem in tested or target.exists():
            skipped += 1
            continue
        out_dir.mkdir(exist_ok=True)
        target.write_text(_test_source(rel, p.stem, api), encoding="utf-8")
        written.append(target.name)
    if not written:
        return f"No new tests written ({skipped} files skipped: already tested, no public code, or already generated)."
    return f"Wrote {len(written)} test files to {out_dir}: {', '.join(written)}. Run them with pytest."


def scaffold_module(repo_path: str, name: str, description: str = "") -> str:
    """New `<name>.py` plus a matching test file, in the style the repo already uses."""
    root = Path(repo_path).expanduser()
    if not root.is_dir():
        return f"{repo_path} is not a folder."
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name or ""):
        return "Module name must be lowercase letters, digits and underscores."
    mod, test = root / f"{name}.py", root / f"test_{name}.py"
    if mod.exists() or test.exists():
        return f"{name}.py or test_{name}.py already exists; not overwriting."
    doc = (description or f"{name} module.").strip().replace('"""', "'''")
    mod.write_text(
        f'"""{doc}"""\n\nfrom __future__ import annotations\n\nimport logging\n\nlog = logging.getLogger(__name__)\n\n\n'
        f"def run() -> str:\n    log.info(\"{name}.run called\")\n    raise NotImplementedError\n",
        encoding="utf-8",
    )
    test.write_text(
        f"import pytest\n\nimport {name}\n\n\ndef test_run_is_a_stub():\n    with pytest.raises(NotImplementedError):\n        {name}.run()\n",
        encoding="utf-8",
    )
    return f"Created {mod.name} and {test.name} in {root}."
