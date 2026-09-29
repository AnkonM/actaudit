"""Tab 4 · Proxy Audit (Experiment 4).

A. Target-label proxy check on the loaded system (its extracted target_type).
B. Data proxy detection on the shared dataset, featuring the synthetic
   cost-as-a-proxy demo modelled on Obermeyer et al. (2019).
"""
import pandas as pd
import streamlit as st

import pipeline
from ui import charts, state
from ui.components import md_escape, quote_evidence, require_analysis, threshold_note
from ui.datasets import dataset_picker, set_demo

px = pipeline.proxy
COST_DEMO_ID = "cost_proxy"


# --- A -----------------------------------------------------------------------------------

def _pattern_table() -> None:
    with st.expander("The proxy rule table", icon=":material/rule:"):
        st.table({
            "target_type": [t.value for t in px.PROXY_PATTERNS] + ["direct_outcome", "other", "unknown"],
            "Proxy for": [p.stands_in_for for p in px.PROXY_PATTERNS.values()] + ["—", "—", "—"],
            "Result": ["flag"] * len(px.PROXY_PATTERNS) + ["no flag", "no flag", "documentation gap"],
            "Reference case": [p.reference for p in px.PROXY_PATTERNS.values()] + ["", "", ""],
        }, hide_index=True, border="horizontal")


def render_target_check() -> None:
    st.subheader("A · Target-label proxy check")
    examples = pipeline.EXAMPLE_SETS.get("proxy") or None
    result = require_analysis("t4", examples, source="Tab 4")
    if result is None:
        _pattern_table()
        return
    facts = result.extraction.facts
    check = px.target_proxy_check(facts)
    target = facts.target_variable or "not stated"
    c1, c2 = st.columns(2)
    c1.markdown(f"**Target variable:** {md_escape(target)}")
    c2.markdown(f"**Target type:** `{check.target_type.value}`")
    if "target_variable" in facts.evidence_snippets:
        quote_evidence("target_variable", facts.evidence_snippets["target_variable"])
    if result.schema_version < pipeline.SCHEMA_VERSION:
        st.caption(":material/history_toggle_off: Recorded with an older schema: the target was not "
                   "extracted, so it shows as unknown. Load another example or re-run the audit.")
    if check.status == "flag":
        p = check.pattern
        st.warning(f"{check.message}\n\nReference case: [{p.reference}]({p.reference_url})",
                   title=f"Proxy target: {p.proxy} standing in for {p.stands_in_for}",
                   icon=":material/swap_horiz:")
    elif check.status == "unknown":
        st.info(check.message, title="Target not stated", icon=":material/help:")
    else:
        st.success(check.message, title="No known proxy pattern", icon=":material/check_circle:")
    _pattern_table()


# --- B -----------------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=16)
def _associations(df: pd.DataFrame, protected: str, exclude: tuple[str, ...]):
    return px.association_ranking(df, protected, exclude)


@st.cache_data(show_spinner="Running the reconstruction test…", max_entries=16)
def _reconstruct(df: pd.DataFrame, protected: str, exclude: tuple[str, ...]):
    return px.reconstruction_test(df, protected, exclude)


@st.cache_data(show_spinner=False, max_entries=8)
def _cost_demo(df: pd.DataFrame, group: str, need: str, cost: str):
    return px.cost_proxy_selection(df, group, need, cost)


def _cost_demo_section(ds) -> None:
    meta = ds.meta
    group = meta["protected"][0]
    st.markdown("##### Featured: cost as a proxy for need")
    st.caption(":violet-badge[:material/science: synthetic data] Two groups with the same "
               "distribution of true need; at equal need, group B's recorded cost is 30% lower "
               "(unequal access). The programme selects the top patients by predicted cost.")
    demo = _cost_demo(ds.df, group, meta["need_column"], meta["cost_column"])
    band = demo.by_band.assign(series="Group " + demo.by_band[group].astype(str))
    order = sorted(band["series"].unique())
    by_cost, by_need = st.columns(2, gap="large")
    with by_cost:
        st.markdown("Selected **by predicted cost** (what the algorithm does)")
        charts.grouped_hbar(band, "need_band", "series", "selected_by_cost", "Share selected",
                            series_order=order, domain=(0, 1))
    with by_need:
        st.markdown("Selected **by true need** (what the programme intends)")
        charts.grouped_hbar(band, "need_band", "series", "selected_by_need", "Share selected",
                            series_order=order, domain=(0, 1))
    st.caption("Each bar is one group's share selected within one band of true need. At the "
               "same need level, a fair proxy would select both groups equally.")
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.dataframe(demo.overall, hide_index=True, column_config={
            "mean_need": st.column_config.NumberColumn("mean true need", format="%.1f"),
            "selected_by_cost": st.column_config.NumberColumn("selected by cost", format="percent"),
            "selected_by_need": st.column_config.NumberColumn("selected by need", format="percent"),
        })
    with right:
        for line in px.cost_proxy_findings(demo, group):
            st.markdown(f"- {md_escape(line)}")
    with st.expander("Selection rates per need band (table)", icon=":material/table:"):
        st.dataframe(demo.by_band, hide_index=True, column_config={
            "selected_by_cost": st.column_config.NumberColumn(format="percent"),
            "selected_by_need": st.column_config.NumberColumn(format="percent"),
        })
    threshold_note("COST_DEMO_SELECT_SHARE")


def _association_section(ds, protected: str) -> None:
    others = tuple(c for c in ds.protected if c != protected)
    table = _associations(ds.df, protected, others)
    st.markdown(f"##### Association with {md_escape(protected)}")
    st.caption("How strongly each other column is tied to the protected attribute. Numeric "
               "columns use the correlation ratio, categorical ones Cramér's V (both 0 to 1).")
    if table.empty:
        st.info("No other usable columns to compare.", icon=":material/info:")
        return
    moderate, strong = pipeline.config.value("ASSOC_MODERATE"), pipeline.config.value("ASSOC_STRONG")
    left, right = st.columns([3, 2], gap="large")
    with left:
        charts.hbar(table.head(15), "column", "value", "Association (0–1)", percent=False,
                    rules=[(moderate, f"moderate {moderate:g}"), (strong, f"strong {strong:g}")],
                    tooltip=["column", "measure", "value", "level"])
    with right:
        st.dataframe(table, hide_index=True, height=320)
    threshold_note("ASSOC_MODERATE", "ASSOC_STRONG", "MAX_CATEGORIES")


def _reconstruction_section(ds, protected: str) -> None:
    st.markdown("##### Reconstruction test")
    st.caption(f"Can a simple, fixed-seed logistic regression predict **{md_escape(protected)}** "
               "from all the non-protected columns? Cross-validated AUC: 0.5 is chance, 1.0 is "
               "perfect recovery.")
    others = tuple(c for c in ds.protected if c != protected)
    key = f"t4_recon::{ds.name}::{protected}::{others}"
    if st.button("Run reconstruction test", icon=":material/model_training:", key="t4_run_recon"):
        try:
            st.session_state[key] = _reconstruct(ds.df, protected, others)
        except px.ReconstructionError as exc:
            st.session_state[key] = str(exc)
    result = st.session_state.get(key)
    if result is None:
        st.caption("Takes a second or two; results are cached.")
    elif isinstance(result, str):
        st.warning(result, title="The test couldn't run on this data", icon=":material/error:")
    else:
        left, right = st.columns([2, 3], gap="large")
        with left:
            st.metric("Cross-validated AUC", f"{result.auc_mean:.2f}", delta=result.level,
                      delta_color="inverse" if result.level != "low" else "off", delta_arrow="off",
                      help=f"± {result.auc_std:.2f} across folds · {result.rows_used:,} rows · "
                           f"{result.classes} groups")
            st.markdown(md_escape(result.interpretation))
        with right:
            top = pd.DataFrame(result.top_features, columns=["column", "AUC drop when shuffled"])
            charts.hbar(top, "column", "AUC drop when shuffled", "AUC drop when the column is shuffled",
                        percent=False)
    threshold_note("AUC_PROXY", "AUC_STRONG", "CV_FOLDS", "MODEL_SEED", "RECON_ROW_CAP")


def render_data_proxies() -> None:
    st.subheader("B · Data proxy detection")
    if state.dataset() is None:
        with st.container(border=True):
            st.markdown(":material/star: **Featured example — cost as a proxy for need** "
                        ":violet-badge[synthetic data]")
            st.caption("A synthetic dataset built like the Obermeyer et al. (Science, 2019) case: "
                       "two groups with the same true need, where cost under-measures one group's need.")
            st.button("Load the cost-as-a-proxy demo", type="primary", icon=":material/science:",
                      key="t4_featured", on_click=set_demo, args=(COST_DEMO_ID,))
    ds = dataset_picker("t4")
    if ds is None:
        return
    if not ds.protected:
        st.info("Choose a protected attribute to check which columns act as proxies for it.",
                icon=":material/person_search:")
        return
    protected = ds.protected[0]
    if ds.meta.get("id") == COST_DEMO_ID:
        _cost_demo_section(ds)
    _association_section(ds, protected)
    _reconstruction_section(ds, protected)


def render() -> None:
    render_target_check()
    st.divider()
    render_data_proxies()
