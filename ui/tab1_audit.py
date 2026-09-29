"""Tab 1 · System Audit (Experiment 1). Everything the single-page app did before the
experiment tabs, unchanged, plus an ethical analysis of affected parties and harms.

Live analyses write the shared current_analysis, so every other tab can use them.
"""
import os

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

import pipeline
from ui import state
from ui.components import (
    PROJECT_HEURISTIC_BADGE,
    TIER_STYLES,
    md_escape,
    quote_evidence,
    render_principles,
    value_str,
    verdict_banner_html,
)

LIVE_CAP = 5  # live analyses per session on the shared key (cache hits don't count)
CACHE_TTL = "24h"

EXPLAINER = (
    "An LLM only *extracts* observable facts from the documentation; it never judges "
    "risk. A fixed, deterministic rule table then decides the tier, and every result "
    "shows exactly which rule fired and why."
)
STEPS = [
    (":material/manage_search:", "1 · Extract facts",
     "An LLM reads the README or text and fills a fixed set of factual fields, quoting evidence."),
    (":material/rule:", "2 · Apply rule table",
     "Ordered rules, first match wins, map those facts to an EU AI Act tier. No LLM involved."),
    (":material/fact_check:", "3 · Explain the tier",
     "The fired rule, its provision and UNESCO/IEEE principle flags are shown with their evidence."),
]

# §8.1: one friendly, specific title and icon per failure type; the exception's own
# (already actionable) message is the body. Most specific classes first.
QUICK_PICK_HINT = "The examples under **Try an example** still work — they need no API call."
ERROR_STYLES: list[tuple[type[Exception], str, str]] = [
    (pipeline.InvalidRepoURLError, "That doesn't look like a GitHub repository URL", ":material/link_off:"),
    (pipeline.RepoNotFoundError, "Repository not found", ":material/search_off:"),
    (pipeline.ReadmeNotFoundError, "No README found", ":material/description:"),
    (pipeline.RateLimitedError, "GitHub is rate-limiting requests", ":material/hourglass_top:"),
    (pipeline.NetworkError, "Couldn't reach GitHub", ":material/wifi_off:"),
    (pipeline.EmptyInputError, "Nothing to analyze", ":material/edit_note:"),
    (pipeline.InvalidAPIKeyError, "The Gemini API key was rejected", ":material/key_off:"),
    (pipeline.AllModelsUnavailableError, "All Gemini models are out of quota or busy", ":material/cloud_off:"),  # retitled in _set_error
    (pipeline.ExtractionAPIError, "The Gemini API is unavailable", ":material/cloud_off:"),
    (pipeline.MalformedExtractionError, "The model returned unusable output", ":material/report:"),
]
POINT_TO_QUICK_PICKS = (pipeline.ExtractionAPIError,)  # includes the subclasses above
CATCH_ALL = ("Something went wrong", ":material/error:")

ORIGIN_TEXT = {
    "fixture": "recorded example (no live API call)",
    "cached": "cached result (no new API call)",
    "live": "live analysis",
}


# --- Actions ---------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL, max_entries=256, show_spinner=False)
def _cached_analysis(kind: str, value: str, _api_key: str | None, _misses: list) -> "pipeline.AnalysisResult":
    """Cached on (kind, value) only. `_`-prefixed arguments are excluded from the cache
    key and never stored, so a visitor's own key is not part of any cache entry."""
    _misses.append(1)  # runs only on a cache miss
    if kind == "github":
        return pipeline.analyze_github(value, api_key=_api_key)
    return pipeline.analyze_text(value, api_key=_api_key)


@st.cache_data(show_spinner=False)
def _quick_pick_tiers() -> dict[str, str | None]:
    """Tier of each recorded quick-pick, None if not recorded yet (static fixtures)."""
    return {
        label: (
            pipeline.analyze_quick_pick(label).classification.tier.value
            if pipeline.quick_pick_status(label) != "not_recorded" else None
        )
        for label in pipeline.quick_pick_labels()
    }


def _set_error(exc: Exception, own_key_used: bool = False) -> None:
    if isinstance(exc, pipeline.AllModelsUnavailableError) and not exc.quota_exhausted:
        # Only overload/deadline errors: say so, rather than implying quota ran out.
        st.session_state.error = (
            "Gemini is overloaded right now",
            f"{exc} {QUICK_PICK_HINT}",
            ":material/hourglass_top:",
        )
        return
    for cls, title, icon in ERROR_STYLES:
        if isinstance(exc, cls):
            message = str(exc)
            if isinstance(exc, pipeline.InvalidAPIKeyError) and own_key_used:
                message = (f"{message} This is the key entered in the sidebar: correct it, or "
                           "clear it to use the demo's shared key.")
            if isinstance(exc, POINT_TO_QUICK_PICKS):
                message = f"{message} {QUICK_PICK_HINT}"
            st.session_state.error = (title, message, icon)
            return
    title, icon = CATCH_ALL
    st.session_state.error = (
        title, f"An unexpected error occurred ({type(exc).__name__}). Please try again.", icon,
    )


def server_key() -> str | None:
    """The shared Gemini key: the platform's secrets first (st.secrets), then the
    environment (a local .env). Never shown, logged or cached."""
    try:
        key = st.secrets.get("GEMINI_API_KEY")
    except StreamlitSecretNotFoundError:  # no secrets.toml, e.g. local development
        key = None
    return (key or os.getenv("GEMINI_API_KEY") or "").strip() or None


def run_live(kind: str, raw_value: str) -> None:
    state.clear_analysis()
    own_key = (st.session_state.get("byo_key") or "").strip() or None
    shared_key = server_key()
    if own_key is None and shared_key is None:
        st.session_state.error = (
            "Live analysis isn't set up on this deployment",
            "No shared Gemini API key is configured. Add your own key in the sidebar to "
            "analyze your own input, or use the examples under **Try an example**, which "
            "need no key.",
            ":material/key_off:",
        )
        return
    used = st.session_state.live_count
    if own_key is None and used >= LIVE_CAP:
        st.session_state.error = (
            "Live analysis limit reached for this session",
            f"This public demo allows {LIVE_CAP} live analyses per session to protect its "
            "shared API quota. The examples under **Try an example** work without limits, "
            "or add your own Gemini API key in the sidebar to keep analyzing.",
            ":material/lock_clock:",
        )
        return
    value = raw_value.strip() if kind == "github" else pipeline.clean_pasted_text(raw_value or "")
    misses: list = []
    try:
        with st.spinner("Fetching and analyzing… this can take a few seconds."):
            result = _cached_analysis(kind, value, _api_key=own_key or shared_key, _misses=misses)
    except Exception as exc:  # never show a stack trace in the UI
        _set_error(exc, own_key_used=own_key is not None)
        return
    state.set_analysis(result, "live" if misses else "cached", "Tab 1 live audit")
    if misses and own_key is None:
        st.session_state.live_count = used + 1


def run_quick_pick(label: str) -> None:
    state.clear_analysis()
    try:
        state.set_analysis(pipeline.analyze_quick_pick(label), "fixture", "Tab 1 quick-pick")
    except Exception as exc:
        _set_error(exc)


# --- Rendering -----------------------------------------------------------------------

def render_input() -> None:
    with st.container(border=True, key="input_card"):
        mode = st.segmented_control(
            "Input type", ["GitHub URL", "Paste text"], default="GitHub URL",
            required=True, key="input_mode", label_visibility="collapsed",
        )
        if mode == "GitHub URL":
            with st.container(horizontal=True, vertical_alignment="bottom"):
                url = st.text_input("Public GitHub repository URL",
                                    placeholder="https://github.com/owner/repo")
                clicked = st.button("Analyze", type="primary", icon=":material/search:",
                                    key="analyze_url")
            if clicked:
                run_live("github", url)
        else:
            text = st.text_area("Documentation text (README, model card, product description…)",
                                height=110)
            if st.button("Analyze", type="primary", icon=":material/search:", key="analyze_text"):
                run_live("text", text)

        st.markdown("**Try an example** :small[— recorded results, no network or API quota needed]")
        tiers = _quick_pick_tiers()
        with st.container(horizontal=True, gap="small"):
            for label in pipeline.quick_pick_labels():
                tier = tiers[label]
                if tier is None:  # fixture not recorded yet (scripts/record_all.py)
                    st.button(label, key=f"qp_{label}", icon=":material/hourglass_empty:",
                              disabled=True, help="Not recorded yet.")
                elif st.button(label, key=f"qp_{label}", icon=TIER_STYLES[tier].icon):
                    run_quick_pick(label)


def render_error() -> None:
    if st.session_state.error is not None:
        title, message, icon = st.session_state.error
        st.warning(message, title=title, icon=icon)


def render_how_it_works(expanded: bool) -> None:
    with st.expander("How ActAudit works", expanded=expanded, icon=":material/account_tree:"):
        st.markdown(EXPLAINER)
        for col, (icon, heading, body) in zip(st.columns(3), STEPS):
            with col.container(border=True, height="stretch"):
                st.markdown(f"{icon} **{heading}**")
                st.caption(body)


def render_verdict(result) -> None:
    c = result.classification
    facts = result.extraction.facts
    origin = st.session_state.analysis_origin
    with st.container(border=True, key="verdict"):
        hero, why = st.columns([5, 6], gap="large")
        with hero:
            st.html(verdict_banner_html(c.tier.value))
            with st.container(horizontal=True, gap="small"):
                if origin == "fixture":
                    st.badge("Recorded example", icon=":material/history:", color="blue")
                elif origin == "cached":
                    st.badge("Cached result", icon=":material/bolt:", color="blue")
                else:
                    st.badge("Live analysis", icon=":material/bolt:", color="blue")
                if facts.extraction_confidence.value == "low":
                    st.badge("Low extraction confidence", icon=":material/warning:", color="orange")
                if result.llm_input_truncated:
                    st.badge("Input truncated", icon=":material/content_cut:", color="gray")
                if result.schema_version < pipeline.SCHEMA_VERSION:
                    st.badge("Recorded with an older schema", icon=":material/history_toggle_off:",
                             color="gray",
                             help="Recorded before the schema v2 fields existed; those fields "
                             "show their absent-signal defaults, not extracted values.")
            st.caption(f"Source: **{md_escape(result.source_label)}** · {ORIGIN_TEXT[origin or 'live']}")
            st.caption(f"Extracted by **{result.extraction.model}**")
            if result.extraction.model != pipeline.MODEL_CHAIN[0]:
                st.caption(
                    f":orange[:material/warning: A fallback model answered] — the primary, "
                    f"{pipeline.MODEL_CHAIN[0]}, was unavailable. Fallback models can extract "
                    "facts less accurately; check the extracted facts."
                )
        with why:
            st.subheader("Why this tier")
            # §8: justification and provision always on two separate lines.
            st.markdown(c.justification)
            st.markdown(f"**Provision:** {c.provision}")
            st.caption(":material/rule: Decided by the first matching rule — see the **Rule table** tab.")
            for name, snippet in c.evidence.items():
                quote_evidence(name, snippet)
            for pointer in pipeline.harms.related_tabs(facts, c.tier):
                st.caption(f":material/arrow_forward: {pointer.text}")


def render_facts(result) -> None:
    facts = result.extraction.facts
    if facts.extraction_confidence.value == "low":
        st.warning(
            "The documentation contained little relevant information, so this "
            "classification rests on incomplete documentation — itself a finding worth noting.",
            title="Low extraction confidence", icon=":material/warning:",
        )
    if result.schema_version < pipeline.SCHEMA_VERSION:
        st.caption(":material/history_toggle_off: Recorded with an older schema: fields added "
                   "later (target, synthetic media, military use, robustness, fail-safe) show "
                   "their default values, not extracted ones.")
    rows = [
        {
            "Field": name,
            "Value": value_str(getattr(facts, name)),
            "Evidence": facts.evidence_snippets.get(name, ""),
        }
        for name in pipeline.DISPLAY_ORDER
    ]
    st.dataframe(
        rows,
        hide_index=True,
        column_config={
            "Field": st.column_config.TextColumn("Field", width="medium"),
            "Value": st.column_config.TextColumn("Value", width="medium"),
            "Evidence": st.column_config.TextColumn("Evidence (from the source)", width="large"),
        },
    )


def render_source(result) -> None:
    if result.readme is not None:
        st.caption(f"Fetched from {md_escape(result.readme.source_url)}")
    if result.llm_input_truncated:
        st.info(
            f"Model saw a truncated copy ({pipeline.MAX_INPUT_CHARS:,} of "
            f"{len(result.source_text):,} characters). The full original is shown below.",
            icon=":material/content_cut:",
        )
    st.code(result.source_text, language="markdown", wrap_lines=True, height=420)


def render_rule_table(result) -> None:
    st.caption(
        "Rules are checked top to bottom and the first match decides the tier. "
        "The row marked **Decided** is the one that decided this result."
    )
    fired = result.classification.rule_number
    table = pipeline.rule_table()
    # st.table wraps long conditions (st.dataframe truncates them) and renders Markdown.
    # Condition text is fixed rule-table data, never user input.
    st.table(
        {
            "Order": [rule["number"] for rule in table],
            # Plain text, not code: the code font's ligatures would draw "==" as one glyph.
            "Applies when": [rule["condition"] for rule in table],
            "Tier": [rule["tier"] for rule in table],
            "Provision": [rule["provision"] for rule in table],
            "This result": [
                ":blue-badge[:material/check_circle: Decided]" if rule["number"] == fired else ""
                for rule in table
            ],
        },
        hide_index=True,
        border="horizontal",
    )


def render_ethical_analysis(result) -> None:
    facts = result.extraction.facts
    st.subheader("Ethical analysis")
    st.caption(
        f"{PROJECT_HEURISTIC_BADGE} Who the system affects and which kinds of harm its stated "
        "facts point to, from a fixed rule table (a project heuristic, not derived from a "
        "specific Act provision). No LLM judges harm; each item names the facts behind it."
    )
    parties_col, harms_col = st.columns([2, 3], gap="large")
    with parties_col:
        st.markdown("##### Affected parties")
        for party in pipeline.harms.affected_parties(facts):
            with st.container(border=True):
                st.markdown(party.party)
                st.caption(f"From `{party.reason}`")
    with harms_col:
        st.markdown("##### Harm categories")
        grouped = pipeline.harms.findings_by_category(facts)
        quiet = [c for c, findings in grouped.items() if not findings]
        if quiet:
            st.caption(":material/check: Not indicated by the extracted facts: " + ", ".join(quiet) + ".")
        for category, findings in grouped.items():
            if not findings:
                continue
            meaning = pipeline.harms.CATEGORY_MEANING[category]
            with st.container(border=True):
                st.markdown(f"**{category}** :orange-badge[{len(findings)} indicated]")
                st.caption(meaning[0].upper() + meaning[1:] + ".")
                for finding in findings:
                    st.markdown(f"- {finding.harm}")
                    triggers = ", ".join(f"`{n}={v}`" for n, v in finding.fired_fields)
                    st.caption(f"Triggered by {triggers}. Rationale: {finding.rationale}.")
                    for name, snippet in finding.evidence.items():
                        quote_evidence(name, snippet)


def render_result(result) -> None:
    render_verdict(result)
    principles_tab, facts_tab, rules_tab, source_tab = st.tabs([
        f":material/verified_user: Principles ({len(result.principles)})",
        ":material/table_rows: Extracted facts",
        ":material/rule: Rule table",
        ":material/description: Raw source",
    ])
    with principles_tab:
        render_principles(result)
    with facts_tab:
        render_facts(result)
    with rules_tab:
        render_rule_table(result)
    with source_tab:
        render_source(result)
    render_ethical_analysis(result)


def render() -> None:
    render_input()  # may run an analysis and update session state
    render_error()
    result = state.analysis()
    if result is not None:
        render_result(result)
    render_how_it_works(expanded=result is None)
