"""AppTests for the analysis-reading tabs 3, 6 and 7A (offline, facts built by hand)."""
import pytest
import streamlit as st

from schema import DecisionAutonomy as A, DeploymentDomain as D, SyntheticMediaType as M
from tests.helpers import make_result
from tests.test_tabs import open_tab

T3, T6, T7 = "3 · Synthetic Media", "6 · Impact Assessment", "7 · Robustness & Autonomy"


@pytest.fixture(autouse=True)
def _clear_cache():
    st.cache_data.clear()
    yield


def texts(at) -> str:
    parts = [e.value for g in (at.markdown, at.caption, at.info, at.warning, at.success) for e in g]
    return "\n".join(str(p) for p in parts)


@pytest.mark.parametrize("tab,key", [(T3, "t3"), (T6, "t6"), (T7, "t7")])
def test_empty_state_prompts_tab_1_and_offers_examples(tab, key):
    at = open_tab(tab)
    assert not at.exception
    assert "No system is loaded yet" in texts(at) and "Tab 1 · System Audit" in texts(at)
    assert any(b.key and b.key.startswith(f"{key}_") for b in at.button)


def test_tab3_voice_cloner():
    result = make_result("VoiceClone", generates_synthetic_media=True, synthetic_media_types=(M.AUDIO,),
                         impersonation_capable=True)
    at = open_tab(T3, current_analysis=result, analysis_origin="fixture")
    assert not at.exception
    text = texts(at)
    assert "**EU AI Act Art. 50(2)** · Provider duty :red-badge[:material/gavel: Applies]" in text
    assert "Overall misuse vulnerability:** :red-badge[High]" in text
    assert "**Impersonation and fraud.**" in text
    matrix = next(t.value for t in at.table if "Vulnerability" in t.value.columns)
    assert matrix["Capability"].tolist() == ["Impersonation of a real person", "Synthetic audio"]


def test_tab3_non_generative_system():
    at = open_tab(T3, current_analysis=make_result(), analysis_origin="fixture")
    assert "nothing to score" in texts(at)


def test_tab6_assessment_and_downloads():
    result = make_result("HireBot", deployment_domain=D.HIRING, decision_autonomy=A.FULLY_AUTONOMOUS)
    at = open_tab(T6, current_analysis=result, analysis_origin="fixture")
    assert not at.exception
    subheaders = [h.value for h in at.subheader]
    assert subheaders == ["UNESCO and IEEE principle flags", "Impact assessment", "Impact level",
                          "Recommended actions", "Download"]
    text = texts(at)
    for point in "abcdef":
        assert f"**({point}) " in text
    assert "not determinable" in text and "Not the official Canadian scoring" in text
    downloads = at.get("download_button")
    assert len(downloads) == 2


def test_tab6_includes_dataset_results_when_loaded():
    from tests.test_data_tabs import ADULT, T2, load_demo
    at = load_demo(open_tab(T2), "t2", ADULT, T2)
    at.session_state["current_analysis"] = make_result("HireBot", deployment_domain=D.HIRING)
    at.session_state["main_tabs"] = T6
    at.run()
    assert "Dataset results" in [h.value for h in at.subheader]
    assert at.toggle(key="t6_include_dataset").value is True


def test_tab7_out_of_scope_system():
    result = make_result("Sentinel", military_defence_use=True, decision_autonomy=A.HUMAN_IN_LOOP)
    at = open_tab(T7, current_analysis=result, analysis_origin="fixture")
    assert not at.exception
    text = texts(at)
    assert "the EU AI Act does not apply (Rule 0)" in text
    assert "meaningful human control" in text
    assert text.count("Not required (the Act doesn't apply)") == 3
    assert "robustness study hasn't been recorded yet" in text or "Degradation" in text
