"""ActAudit Streamlit dashboard (Blueprint Section 8). UI only.

pipeline.py is the only backend interface: every result, error type, quick-pick and
model setting comes through it. Run with: streamlit run app.py
"""
from dataclasses import fields
from enum import Enum

import streamlit as st
from dotenv import load_dotenv

import pipeline

load_dotenv()

LIVE_CAP = 5  # live analyses per session on the server's key (cache hits don't count)
CACHE_TTL_SECONDS = 24 * 60 * 60

# (background, text, icon, subtitle). Colour is never the only signal: every badge
# carries the tier name, an icon and a subtitle, and Prohibited differs from
# High-Risk in all three.
TIER_STYLE = {
    "Prohibited": ("#5c0a0a", "#ffffff", "⛔", "Banned practice under EU AI Act Art. 5"),
    "High-Risk": ("#c62828", "#ffffff", "⚠️", "Allowed, with strict obligations"),
    "Limited-Risk": ("#f59e0b", "#1f1300", "ℹ️", "Transparency duties may apply"),
    "Minimal-Risk": ("#2e7d32", "#ffffff", "✅", "No specific obligations identified"),
}

CSS = """
<style>
.aa-badge {border-radius: 12px; padding: 20px 24px; text-align: center;
           border: 3px solid rgba(0,0,0,.25);}
.aa-badge .aa-icon {font-size: 2rem; line-height: 1;}
.aa-badge .aa-tier-name {font-size: 2.25rem; font-weight: 800; letter-spacing: .02em;
                         margin: 6px 0 2px;}
.aa-badge .aa-sub {font-size: 1rem; font-weight: 500; opacity: .95;}
.aa-badge.aa-prohibited {border-style: double; border-width: 6px; border-color: #ffffff;}
</style>
"""

# §8.1: one friendly, specific title per failure type; the exception's own message
# (already actionable) goes underneath. Most specific classes first.
QUICK_PICK_HINT = "The pre-loaded examples below still work — they need no API call."
ERROR_TITLES: list[tuple[type[Exception], str]] = [
    (pipeline.InvalidRepoURLError, "That doesn't look like a GitHub repository URL"),
    (pipeline.RepoNotFoundError, "Repository not found"),
    (pipeline.ReadmeNotFoundError, "No README found"),
    (pipeline.RateLimitedError, "GitHub is rate-limiting requests"),
    (pipeline.NetworkError, "Couldn't reach GitHub"),
    (pipeline.EmptyInputError, "Nothing to analyze"),
    (pipeline.AllModelsUnavailableError, "All Gemini models are out of quota or busy"),
    (pipeline.ExtractionAPIError, "The Gemini API is unavailable"),
    (pipeline.MalformedExtractionError, "The model returned unusable output"),
]
POINT_TO_QUICK_PICKS = (pipeline.AllModelsUnavailableError, pipeline.ExtractionAPIError)

SIMPLIFICATIONS = """
**Simplified rule table (blueprint §6.2)**
- Rule 1 (real-time remote biometric ID for law enforcement, Art. 5(1)(h)) does not model the Act's statutory exceptions.
- Rule 4 treats every system in a named Annex III domain as High-Risk; the Art. 6(3) narrow-task exemption is not modelled.
- Rules 5, 7 and 8 are project heuristics layered on the Act's tiers, not specific Act provisions.
- Clinical/diagnostic AI (the Annex I medical-device route, Art. 6(1)) is not assessed; only healthcare-*access* AI is.

**Known limitations (blueprint §9)**
- English-only, README/description-only: code and data are not inspected.
- An LLM extracts the facts, so extraction can be wrong; the facts table shows exactly what it extracted.
- Thin documentation lowers extraction confidence; that is itself a finding, not a pass.
"""


@st.cache_data(ttl=CACHE_TTL_SECONDS, max_entries=256, show_spinner=False)
def _cached_analysis(kind: str, value: str, _api_key: str | None, _misses: list) -> "pipeline.AnalysisResult":
    """Cached on (kind, value) only. `_`-prefixed arguments are excluded from the cache
    key and never stored, so a visitor's own key is not part of any cache entry."""
    _misses.append(1)  # runs only on a cache miss
    if kind == "github":
        return pipeline.analyze_github(value, api_key=_api_key)
    return pipeline.analyze_text(value, api_key=_api_key)


def _set_error(exc: Exception) -> None:
    for cls, title in ERROR_TITLES:
        if isinstance(exc, cls):
            message = str(exc)
            if isinstance(exc, POINT_TO_QUICK_PICKS):
                message = f"{message} {QUICK_PICK_HINT}"
            st.session_state["error"] = (title, message)
            return
    st.session_state["error"] = (
        "Something went wrong",
        f"An unexpected error occurred ({type(exc).__name__}). Please try again.",
    )


def _clear_output() -> None:
    for name in ("result", "error", "origin"):
        st.session_state.pop(name, None)


def _run_live(kind: str, raw_value: str) -> None:
    _clear_output()
    own_key = (st.session_state.get("byo_key") or "").strip() or None
    used = st.session_state.get("live_count", 0)
    if own_key is None and used >= LIVE_CAP:
        st.session_state["error"] = (
            "Live analysis limit reached for this session",
            f"This public demo allows {LIVE_CAP} live analyses per session to protect its "
            "shared API quota. The pre-loaded examples below work without limits, or "
            "paste your own Gemini API key in the sidebar to keep analyzing.",
        )
        return
    value = raw_value.strip() if kind == "github" else pipeline.clean_pasted_text(raw_value or "")
    misses: list = []
    try:
        with st.spinner("Fetching and analyzing… this can take a few seconds."):
            result = _cached_analysis(kind, value, _api_key=own_key, _misses=misses)
    except Exception as exc:  # never show a stack trace in the UI
        _set_error(exc)
        return
    st.session_state["result"] = result
    st.session_state["origin"] = "live" if misses else "cached"
    if misses and own_key is None:
        st.session_state["live_count"] = used + 1


def _run_quick_pick(label: str) -> None:
    _clear_output()
    try:
        st.session_state["result"] = pipeline.analyze_quick_pick(label)
        st.session_state["origin"] = "fixture"
    except Exception as exc:
        _set_error(exc)


def _value_str(value) -> str:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_header() -> None:
    st.title("ActAudit")
    st.markdown(
        "ActAudit reads an AI system's README or description and classifies it against the "
        "**EU AI Act** tiers and **UNESCO / IEEE** ethics principles. "
        "An LLM only *extracts* observable facts from the text; a fixed, deterministic rule "
        "table — which you can inspect below every result — decides the tier."
    )
    st.info(
        "**Educational decision-support tool implementing a simplified subset of the EU AI "
        "Act. Not legal advice or a compliance certification.**"
    )
    with st.expander("What's simplified? Acknowledged simplifications and limitations"):
        st.markdown(SIMPLIFICATIONS)


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Settings")
        st.text_input(
            "Your own Gemini API key (optional)",
            type="password",
            key="byo_key",
            help="Used only for this browser session, held in memory, never logged or "
            "saved. Overrides the demo's shared key and lifts the session limit.",
        )
        if (st.session_state.get("byo_key") or "").strip():
            st.caption("Using your own key for live analyses this session.")
        else:
            used = st.session_state.get("live_count", 0)
            st.caption(f"Live analyses on the shared key this session: {used} of {LIVE_CAP}.")
        st.caption("Repeat submissions of the same input are served from cache and don't count.")


def render_input() -> None:
    mode = st.radio("Input", ["GitHub URL", "Paste text"], horizontal=True, label_visibility="collapsed")
    if mode == "GitHub URL":
        url = st.text_input("Public GitHub repository URL", placeholder="https://github.com/owner/repo")
        if st.button("Analyze", type="primary", key="analyze_url"):
            _run_live("github", url)
    else:
        text = st.text_area(
            "Documentation text (README, model card, product description…)", height=200
        )
        if st.button("Analyze", type="primary", key="analyze_text"):
            _run_live("text", text)

    st.caption("Or try a pre-loaded example (served from recorded results — no network or quota needed):")
    labels = pipeline.quick_pick_labels()
    per_row = 3
    for start in range(0, len(labels), per_row):
        cols = st.columns(per_row)
        for col, label in zip(cols, labels[start:start + per_row]):
            if col.button(label, key=f"qp_{label}", width="stretch"):
                _run_quick_pick(label)


def render_badge(result) -> None:
    tier = result.classification.tier.value
    bg, fg, icon, subtitle = TIER_STYLE[tier]
    extra = " aa-prohibited" if tier == "Prohibited" else ""
    st.markdown(
        f'<div class="aa-badge{extra}" style="background:{bg};color:{fg};" role="status" '
        f'aria-label="Risk tier: {tier}">'
        f'<div class="aa-icon">{icon}</div>'
        f'<div class="aa-tier-name">{tier}</div>'
        f'<div class="aa-sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def render_trust(result) -> None:
    origin = {
        "fixture": "recorded example (no live API call)",
        "cached": "cached result (no new API call)",
        "live": "live analysis",
    }[st.session_state.get("origin", "live")]
    st.caption(
        f"Source: **{result.source_label}** · Extracted by `{result.extraction.model}` · {origin}"
    )
    if result.extraction.model != pipeline.MODEL_CHAIN[0]:
        st.caption(
            f"⚠️ A fallback model answered (the primary, `{pipeline.MODEL_CHAIN[0]}`, was "
            "unavailable). Fallback models can extract facts less accurately — check the "
            "facts table below."
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


def render_result(result) -> None:
    st.divider()
    # Order: badge → why this tier → principles → facts → raw source.
    badge_col, why_col = st.columns([1, 2], gap="large")
    with badge_col:
        render_badge(result)
        render_trust(result)
    with why_col:
        render_why(result)
    principles_col, facts_col = st.columns([2, 3], gap="large")
    with principles_col:
        render_principles(result)
    with facts_col:
        render_facts(result)
    render_source(result)


def main() -> None:
    st.set_page_config(page_title="ActAudit", page_icon="⚖️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    render_header()
    render_input()

    if "error" in st.session_state:
        title, message = st.session_state["error"]
        st.warning(f"**{title}.** {message}")

    result = st.session_state.get("result")
    if result is not None:
        render_result(result)
    render_sidebar()  # last, so its usage counter reflects this run's analysis


main()
