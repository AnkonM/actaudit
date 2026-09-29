"""Shared session state for the eight tabs, initialised in one place (blueprint §15.3).

- current_analysis: the AnalysisResult every analysis-reading tab uses (Tabs 1, 3, 4A,
  5B, 6, 7A), set by a live audit, a quick-pick, a case or a tab's example selector.
- dataset: the uploaded or demo dataset plus column choices (Tabs 2, 4B, 5A). Column
  choices live here, not in widget state, because lazy tabs drop the state of widgets
  that aren't rendered; each tab's pickers start from and write back to this object.
"""
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st


@dataclass
class DatasetState:
    name: str  # shown in the "Currently loaded" line
    source: str  # "demo" or "upload"
    df: pd.DataFrame
    rows_original: int  # before sampling to the row cap
    sampled: bool
    synthetic: bool  # a generated demo dataset (always labelled as such)
    note: str = ""  # provenance line shown under the picker
    protected: list[str] = field(default_factory=list)
    label: str | None = None
    positive_label: Any = None
    prediction: str | None = None


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("current_analysis", None)
    ss.setdefault("analysis_origin", None)  # "live" | "cached" | "fixture"
    ss.setdefault("analysis_source", None)  # where it was loaded from, for display
    ss.setdefault("dataset", None)  # DatasetState | None
    ss.setdefault("error", None)  # Tab 1 live-analysis error: (title, message, icon)
    ss.setdefault("live_count", 0)


def set_analysis(result: Any, origin: str, source: str) -> None:
    st.session_state.current_analysis = result
    st.session_state.analysis_origin = origin
    st.session_state.analysis_source = source
    st.session_state.error = None


def clear_analysis() -> None:
    st.session_state.current_analysis = None
    st.session_state.analysis_origin = None
    st.session_state.analysis_source = None
    st.session_state.error = None


def analysis() -> Any:
    return st.session_state.current_analysis


def dataset() -> DatasetState | None:
    return st.session_state.dataset
