"""Pure, Streamlit-free analysis modules for the experiment tabs (blueprint §15).

Every module here is re-exported by pipeline.py, the UI's only backend interface.
None of them calls an LLM: each judgment is a deterministic rule or plain computation.
"""
