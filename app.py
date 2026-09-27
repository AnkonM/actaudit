"""ActAudit Streamlit dashboard (Blueprint Section 8). UI only.

pipeline.py is the only backend interface: every result, error type and quick-pick
comes through it. Run with: streamlit run app.py
"""
from dataclasses import fields
from enum import Enum

import streamlit as st
from dotenv import load_dotenv

import pipeline

load_dotenv()

TIER_COLORS = {  # (background, text) — §8: red / amber / green
    "Prohibited": ("#b71c1c", "#ffffff"),
    "High-Risk": ("#c62828", "#ffffff"),
    "Limited-Risk": ("#f59e0b", "#1f1300"),
    "Minimal-Risk": ("#2e7d32", "#ffffff"),
}

# §8.1: one friendly, specific title per failure type; the exception's own message
# (already actionable) goes underneath. Most specific classes first.
ERROR_TITLES: list[tuple[type[Exception], str]] = [
    (pipeline.InvalidRepoURLError, "That doesn't look like a GitHub repository URL"),
    (pipeline.RepoNotFoundError, "Repository not found"),
    (pipeline.ReadmeNotFoundError, "No README found"),
    (pipeline.RateLimitedError, "GitHub is rate-limiting requests"),
    (pipeline.NetworkError, "Couldn't reach GitHub"),
    (pipeline.EmptyInputError, "Nothing to analyze"),
    (pipeline.ExtractionAPIError, "The Gemini API is unavailable"),
    (pipeline.MalformedExtractionError, "The model returned unusable output"),
]


def _run(action, origin: str) -> None:
    st.session_state.pop("result", None)
    st.session_state.pop("error", None)
    try:
        with st.spinner("Fetching and analyzing… this can take a few seconds."):
            st.session_state["result"] = action()
            st.session_state["origin"] = origin
    except Exception as exc:  # never show a stack trace in the UI
        for cls, title in ERROR_TITLES:
            if isinstance(exc, cls):
                st.session_state["error"] = (title, str(exc))
                break
        else:
            st.session_state["error"] = (
                "Something went wrong",
                f"An unexpected error occurred ({type(exc).__name__}). Please try again.",
            )


def _value_str(value) -> str:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_input() -> None:
    mode = st.radio("Input", ["GitHub URL", "Paste text"], horizontal=True, label_visibility="collapsed")
    if mode == "GitHub URL":
        url = st.text_input("Public GitHub repository URL", placeholder="https://github.com/owner/repo")
        if st.button("Analyze", type="primary", key="analyze_url"):
            _run(lambda: pipeline.analyze_github(url), "live")
    else:
        text = st.text_area(
            "Documentation text (README, model card, product description…)", height=220
        )
        if st.button("Analyze", type="primary", key="analyze_text"):
            _run(lambda: pipeline.analyze_text(text), "live")

    st.caption("Or try a pre-loaded example (served from recorded results — no network needed):")
    labels = pipeline.quick_pick_labels()
    per_row = 3
    for start in range(0, len(labels), per_row):
        cols = st.columns(per_row)
        for col, label in zip(cols, labels[start:start + per_row]):
            if col.button(label, key=f"qp_{label}", width="stretch"):
                _run(lambda label=label: pipeline.analyze_quick_pick(label), "fixture")


def render_badge(result) -> None:
    tier = result.classification.tier.value
    bg, fg = TIER_COLORS[tier]
    st.markdown(
        f'<div style="background:{bg};color:{fg};padding:18px 24px;border-radius:10px;'
        f'font-size:2rem;font-weight:700;text-align:center;">{tier}</div>',
        unsafe_allow_html=True,
    )
    origin = (
        "recorded example (no live API call)"
        if st.session_state.get("origin") == "fixture"
        else "live analysis"
    )
    st.caption(
        f"Source: **{result.source_label}** · Extracted by `{result.extraction.model}` · {origin}"
    )


def render_why(result) -> None:
    c = result.classification
    st.subheader("Why this tier")
    # §8: justification and provision always on two separate lines, no deduplication.
    st.markdown(c.justification)
    st.markdown(f"**Provision:** {c.provision}")
    st.caption(f"Rule {c.rule_number} of the ordered rule table fired (first match wins).")
    for name, snippet in c.evidence.items():
        st.markdown(f"> **{name}** — “{snippet}”")


def render_facts(result) -> None:
    facts = result.extraction.facts
    st.subheader("Extracted facts")
    if facts.extraction_confidence.value == "low":
        st.warning(
            "**Low extraction confidence.** The documentation contained little relevant "
            "information, so this classification rests on incomplete documentation — "
            "itself a finding worth noting."
        )
    rows = [
        {
            "Field": f.name,
            "Value": _value_str(getattr(facts, f.name)),
            "Evidence": facts.evidence_snippets.get(f.name, ""),
        }
        for f in fields(facts)
        if f.name != "evidence_snippets"
    ]
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_flags(flags) -> None:
    for flag in flags:
        st.markdown(f"**{flag.unesco}** (UNESCO) · **{flag.ieee}** (IEEE EAD)")
        st.markdown(flag.explanation)
        for name, snippet in flag.evidence.items():
            st.markdown(f"> **{name}** — “{snippet}”")


def render_principles(result) -> None:
    st.subheader("UNESCO / IEEE principles")
    fact_based = [f for f in result.principles if not f.documentation_gap]
    gaps = [f for f in result.principles if f.documentation_gap]
    if not result.principles:
        st.success("No UNESCO/IEEE principle concerns were flagged.")
        return
    if fact_based:
        st.markdown("##### Flagged from stated facts")
        _render_flags(fact_based)
    if gaps:
        st.markdown("##### Documentation gaps")
        st.caption("Raised because the documentation doesn't say something, not because of a stated fact.")
        _render_flags(gaps)


def render_source(result) -> None:
    total = len(result.source_text)
    with st.expander("Raw source that was analyzed"):
        if result.readme is not None:
            st.caption(f"Fetched from {result.readme.source_url}")
        if result.llm_input_truncated:
            st.info(
                f"Model saw a truncated copy ({pipeline.MAX_INPUT_CHARS:,} of {total:,} "
                "characters). The full original is shown below."
            )
        st.code(result.source_text, language="markdown", wrap_lines=True)


def main() -> None:
    st.set_page_config(page_title="ActAudit", layout="wide")
    st.title("ActAudit")
    st.markdown(
        "Classify an AI system against the **EU AI Act** and **UNESCO / IEEE** principles "
        "from its README or documentation. An LLM extracts facts; a deterministic, "
        "auditable rule engine decides the tier."
    )
    render_input()

    if "error" in st.session_state:
        title, message = st.session_state["error"]
        st.warning(f"**{title}.** {message}")

    result = st.session_state.get("result")
    if result is None:
        return
    st.divider()
    render_badge(result)
    left, right = st.columns([3, 2])
    with left:
        render_why(result)
        render_facts(result)
    with right:
        render_principles(result)
    render_source(result)
    st.caption(
        "Decision-support and educational tool only — not legal advice or a compliance "
        "certification."
    )


main()
