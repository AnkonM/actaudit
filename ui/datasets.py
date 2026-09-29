"""Shared dataset picker for Tabs 2, 4B and 5A (blueprint §15.3).

The dataset and its column choices live in st.session_state.dataset (ui/state.py), so a
choice made in one tab carries over to the others. Each tab's widgets have their own
keys; before rendering they're set from the shared state, and on change they write back.
"""
from typing import Any

import streamlit as st

import pipeline
from ui import state
from ui.components import md_escape, threshold_note
from ui.state import DatasetState

NONE = "— none —"


@st.cache_data(show_spinner=False, max_entries=4)
def _load_demo(dataset_id: str):
    return pipeline.data_bias.load_demo(dataset_id)


@st.cache_data(show_spinner=False, max_entries=4)
def _parse_upload(data: bytes):
    return pipeline.data_bias.load_csv(data)


@st.cache_data(show_spinner=False, max_entries=16)
def group_candidates(df) -> list[str]:
    return pipeline.data_bias.group_column_candidates(df)


def set_demo(dataset_id: str) -> None:
    loaded, meta = _load_demo(dataset_id)
    note = f"{meta['note']} Source: {meta['source']}. Licence: {meta['licence']}."
    st.session_state.dataset = DatasetState(
        name=meta["name"], source="demo", df=loaded.df, rows_original=loaded.rows_original,
        sampled=False, synthetic=meta["synthetic"], note=note,
        protected=list(meta.get("protected", []))[:2], label=meta.get("label"),
        positive_label=meta.get("positive_label"), prediction=meta.get("prediction"), meta=meta,
    )
    st.session_state.pop("dataset_error", None)


def _on_upload(widget_key: str) -> None:
    file = st.session_state.get(widget_key)
    if file is None:
        return
    try:
        loaded = _parse_upload(file.getvalue())
    except pipeline.data_bias.DatasetError as exc:
        st.session_state.dataset_error = str(exc)
        return
    except Exception as exc:  # noqa: BLE001 - never a stack trace
        st.session_state.dataset_error = f"The file couldn't be loaded ({type(exc).__name__})."
        return
    cap = int(pipeline.config.value("ROW_CAP"))
    note = (f"Uploaded file, {loaded.rows_original:,} rows"
            + (f", randomly sampled to {cap:,} rows for computation (seed "
               f"{int(pipeline.config.value('SAMPLE_SEED'))})." if loaded.sampled else "."))
    st.session_state.dataset = DatasetState(
        name=file.name, source="upload", df=loaded.df, rows_original=loaded.rows_original,
        sampled=loaded.sampled, synthetic=False, note=note,
    )
    st.session_state.pop("dataset_error", None)


def _loaders(key: str) -> None:
    demos = pipeline.data_bias.demo_datasets()
    st.markdown("**Bundled demo datasets**")
    with st.container(horizontal=True, gap="small"):
        for meta in demos:
            icon = ":material/science:" if meta["synthetic"] else ":material/table:"
            st.button(meta["name"], key=f"{key}_demo_{meta['id']}", icon=icon,
                      on_click=set_demo, args=(meta["id"],))
    max_mb = pipeline.config.value("MAX_UPLOAD_MB")
    widget = f"{key}_upload"
    st.file_uploader(
        f"Or upload a CSV (up to {max_mb:g} MB; larger datasets are sampled to "
        f"{int(pipeline.config.value('ROW_CAP')):,} rows)",
        type=["csv"], key=widget, max_upload_size=int(max_mb),
        on_change=_on_upload, args=(widget,),
    )


def _sync(widget_key: str, value: Any) -> None:
    st.session_state[widget_key] = value


def _write_back(widget_key: str, attr: str) -> None:
    ds = state.dataset()
    if ds is None:
        return
    value = st.session_state[widget_key]
    if attr in ("label", "prediction") and value == NONE:
        value = None
    setattr(ds, attr, value)
    if attr == "label":  # a new label needs a new positive value
        ds.positive_label = None


def dataset_picker(key: str, need_label: bool = False, need_prediction: bool = False) -> DatasetState | None:
    """Render the picker; return the loaded dataset (or None)."""
    ds = state.dataset()
    with st.container(border=True, key=f"{key}_dataset"):
        if st.session_state.get("dataset_error"):
            st.warning(st.session_state.dataset_error, title="That file couldn't be used",
                       icon=":material/error:")
        if ds is None:
            st.markdown(":material/dataset: **No dataset loaded yet.** Choose a demo dataset "
                        "or upload your own CSV; the choice is shared with the other data tabs.")
            _loaders(key)
            return state.dataset()
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f":material/dataset: **{md_escape(ds.name)}** · {len(ds.df):,} rows · "
                        f"{ds.df.shape[1]} columns")
            if ds.synthetic:
                st.badge("Synthetic data", icon=":material/science:", color="violet")
            if ds.sampled:
                st.badge("Sampled", icon=":material/filter_alt:", color="gray")
            with st.popover("Change dataset", icon=":material/swap_horiz:"):
                _loaders(f"{key}_pop")
        st.caption(md_escape(ds.note))
        if ds.sampled:
            threshold_note("ROW_CAP")
        _column_choices(key, ds, need_label, need_prediction)
    return ds


def _column_choices(key: str, ds: DatasetState, need_label: bool, need_prediction: bool) -> None:
    candidates = group_candidates(ds.df)
    columns = [str(c) for c in ds.df.columns]
    cols = st.columns(4 if (need_label or need_prediction) else 1)
    pk = f"{key}_protected"
    _sync(pk, [c for c in ds.protected if c in candidates])
    cols[0].multiselect(
        "Protected attribute(s)", candidates, key=pk, max_selections=2,
        help="Columns with 2 to "
        f"{int(pipeline.config.value('MAX_CATEGORIES'))} distinct values. Pick two for "
        "intersectional counts.", on_change=_write_back, args=(pk, "protected"),
    )
    if not (need_label or need_prediction):
        return
    lk = f"{key}_label"
    _sync(lk, ds.label if ds.label in columns else NONE)
    cols[1].selectbox("Label (outcome) column", [NONE, *columns], key=lk,
                      on_change=_write_back, args=(lk, "label"))
    if ds.label:
        counts = ds.df[ds.label].dropna().value_counts()
        values = list(counts.index[::-1])[:50]  # least frequent first
        if ds.positive_label not in values:
            # Default: the least frequent value, usually the outcome of interest
            # (e.g. '>50K' or 'Yes'); the user can change it.
            ds.positive_label = values[0] if values else None
        vk = f"{key}_positive"
        _sync(vk, ds.positive_label)
        cols[2].selectbox("Positive label value", values, key=vk, format_func=str,
                          on_change=_write_back, args=(vk, "positive_label"),
                          help="The outcome counted as 'selected' or 'positive'.")
    if need_prediction:
        prk = f"{key}_prediction"
        _sync(prk, ds.prediction if ds.prediction in columns else NONE)
        cols[3].selectbox("Prediction column", [NONE, *columns], key=prk,
                          on_change=_write_back, args=(prk, "prediction"),
                          help="The model's predicted outcome, in the same values as the label.")
