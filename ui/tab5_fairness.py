"""Tab 5 · Fairness & Explainability (Experiment 5).

A. Fairness metrics of a model's predictions on the shared dataset (fairlearn).
B. Explainability of ActAudit itself: the full rule trace, and a what-if explorer that
   re-runs the rule engine and principle mapping on edited facts (no LLM call).
"""
import hashlib

import pandas as pd
import streamlit as st

import pipeline
from ui import charts
from ui.components import md_escape, require_analysis, threshold_note, tier_badge, value_str
from ui.datasets import dataset_picker

fm = pipeline.fairness


# --- A · Fairness metrics ----------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=16)
def _group_metrics(df: pd.DataFrame, attr: str, label: str, pred: str, positive):
    return fm.group_metrics(df, attr, label, pred, positive)


def _confusion_matrices(table: pd.DataFrame) -> None:
    with st.expander("Confusion matrix per group", icon=":material/grid_view:"):
        rows = table.to_dict("records")
        for start in range(0, len(rows), 3):
            for col, row in zip(st.columns(3), rows[start:start + 3]):
                with col:
                    st.markdown(f"**{md_escape(row['group'])}** · {row['n']:,} rows")
                    st.table(pd.DataFrame(
                        {"predicted positive": [row["tp"], row["fp"]],
                         "predicted negative": [row["fn"], row["tn"]]},
                        index=["actual positive", "actual negative"]))


def render_fairness() -> None:
    st.subheader("A · Fairness metrics")
    ds = dataset_picker("t5", need_label=True, need_prediction=True)
    if ds is None:
        return
    missing = [name for name, v in (("a protected attribute", ds.protected), ("a label column", ds.label),
                                     ("a prediction column", ds.prediction)) if not v]
    if missing:
        st.info("Choose " + ", ".join(missing) + " above to compute fairness metrics.",
                icon=":material/tune:")
        return
    attr = ds.protected[0]
    if len(ds.protected) == 2:
        attr = st.segmented_control("Group by", ds.protected, default=ds.protected[0],
                                    required=True) or ds.protected[0]
    if not (ds.df[ds.prediction] == ds.positive_label).any():
        st.warning(f"No value in the prediction column equals the positive label "
                   f"({md_escape(ds.positive_label)}); check that label and prediction use the same values.",
                   icon=":material/warning:")
        return
    try:
        table = _group_metrics(ds.df, attr, ds.label, ds.prediction, ds.positive_label)
    except fm.FairnessError as exc:
        st.warning(str(exc), icon=":material/error:")
        return
    summary = fm.summarise(table)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Demographic parity difference", f"{summary.demographic_parity_difference:.1%}",
              help="Highest minus lowest selection rate.")
    c2.metric("Equal opportunity difference", f"{summary.equal_opportunity_difference:.1%}",
              help="Highest minus lowest true-positive rate.")
    c3.metric("Equalized odds difference", f"{summary.equalized_odds_difference:.1%}",
              help="The larger of the TPR and FPR differences.")
    c4.metric("Disparate impact ratio", f"{summary.disparate_impact_ratio:.2f}",
              delta="passes four-fifths" if summary.passes_four_fifths else "fails four-fifths",
              delta_color="off" if summary.passes_four_fifths else "inverse", delta_arrow="off",
              help="Lowest selection rate divided by the highest.")
    for flag in summary.flags:
        st.markdown(f"- {md_escape(flag)}")
    left, right = st.columns([3, 2], gap="large")
    with left:
        top = float(table["selection_rate"].max())
        ff = pipeline.config.value("FOUR_FIFTHS")
        charts.hbar(table, "group", "selection_rate", "Selection rate (share predicted positive)",
                    rules=[(ff * top, f"four-fifths of highest ({ff * top:.0%})")],
                    tooltip=["group", "n", "selection_rate", "tpr", "fpr"])
    with right:
        st.dataframe(table[["group", "n", "selection_rate", "tpr", "fpr", "precision"]], hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="percent")
                                    for c in ("selection_rate", "tpr", "fpr", "precision")})
        st.caption("TPR: share of actual positives predicted positive. FPR: share of actual "
                   "negatives predicted positive. Blank = undefined for that group.")
    _confusion_matrices(table)
    threshold_note("FOUR_FIFTHS", "FAIRNESS_DIFF")


# --- B · Explainability of the auditor ------------------------------------------------------

def _token(result) -> str:
    return hashlib.md5(f"{result.source_label}|{result.extraction.raw_response}".encode()).hexdigest()[:10]


def _key(token: str, name: str) -> str:
    return f"wi_{token}_{name}"


def _control_value(facts, name: str):
    value = getattr(facts, name)
    if name in pipeline.LIST_ENUM_FIELDS:
        return [v.value for v in value]
    if name in pipeline.ENUM_FIELDS:
        return value.value
    return value


def _init_controls(token: str, facts) -> None:
    for name in pipeline.DISPLAY_ORDER:
        st.session_state.setdefault(_key(token, name), _control_value(facts, name))


def _edited_facts(token: str, facts):
    changes = {}
    for name in pipeline.DISPLAY_ORDER:
        raw = st.session_state[_key(token, name)]
        if name in pipeline.LIST_ENUM_FIELDS:
            cls = pipeline.LIST_ENUM_FIELDS[name]
            value = tuple(cls(v) for v in raw)
        elif name in pipeline.ENUM_FIELDS:
            value = pipeline.ENUM_FIELDS[name](raw)
        else:
            value = raw
        changes[name] = value
    return pipeline.whatif.edit_facts(facts, changes)


def _apply_preset(token: str, values: dict) -> None:
    for name, value in values.items():
        st.session_state[_key(token, name)] = value


def _reset(token: str, facts) -> None:
    for name in pipeline.DISPLAY_ORDER:
        st.session_state[_key(token, name)] = _control_value(facts, name)


def _render_trace(facts, edited: bool) -> None:
    trace = pipeline.classify_with_trace(facts)
    st.markdown("##### Rule trace" + (" — for the what-if facts" if edited else ""))
    st.caption("Every rule in order. The first rule whose whole condition holds decides the "
               "tier; for the others, the parts of the condition that failed are listed.")
    status, why = [], []
    for e in trace.entries:
        if e.decided:
            status.append(":blue-badge[:material/check_circle: Decided]")
            why.append("Every part of the condition holds.")
        elif e.matched:
            status.append(":gray-badge[Matched, not reached]")
            why.append("Also holds, but an earlier rule decided first.")
        else:
            status.append("Not matched")
            why.append("; ".join(f"{c.text} (is {c.actual})" for c in e.failed))
    st.table({
        "Order": [e.number for e in trace.entries],
        "Applies when": [e.condition_text for e in trace.entries],
        "Tier": [e.tier.value for e in trace.entries],
        "Result": status,
        "Why": why,
    }, hide_index=True, border="horizontal")


def _control(token: str, name: str) -> None:
    key = _key(token, name)
    if name in pipeline.LIST_ENUM_FIELDS:
        st.multiselect(name, [e.value for e in pipeline.LIST_ENUM_FIELDS[name]], key=key)
    elif name in pipeline.ENUM_FIELDS:
        st.selectbox(name, [e.value for e in pipeline.ENUM_FIELDS[name]], key=key)
    elif name in pipeline.BOOL_FIELDS:
        st.toggle(name, key=key)
    else:
        limit = pipeline.MAX_PURPOSE_CHARS if name == "system_purpose" else pipeline.MAX_TARGET_CHARS
        st.text_input(name, key=key, max_chars=limit)


def render_explainability() -> None:
    st.subheader("B · Explainability of ActAudit's verdict")
    result = require_analysis("t5")
    if result is None:
        return
    original = result.extraction.facts
    token = _token(result)
    _init_controls(token, original)
    facts = _edited_facts(token, original)
    diff = pipeline.whatif.compare(original, facts)

    st.markdown("##### What-if explorer")
    st.caption("Every extracted fact starts at its extracted value. Change any of them to see "
               "how the fixed rules would classify the system — instantly, with no LLM call. "
               "Edited facts are hypothetical: their evidence snippets are dropped.")
    with st.container(horizontal=True, gap="small"):
        for label, values in pipeline.whatif.PRESETS.items():
            st.button(label, key=f"t5_preset_{label}", icon=":material/auto_fix_high:",
                      on_click=_apply_preset, args=(token, values))
        st.button("Reset to extracted values", key="t5_reset", icon=":material/restart_alt:",
                  on_click=_reset, args=(token, original))
    with st.container(border=True):
        cols = st.columns([2, 3], gap="large")
        with cols[0]:
            st.caption("Extracted")
            tier_badge(diff.original_tier.value)
            st.caption("What-if")
            tier_badge(diff.edited_tier.value)
        with cols[1]:
            for line in pipeline.whatif.describe(diff):
                st.markdown(f"- {line}")
            if diff.changed_fields:
                st.dataframe(pd.DataFrame(
                    [(n, value_str(a), value_str(b)) for n, a, b in diff.changed_fields],
                    columns=["fact", "extracted", "what-if"]), hide_index=True)
    with st.expander("Edit the facts", expanded=True, icon=":material/edit:"):
        grid = st.columns(3)
        for i, name in enumerate(pipeline.DISPLAY_ORDER):
            with grid[i % 3]:
                _control(token, name)
    _render_trace(facts, edited=bool(diff.changed_fields))


def render() -> None:
    render_fairness()
    st.divider()
    render_explainability()
