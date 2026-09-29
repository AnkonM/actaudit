"""ActAudit Streamlit entry point (blueprint §8, §15). Run with: streamlit run app.py

A thin shell: page config, shared state, header with the "Currently loaded" line, the
eight experiment tabs (ui/tabs.py) and the sidebar. All UI lives in the ui/ package,
which reaches the backend only through pipeline.py.
"""
import streamlit as st
from dotenv import load_dotenv

from ui.layout import render_header, render_sidebar
from ui.state import init_state
from ui.tabs import render_tabs

load_dotenv()  # local development only; a missing .env is fine

st.set_page_config(page_title="ActAudit", page_icon=":material/balance:", layout="wide",
                   initial_sidebar_state="collapsed")  # room for all eight tab labels
init_state()

header = st.container()  # filled after the tabs, so "Currently loaded" reflects this run
render_tabs()  # the selected tab may load an analysis or dataset
with header:
    render_header()
render_sidebar()  # last, so its usage counter reflects this run's analysis
