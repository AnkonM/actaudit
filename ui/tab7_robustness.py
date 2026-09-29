"""Tab 7 · Robustness & Autonomy (Experiment 7).

A. Autonomy and scope of the loaded system (Rule 0, decision autonomy, Art. 14 / 15
   documentation checks).
B. Degradation study of ActAudit itself, precomputed by scripts/robustness_study.py.
"""
import streamlit as st

import pipeline
from ui.components import md_escape, quote_evidence, require_analysis, tier_badge

au = pipeline.autonomy


def render_autonomy() -> None:
    st.subheader("A · Autonomy and scope")
    result = require_analysis("t7", pipeline.EXAMPLE_SETS["autonomy"], source="Tab 7")
    if result is None:
        return
    facts = result.extraction.facts
    tier = result.classification.tier
    scope = au.scope_result(facts)
    with st.container(border=True):
        left, right = st.columns([1, 3], gap="large")
        with left:
            st.caption("EU AI Act tier")
            tier_badge(tier.value)
        with right:
            st.markdown(f"**Scope ({scope.citation}):** {scope.text}")
            if "military_defence_use" in facts.evidence_snippets:
                quote_evidence("military_defence_use", facts.evidence_snippets["military_defence_use"])
    if scope.out_of_scope or facts.decision_autonomy.value == "fully_autonomous":
        st.info(au.MEANINGFUL_HUMAN_CONTROL, icon=":material/pan_tool:")
    st.markdown("##### Decision autonomy")
    st.markdown(f"`decision_autonomy` = `{facts.decision_autonomy.value}` — "
                f"{au.AUTONOMY_TEXT[facts.decision_autonomy]}")
    if "decision_autonomy" in facts.evidence_snippets:
        quote_evidence("decision_autonomy", facts.evidence_snippets["decision_autonomy"])
    if result.schema_version < pipeline.SCHEMA_VERSION:
        st.caption(":material/history_toggle_off: Recorded with an older schema: robustness "
                   "testing, fail-safe and military use show their defaults (false).")
    st.markdown("##### Documentation checks (Art. 14 and 15)")
    for check in au.documentation_checks(facts, tier):
        with st.container(border=True):
            badge = (":green-badge[:material/check: documented]" if check.documented
                     else ":orange-badge[:material/close: not documented]")
            st.markdown(f"**{check.provision}** {badge} :gray-badge[{check.status}]")
            st.caption(f"{check.requirement} From `{check.field}`.")
            if check.evidence:
                quote_evidence(check.field, check.evidence)
    for line in au.autonomy_findings(facts, tier):
        st.markdown(f"- {line}")


def render_degradation() -> None:
    st.subheader("B · Degradation study of ActAudit")
    st.info("The robustness study hasn't been recorded yet. Run `python scripts/record_all.py` "
            "to record it; this section needs no live API call.", icon=":material/hourglass_empty:")


def render() -> None:
    render_autonomy()
    st.divider()
    render_degradation()
