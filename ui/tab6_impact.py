"""Tab 6 · Impact Assessment (Experiment 6): UNESCO/IEEE principle flags, a structured
impact assessment following Art. 27(1), a project-defined impact level, recommended
actions, and Markdown/PDF downloads."""
import re

import pandas as pd
import streamlit as st

import pipeline
from ui import state
from ui.components import md_escape, render_principles, require_analysis
from ui.tab2_dataset_bias import _base_rates, _representation

ia_mod = pipeline.impact_assessment


def _dataset_findings() -> tuple[str | None, list[str], bool]:
    """Findings from the shared dataset (Tab 2's numbers), if one is loaded and set up."""
    ds = state.dataset()
    if ds is None or not ds.protected:
        return None, [], False
    rep = _representation(ds.df, ds.protected[0])
    base = _base_rates(ds.df, ds.protected[0], ds.label, ds.positive_label) if ds.label else None
    lines = pipeline.data_bias.findings(rep, base=base)
    flagged = rep.imbalanced or bool(rep.table["below_min_share"].any()) or bool(base and base.flagged)
    return ds.name, lines, flagged


def _filename(system: str, ext: str) -> str:
    return "actaudit_impact_" + (re.sub(r"[^A-Za-z0-9]+", "_", system).strip("_")[:40] or "system") + f".{ext}"


def render() -> None:
    result = require_analysis("t6")
    if result is None:
        return
    name, findings, flagged = _dataset_findings()
    include = False
    if name:
        include = st.toggle(f"Include results for the loaded dataset ({md_escape(name)})", value=True,
                            key="t6_include_dataset")
    ia = ia_mod.build(result, name if include else None, findings if include else None,
                      flagged and include)

    st.subheader("UNESCO and IEEE principle flags")
    render_principles(result)

    st.subheader("Impact assessment")
    st.caption(f":material/gavel: Organised by the six elements of EU AI Act Art. 27(1) "
               f":blue-badge[citation verified]. {ia.applicability}")
    for el in ia.elements:
        with st.container(border=True):
            badge = ":green-badge[from facts]" if el.determinable else ":gray-badge[not determinable]"
            st.markdown(f"**({el.point}) {el.title}** {badge}")
            for line in el.lines:
                st.markdown(f"- {md_escape(line)}")

    st.subheader("Impact level")
    lvl = ia.impact
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.metric("Impact level", f"Level {lvl.level}", delta=lvl.meaning, delta_arrow="off",
                  delta_color={"I": "normal", "II": "off"}.get(lvl.level, "inverse"))
        st.markdown(f"Score **{lvl.score}** = {lvl.impact_points} impact points − "
                    f"{lvl.mitigation_points} mitigation points")
        if lvl.override:
            st.caption(lvl.override)
        st.caption(f":material/info: {ia_mod.IMPACT_LEVEL_LABEL}")
    with right:
        st.dataframe(pd.DataFrame(lvl.applied, columns=["Factor", "Condition", "Points"]),
                     hide_index=True)
    with st.expander("Scoring table and level bands", icon=":material/rule:"):
        st.dataframe(pd.DataFrame([(f.label, f.condition_text, f.points) for f in ia_mod.IMPACT_SCORING],
                                  columns=["Factor", "Condition", "Points"]), hide_index=True)
        bands, low = [], 0
        for bound, level, meaning in ia_mod.LEVEL_BANDS:
            bands.append(f"Level {level} ({meaning}): score {low}" + (f"–{bound}" if bound < 10**8 else "+"))
            low = bound + 1
        st.caption(" · ".join(bands) + ". A prohibited practice is always level IV.")

    st.subheader("Recommended actions")
    st.caption("From a fixed rule table: each action names the facts behind it and its citation.")
    # st.table wraps long text; every cell is fixed rule-table text (no user input).
    st.table({
        "Action": [a.action for a in ia.actions],
        "Because": [a.because for a in ia.actions],
        "Citation": [a.citation for a in ia.actions],
        "Status": [":blue-badge[verified]" if a.citation_verified else ":orange-badge[unverified]"
                   for a in ia.actions],
    }, hide_index=True, border="horizontal")

    if ia.dataset_name:
        st.subheader("Dataset results")
        st.caption(f"From Tab 2's checks on {md_escape(ia.dataset_name)}.")
        for line in ia.dataset_findings:
            st.markdown(f"- {md_escape(line)}")

    st.subheader("Download")
    with st.container(horizontal=True, gap="small"):
        st.download_button("Markdown report", ia_mod.to_markdown(ia), _filename(ia.system, "md"),
                           mime="text/markdown", icon=":material/description:", key="t6_md")
        st.download_button("PDF report", ia_mod.to_pdf(ia), _filename(ia.system, "pdf"),
                           mime="application/pdf", icon=":material/picture_as_pdf:", key="t6_pdf")
    st.caption("Both contain the not-legal-advice disclaimer, the tier and rule, citations "
               "with their verified status, principles, the assessment, actions and any "
               "dataset results.")

