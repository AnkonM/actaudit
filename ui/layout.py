"""Page chrome shared by every tab: header and sidebar."""
import streamlit as st

from ui.components import NOTICE, loaded_line
from ui.tab1_audit import LIVE_CAP


def render_header() -> None:
    st.title("ActAudit", icon=":material/balance:")
    st.info(NOTICE, icon=":material/school:")
    loaded_line()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Settings", icon=":material/key:")
        st.text_input(
            "Your own Gemini API key (optional)",
            type="password",
            key="byo_key",
            help="Used only for this browser session, held in memory, never logged or "
            "saved. Overrides the demo's shared key and lifts the session limit.",
        )
        if (st.session_state.get("byo_key") or "").strip():
            st.caption(":material/check_circle: Using your own key for live analyses this session.")
        else:
            used = st.session_state.live_count
            st.progress(min(used / LIVE_CAP, 1.0))
            st.caption(f"Live analyses on the shared key this session: {used} of {LIVE_CAP}.")
        st.caption("Repeat submissions of the same input are served from cache and don't count.")
