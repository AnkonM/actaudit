"""Tab 2 · Dataset Bias (Experiment 2): representation, reference shares,
intersectional counts, missingness and label base rates by protected group, with a
rule-generated findings summary. All numbers come from analysis/data_bias.py.
"""
import pandas as pd
import streamlit as st

import pipeline
from ui import charts, state
from ui.components import md_escape, threshold_note
from ui.datasets import dataset_picker

db = pipeline.data_bias


@st.cache_data(show_spinner=False, max_entries=32)
def _representation(df: pd.DataFrame, attr: str):
    return db.representation(df, attr)


@st.cache_data(show_spinner=False, max_entries=16)
def _intersection(df: pd.DataFrame, a: str, b: str):
    return db.intersectional_counts(df, a, b)


@st.cache_data(show_spinner=False, max_entries=16)
def _missing(df: pd.DataFrame, attr: str):
    return db.missingness_by_group(df, attr)


@st.cache_data(show_spinner=False, max_entries=16)
def _base_rates(df: pd.DataFrame, attr: str, label: str, positive):
    return db.label_base_rates(df, attr, label, positive)


def _art10_note() -> None:
    result = state.analysis()
    if result is not None and result.classification.tier == pipeline.RiskTier.HIGH_RISK:
        st.info(f"{db.ART10_NOTE}\n\n:gray-badge[{db.ART10_CITATION}] "
                f"{':blue-badge[citation verified]' if db.ART10_VERIFIED else ':orange-badge[unverified]'}",
                title=f"Data governance for {md_escape(result.source_label)} (High-Risk)",
                icon=":material/gavel:")


def _representation_section(ds, rep) -> None:
    st.markdown(f"##### Representation — {md_escape(rep.attribute)}")
    left, right = st.columns([3, 2], gap="large")
    with left:
        min_share = pipeline.config.value("MIN_GROUP_SHARE")
        charts.hbar(rep.table, "group", "share", "Share of rows",
                    rules=[(min_share, f"minimum share {min_share:.0%}")],
                    tooltip=["group", "count", "share"])
    with right:
        st.metric("Imbalance ratio (largest ÷ smallest)", f"{rep.imbalance_ratio:.1f}×",
                  delta="imbalanced" if rep.imbalanced else "within threshold",
                  delta_color="inverse" if rep.imbalanced else "off", delta_arrow="off")
        st.dataframe(rep.table, hide_index=True, column_config={
            "share": st.column_config.NumberColumn("share", format="percent"),
            "below_min_share": st.column_config.CheckboxColumn("below minimum"),
        })
        if rep.missing:
            st.caption(f"{rep.missing:,} rows have no value for this attribute (not counted).")
    threshold_note("MIN_GROUP_SHARE", "IMBALANCE_RATIO")


def _reference_section(rep, key: str):
    with st.expander("Compare with reference population shares (optional)", icon=":material/public:"):
        st.caption("Enter the share you'd expect for each group in the population the system "
                   "serves (e.g. census figures). Shares are normalised to 100% over the groups "
                   "you fill in; leave a row blank to skip it.")
        editor = st.data_editor(
            pd.DataFrame({"group": rep.table["group"], "expected %": [None] * len(rep.table)}),
            hide_index=True, disabled=["group"], key=f"{key}_ref_{rep.attribute}",
            column_config={"expected %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0)},
        )
        expected = {g: v for g, v in zip(editor["group"], editor["expected %"]) if pd.notna(v) and v > 0}
        if not expected:
            return None
        comparison = db.reference_comparison(rep, expected)
        st.dataframe(comparison, hide_index=True, column_config={
            "observed_share": st.column_config.NumberColumn(format="percent"),
            "expected_share": st.column_config.NumberColumn(format="percent"),
            "ratio": st.column_config.NumberColumn(format="%.2f"),
        })
        threshold_note("REF_UNDER", "REF_OVER")
        return comparison


def _intersection_section(ds):
    if len(ds.protected) < 2:
        st.caption(":material/join: Choose a second protected attribute above to see "
                   "intersectional counts.")
        return None
    a, b = ds.protected[:2]
    inter = _intersection(ds.df, a, b)
    st.markdown(f"##### Intersectional counts — {md_escape(a)} × {md_escape(b)}")
    pivot = inter.table.pivot(index=a, columns=b, values="count")
    st.dataframe(pivot, column_config={c: st.column_config.NumberColumn(format="%d") for c in pivot.columns})
    small = inter.table[inter.table["small"]]
    if not small.empty:
        st.warning(f"{inter.small_cells} combination(s) have fewer than "
                   f"{int(pipeline.config.value('SMALL_CELL'))} rows and {inter.empty_cells} never "
                   "occur. Statistics for them are unreliable or impossible.",
                   icon=":material/grid_off:")
    threshold_note("SMALL_CELL")
    return inter


def _missing_section(ds, attr: str):
    st.markdown(f"##### Missing values by {md_escape(attr)}")
    missing = _missing(ds.df, attr)
    if missing.empty:
        st.success("No column has missing values.", icon=":material/check_circle:")
    else:
        percent_cols = [c for c in missing.columns if c not in ("column", "flagged")]
        st.dataframe(missing, hide_index=True, column_config={
            **{c: st.column_config.NumberColumn(format="percent") for c in percent_cols},
            "flagged": st.column_config.CheckboxColumn("gap flagged"),
        })
    threshold_note("MISSINGNESS_GAP")
    return missing


def _base_rate_section(ds, attr: str):
    if not ds.label:
        st.caption(":material/label: Choose a label column above to compare outcome base rates.")
        return None
    base = _base_rates(ds.df, attr, ds.label, ds.positive_label)
    st.markdown(f"##### Base rate of {md_escape(ds.label)} = {md_escape(ds.positive_label)} "
                f"by {md_escape(attr)}")
    left, right = st.columns([3, 2], gap="large")
    with left:
        charts.hbar(base.table, "group", "base_rate", "Share with the positive label",
                    tooltip=["group", "count", "positives", "base_rate"])
    with right:
        st.metric("Gap (highest − lowest)", f"{base.gap:.1%}",
                  delta="flagged" if base.flagged else "within threshold",
                  delta_color="inverse" if base.flagged else "off", delta_arrow="off")
        st.dataframe(base.table, hide_index=True,
                     column_config={"base_rate": st.column_config.NumberColumn(format="percent")})
    threshold_note("BASE_RATE_GAP")
    return base


def render() -> None:
    _art10_note()
    ds = dataset_picker("t2", need_label=True)
    if ds is None:
        return
    if not ds.protected:
        st.info("Choose at least one protected attribute (e.g. sex or race) to start.",
                icon=":material/person_search:")
        return
    attr = ds.protected[0]
    if len(ds.protected) == 2:
        attr = st.segmented_control("Attribute to analyse", ds.protected, default=ds.protected[0],
                                    required=True) or ds.protected[0]
    rep = _representation(ds.df, attr)
    _representation_section(ds, rep)
    reference = _reference_section(rep, "t2")
    inter = _intersection_section(ds)
    missing = _missing_section(ds, attr)
    base = _base_rate_section(ds, attr)

    st.subheader("Findings")
    st.caption("Generated by fixed rules from the numbers above — no LLM is involved.")
    for line in db.findings(rep, reference, inter, missing, base):
        st.markdown(f"- {md_escape(line)}")
