"""Blueprint §15.1 invariants that are checked statically over the UI source."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_FILES = [ROOT / "app.py", *sorted((ROOT / "ui").glob("*.py"))]
ALLOWED_TOP_LEVEL = {"streamlit", "pandas", "altair", "dotenv", "pipeline", "ui",
                     "os", "re", "dataclasses", "enum", "typing", "urllib", "io", "json",
                     "datetime", "math", "hashlib", "collections", "functools", "__future__"}
BACKEND = {"schema", "rules", "principles", "extractor", "github_fetch", "analysis", "examples"}


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_ui_reaches_the_backend_only_through_the_pipeline_facade():
    for path in UI_FILES:
        imported = _imports(path)
        assert not imported & BACKEND, f"{path.name} imports {imported & BACKEND}"
        assert imported <= ALLOWED_TOP_LEVEL, f"{path.name}: {imported - ALLOWED_TOP_LEVEL}"


def test_raw_html_only_in_the_design_system_module():
    """Only ui/components.py may emit HTML, and only from fixed templates."""
    for path in UI_FILES:
        source = path.read_text()
        if path.name == "components.py":
            continue
        assert "unsafe_allow_html" not in source, path.name
        assert "st.html(" not in source.replace("st.html(verdict_banner_html(", ""), path.name
    components = (ROOT / "ui" / "components.py").read_text()
    assert "unsafe_allow_html" not in components  # st.html with fixed strings only


def test_md_escape_neutralises_markdown_and_html():
    from ui.components import md_escape
    hostile = "[click](javascript:alert(1)) <b>x</b> :red[boom] $x$ **bold**\nline"
    escaped = md_escape(hostile)
    import re
    # Every Markdown-special character is preceded by a backslash, so none is active.
    assert not re.search(r"(?<!\\)[\[\]()<>:*$]", escaped)
    assert "\\[click\\]\\(javascript" in escaped
    assert "\n" not in escaped


def test_thresholds_live_in_config():
    """§15.1: analysis modules compare against config values, not hard-coded thresholds.

    Flags any comparison with a fractional numeric literal (e.g. `x > 0.8`). Integers such
    as 0, 1 or a band bound in a documented scoring table are not thresholds of this kind.
    """
    offenders = []
    for path in sorted((ROOT / "analysis").glob("*.py")):
        if path.name == "config.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Compare):
                for operand in [node.left, *node.comparators]:
                    if isinstance(operand, ast.Constant) and isinstance(operand.value, float):
                        offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
