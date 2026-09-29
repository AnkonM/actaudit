"""AppTests for the data tabs (2, 4B, 5A) and Tab 5B, offline."""
import pandas as pd
import pytest
import streamlit as st

from tests.test_tabs import open_tab
from ui.state import DatasetState

T2, T4, T5 = "2 · Dataset Bias", "4 · Proxy Audit", "5 · Fairness & Explainability"
ADULT = "UCI Adult income (6,000-row sample)"


@pytest.fixture(autouse=True)
def _clear_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def texts(at) -> str:
    parts = [e.value for group in (at.markdown, at.caption, at.info, at.warning, at.success) for e in group]
    return "\n".join(str(p) for p in parts)


def on_tab(at, tab: str):
    """AppTest doesn't send the tabs widget's own state back on a rerun (a browser does),
    so re-select the tab before every interaction."""
    at.session_state["main_tabs"] = tab
    return at


def load_demo(at, key: str, name: str, tab: str):
    on_tab(at, tab).button(key=f"{key}_demo_{'adult' if 'Adult' in name else 'cost_proxy'}").click().run()
    assert not at.exception
    return at


def test_tab2_empty_state_offers_demo_and_upload():
    at = open_tab(T2)
    assert "No dataset loaded yet" in texts(at)
    assert len(at.get("file_uploader")) == 1
    assert at.button(key="t2_demo_adult") is not None


def test_tab2_on_adult_shows_every_section_and_findings():
    at = load_demo(open_tab(T2), "t2", ADULT, T2)
    text = texts(at)
    for heading in ("##### Representation — sex", "##### Intersectional counts — sex × race",
                    "##### Missing values by sex", "##### Base rate of income = \\>50K by sex"):
        assert heading in text, heading
    assert "Findings" in [h.value for h in at.subheader]
    assert any("reasonably balanced" in m.value for m in at.markdown)  # sex: 67% / 33%
    assert "Minimum group share: 0.1" in text  # thresholds shown next to results
    assert "Dataset: **UCI Adult income" in text  # Currently loaded line


def test_column_choices_carry_over_between_tabs():
    at = load_demo(open_tab(T2), "t2", ADULT, T2)
    on_tab(at, T2).multiselect(key="t2_protected").set_value(["race"]).run()
    at.session_state["main_tabs"] = T5
    at.run()
    assert at.multiselect(key="t5_protected").value == ["race"]
    assert not at.exception


def test_tab4_featured_cost_demo_and_reconstruction():
    at = open_tab(T4)
    on_tab(at, T4).button(key="t4_featured").click().run()
    text = texts(at)
    assert "##### Featured: cost as a proxy for need" in text
    assert "Even among the highest" in text
    assert "insurance\\_type" in text or "insurance_type" in str(at.dataframe[-1].value)
    on_tab(at, T4).button(key="t4_run_recon").click().run()
    assert not at.exception
    assert [m.label for m in at.metric] == ["Cross-validated AUC"]
    assert float(at.metric[0].value) > 0.7


def test_tab4_target_check_on_a_loaded_system():
    at = open_tab()
    at.button(key="qp_Résumé parser (hiring)").click().run()
    at.session_state["main_tabs"] = T4
    at.run()
    assert "**Target type:** `" in texts(at)
    assert not at.exception


def test_tab5_fairness_metrics_on_adult():
    at = load_demo(open_tab(T5), "t5", ADULT, T5)
    labels = [m.label for m in at.metric]
    assert labels == ["Demographic parity difference", "Equal opportunity difference",
                      "Equalized odds difference", "Disparate impact ratio"]
    assert "fails four-fifths" in str(at.metric[3].proto.delta)
    assert "Four-fifths rule: 0.8" in texts(at)


def test_tab5_what_if_preset_and_trace():
    at = open_tab()
    at.button(key="qp_Résumé parser (hiring)").click().run()
    at.session_state["main_tabs"] = T5
    at.run()
    trace = next(t.value for t in at.table if "Why" in t.value.columns)
    assert trace["Order"].tolist() == list(range(0, 9))
    assert (trace["Result"] == ":blue-badge[:material/check_circle: Decided]").sum() == 1
    on_tab(at, T5).button(key="t5_preset_What if the README had disclosed human oversight and transparency?").click().run()
    text = texts(at)
    assert "The tier stays High-Risk (rule 4)." in text
    assert "No longer flagged:" in text
    assert not at.exception


def test_hostile_dataset_names_render_as_text():
    hostile = "[x](javascript:alert(1)) <b>b</b>"
    df = pd.DataFrame({hostile: ["<i>a</i>", "b"] * 20, "y": ["1", "0"] * 20})
    ds = DatasetState(name=hostile, source="upload", df=df, rows_original=40, sampled=False,
                      synthetic=False, note=hostile, protected=[hostile])
    at = open_tab(T2, dataset=ds)
    assert not at.exception
    for element in list(at.markdown) + list(at.caption):
        assert "](javascript" not in element.value and "<b>" not in element.value
