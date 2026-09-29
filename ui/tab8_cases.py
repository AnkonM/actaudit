"""Tab 8 · Case Library (Experiment 8): documented AI incidents, each run through
ActAudit from a neutral description of the system, compared with what happened."""
import streamlit as st

import pipeline
from ui import state
from ui.components import md_escape, tier_badge

cl = pipeline.case_library


@st.cache_data(show_spinner=False)
def _cases():
    return cl.load_cases()


def _load(case) -> None:
    state.set_analysis(pipeline.load_example(case.fixture, label=case.title), "fixture", "Case Library")


def _analysis(case) -> None:
    status = pipeline.example_status(case.fixture)
    if status == "not_recorded":
        st.info("ActAudit's analysis of this description hasn't been recorded yet "
                "(`python scripts/record_all.py`).", icon=":material/hourglass_empty:")
        return
    result = pipeline.load_example(case.fixture, label=case.title)
    c = result.classification
    st.caption("ActAudit's reading of the description")
    with st.container(horizontal=True, gap="small", vertical_alignment="center"):
        tier_badge(c.tier.value)
        st.markdown(f":gray-badge[Rule {c.rule_number}] {md_escape(c.provision)}")
    if result.principles:
        st.markdown("**Principle flags:** " + ", ".join(
            f"{p.unesco}" + (" (documentation gap)" if p.documentation_gap else "")
            for p in result.principles))
    st.markdown("**Would the AI Act have caught this?** "
                + md_escape(cl.would_act_catch(case, c.tier, c.provision, result.extraction.facts)))
    st.button("Load into the other tabs", key=f"t8_load_{case.id}", icon=":material/upload_file:",
              on_click=_load, args=(case,), help="Makes this case the loaded system for Tabs 1, 3–7.")


def _card(case) -> None:
    with st.container(border=True, key=f"t8_case_{case.id}"):
        st.markdown(f"#### {md_escape(case.title)}")
        st.caption(f"{case.date} · {md_escape(case.jurisdiction)}")
        incident, audit = st.columns([3, 2], gap="large")
        with incident:
            st.markdown(f"**What happened.** {md_escape(case.what_happened)}")
            st.markdown(f"**Harm.** {md_escape(case.harm)}")
            st.markdown(f"**What followed.** {md_escape(case.what_followed)}")
            with st.expander("System description analysed by ActAudit", icon=":material/description:"):
                st.markdown(md_escape(case.system_description))
            st.markdown("**Sources:** " + " · ".join(
                f"[{md_escape(s.publisher)}]({s.url})" for s in case.sources))
            for note in case.unverified:
                st.caption(f":orange-badge[unverified] {md_escape(note)}")
        with audit:
            _analysis(case)


def render() -> None:
    try:
        cases = _cases()
    except (cl.CaseDataError, FileNotFoundError, ValueError) as exc:
        st.warning(f"The case data couldn't be loaded ({md_escape(exc)}).", icon=":material/error:")
        return
    st.caption(":material/info: Each tier is ActAudit's reading of a neutral description of the "
               "system, not a legal finding about the incident. Facts marked unverified could "
               "not be checked against a source.")
    for case in cases:
        _card(case)
