"""Tab 7 · Robustness & Autonomy (Experiment 7).

A. Autonomy and scope of the loaded system (Rule 0, decision autonomy, Art. 14 / 15
   documentation checks).
B. Degradation study of ActAudit itself, precomputed by scripts/robustness_study.py.
"""
import streamlit as st

import pipeline
from ui import charts
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


@st.cache_data(show_spinner=False, ttl=60)
def _runs():
    return pipeline.robustness.load_runs()


def render_degradation() -> None:
    rb = pipeline.robustness
    st.subheader("B · Degradation study of ActAudit")
    st.caption("How stable are ActAudit's own verdicts when the model changes, when the README "
               "loses information, or when someone plants text aimed at the extractor? Precomputed "
               "by `scripts/robustness_study.py` from five recorded READMEs; this section makes no "
               "API call.")
    runs = _runs()
    if not runs:
        st.info("The robustness study hasn't been recorded yet. Run `python scripts/record_all.py` "
                "to record it; this section needs no live API call.", icon=":material/hourglass_empty:")
        return
    models = tuple(pipeline.MODEL_CHAIN)
    reference = rb.reference_model(runs, models[0])
    matrix = rb.stability_matrix(runs, models, reference)
    flips = rb.field_flip_rates(runs, reference)
    injections = rb.injection_summary(runs, reference)

    st.markdown("##### Findings")
    for line in rb.findings(matrix, flips, injections):
        st.markdown(f"- {md_escape(line)}")

    st.markdown("##### Stability matrix")
    st.caption(f"Each cell is the tier ActAudit gave. Baseline: the unmodified README on "
               f"{md_escape(reference)} (the reference model); the other model columns use the same "
               "text on another model; text perturbations use the reference model. “n/a”: the "
               "perturbation leaves that text unchanged (e.g. truncating a short sample).")
    order = [rb.perturbation_label(p) for p in rb.perturbation_order(models)]
    charts.state_heatmap(matrix, "perturbation", "subject", "state", "cell", order,
                         [label for _, label in rb.SUBJECTS])
    with st.expander("Stability matrix as a table", icon=":material/table:"):
        st.dataframe(matrix.pivot(index="subject", columns="perturbation", values="cell")[order]
                     .reindex([label for _, label in rb.SUBJECTS]))

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("##### How often each fact flips")
        shown = flips[flips["flips"] > 0]
        if shown.empty:
            st.caption("No extracted fact differed from its baseline in the recorded runs.")
        else:
            charts.hbar(shown, "field", "flip_rate", "Share of perturbed runs where the fact differs "
                        "from the baseline", tooltip=["field", "flips", "runs", "flip_rate"])
    with right:
        st.markdown("##### Injection resistance")
        st.dataframe(injections[["subject", "injection", "outcome", "baseline", "injected",
                                 "facts_changed", "booleans_true_to_false"]], hide_index=True)
        st.caption("“resisted”: same tier and no extracted fact changed from the baseline.")
    st.caption("Injected texts: “" + md_escape(rb.CLAIM) + "” and “" + md_escape(rb.INSTRUCTION) + "”")


def render() -> None:
    render_autonomy()
    st.divider()
    render_degradation()
