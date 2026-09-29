"""The eight experiment tabs: verbatim course captions, shared state, isolation."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ui.tabs import TABS, TABS_KEY

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")

# The course's wording, exactly (prompt §1 / blueprint §15.2). Do not "fix" it.
EXPECTED = [
    ("1 · System Audit", "Experiment 1 — Ethical Analysis of AI Applications"),
    ("2 · Dataset Bias", "Experiment 2 — Detecting Dataset Bias in AI System"),
    ("3 · Synthetic Media", "Experiment 3 — Deepfake Vulnerability Assessment and Ethical Analysis"),
    ("4 · Proxy Audit", 'Experiment 4 — Auditing the "Cost-as-a-Proxy" Resource Bias'),
    ("5 · Fairness & Explainability", "Experiment 5 — Implementing AI Fairness and Explainability Dashboard"),
    ("6 · Impact Assessment",
     "Experiment 6 — Operationalizing UNESCO & IEEE Frameworks via Algorithmic Impact Assessments"),
    ("7 · Robustness & Autonomy", "Experiment 7 — Autonomous Target Selection and System Degradation Auditing"),
    ("8 · Case Library", "Experiment 8 — Case Study on AI Ethics and Regulations"),
]


def test_tab_labels_and_captions_match_the_course_wording():
    assert [(t.label, t.caption) for t in TABS] == EXPECTED


def test_blueprint_tab_table_matches():
    blueprint = (ROOT / "docs" / "ActAudit_Project_Blueprint.md").read_text()
    for label, caption in EXPECTED:
        assert f"| {label} | {caption} |" in blueprint


def test_every_tab_has_a_one_sentence_blurb():
    for tab in TABS:
        assert tab.blurb.endswith(".") and tab.blurb.count(". ") == 0, tab.label


def open_tab(label: str | None = None, **state) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    if label is not None:
        at.session_state[TABS_KEY] = label
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def test_main_tabs_render_in_order_and_tab_1_is_default():
    at = open_tab()
    assert [t.label for t in at.tabs][:8] == [label for label, _ in EXPECTED]
    assert EXPECTED[0][1] in [c.value for c in at.caption]


@pytest.mark.parametrize("label,caption", EXPECTED)
def test_each_tab_renders_alone_with_its_caption(label, caption):
    at = open_tab(label)
    assert not at.exception
    captions = [c.value for c in at.caption]
    assert caption in captions  # exact caption element
    other = [c for _, c in EXPECTED if c != caption]
    assert not any(c in captions for c in other)  # lazy: only the open tab ran


def _loaded_line(at: AppTest) -> str:
    return next(c.value for c in at.caption if "Currently loaded" in c.value)


def test_currently_loaded_line_starts_empty():
    assert _loaded_line(open_tab()) == (
        ":material/inventory_2: Currently loaded — System: none · Dataset: none"
    )


def test_quick_pick_shows_in_currently_loaded_line_on_every_tab():
    at = open_tab()
    at.button(key="qp_Résumé parser (hiring)").click().run()
    line = _loaded_line(at)
    assert "OmkarPathak/pyresparser" in line and "Tab 1 quick\\-pick" in line
    at.session_state[TABS_KEY] = "6 · Impact Assessment"
    at.run()
    assert _loaded_line(at) == line  # shared state survives switching tabs


def test_tab_1_ethical_analysis_and_pointers():
    at = open_tab()
    at.button(key="qp_Résumé parser (hiring)").click().run()  # High-Risk, hiring
    assert not at.exception
    assert "Ethical analysis" in [h.value for h in at.subheader]
    markdown = [m.value for m in at.markdown]
    assert "Job applicants and employees" in markdown
    assert any(m.startswith("**Allocative** :orange-badge[") for m in markdown)
    captions = [c.value for c in at.caption]
    assert any("project heuristic" in c for c in captions)
    assert any(c.startswith(":material/arrow_forward: High-risk systems must use") and "Tab 2" in c
               for c in captions)
