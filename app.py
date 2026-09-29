"""ActAudit Streamlit dashboard (Blueprint Section 8). UI only.

pipeline.py is the only backend interface: every result, error type, quick-pick and
model setting comes through it. Run with: streamlit run app.py

Styling is native (theme in .streamlit/config.toml) except for one marked CSS block
used only by the verdict banner.
"""
import os
from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError

import pipeline

load_dotenv()  # local development only; a missing .env is fine

LIVE_CAP = 5  # live analyses per session on the shared key (cache hits don't count)
CACHE_TTL = "24h"


# --- Tier presentation -------------------------------------------------------
# Only these fixed strings are ever placed in HTML. Nothing from a README, the model
# or the user is interpolated into unsafe HTML.

# Material Icons SVG paths (Apache 2.0) for the banner icon. Streamlit's HTML
# sanitizer strips inline <svg>, so each path becomes a CSS mask (see VERDICT CSS).
_SVG_BLOCK = (
    "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zM4 12c0-4.42 "
    "3.58-8 8-8 1.85 0 3.55.63 4.9 1.69L5.69 16.9C4.63 15.55 4 13.85 4 12zm8 8c-1.85 "
    "0-3.55-.63-4.9-1.69L18.31 7.1C19.37 8.45 20 10.15 20 12c0 4.42-3.58 8-8 8z"
)
_SVG_WARNING = "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"
_SVG_INFO = (
    "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"
)
_SVG_REMOVE = "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11H7v-2h10v2z"
_SVG_CHECK = (
    "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 "
    "1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"
)


@dataclass(frozen=True)
class TierStyle:
    css_class: str  # verdict banner modifier
    svg_path: str  # banner icon, drawn as a CSS mask
    icon: str  # Material Symbol for native elements (quick-picks)
    label: str  # banner headline; always contains the tier name as text
    subtitle: str


TIER_STYLES: dict[str, TierStyle] = {
    "Out of scope": TierStyle(
        "out-of-scope", _SVG_REMOVE, ":material/do_not_disturb_on:",
        "Outside the AI Act's scope", "Military, defence or national-security use: Art. 2(3)",
    ),
    "Prohibited": TierStyle(
        "prohibited", _SVG_BLOCK, ":material/block:",
        "Prohibited practice", "Banned under EU AI Act Art. 5",
    ),
    "High-Risk": TierStyle(
        "high", _SVG_WARNING, ":material/warning:",
        "High-risk system", "Allowed, with strict obligations",
    ),
    "Limited-Risk": TierStyle(
        "limited", _SVG_INFO, ":material/info:",
        "Limited-risk system", "Transparency duties may apply",
    ),
    "Minimal-Risk": TierStyle(
        "minimal", _SVG_CHECK, ":material/check_circle:",
        "Minimal-risk system", "No specific obligations identified",
    ),
}

# ============================================================================
# VERDICT CSS — the app's only custom CSS. Used solely by the verdict banner:
# native elements can't draw a solid, theme-aware coloured banner.
# Colours: light-dark(<light>, <dark>) follows the color-scheme Streamlit sets
# for the active theme; the plain declaration before each is a fallback.
# Text/fill contrast, WCAG AA (>= 4.5:1), computed:
#   Prohibited  light #FFFFFF on #7F1D1D 10.02   dark #FECACA on #450A0A 11.16
#   High-Risk   light #FFFFFF on #B91C1C  6.47   dark #FFFFFF on #991B1B  8.31
#   Limited     light #422006 on #FBBF24  8.73   dark #1C1300 on #F59E0B  8.56
#   Minimal     light #FFFFFF on #15803D  5.02   dark #F0FDF4 on #166534  6.81
#   Out of scope light #FFFFFF on #4B5563 7.56   dark #F3F4F6 on #374151  9.37
#     (neutral grey: the Act doesn't apply, so no risk colour; its dark fill sits
#      close to the page, so the #9CA3AF border (7.43:1 on the page) marks the edge)
# Borders keep the banner's edge visible (>= 5:1 against the page) where a fill
# sits close to the page background.
# ============================================================================
VERDICT_CSS = """
<style>
.aa-verdict {
  display: flex; align-items: center; gap: 1rem;
  padding: 1.1rem 1.35rem; border-radius: 0.6rem;
  border: 3px solid; line-height: 1.2;
}
.aa-verdict .aa-icon {
  width: 2.6rem; height: 2.6rem; flex: none; background-color: currentColor;
  -webkit-mask: var(--aa-icon) center / contain no-repeat;
  mask: var(--aa-icon) center / contain no-repeat;
}
.aa-verdict .aa-kicker { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em;
                         text-transform: uppercase; opacity: 0.9; }
.aa-verdict .aa-label { font-size: 1.7rem; font-weight: 800; margin: 0.15rem 0 0.2rem; }
.aa-verdict .aa-sub { font-size: 0.95rem; font-weight: 500; }
.aa-verdict--prohibited {
  background: #7F1D1D; color: #FFFFFF; border-color: #450A0A;
  background: light-dark(#7F1D1D, #450A0A); color: light-dark(#FFFFFF, #FECACA);
  border-color: light-dark(#450A0A, #F87171);
  border-style: double; border-width: 6px;
}
.aa-verdict--high {
  background: #B91C1C; color: #FFFFFF; border-color: #7F1D1D;
  background: light-dark(#B91C1C, #991B1B); color: #FFFFFF;
  border-color: light-dark(#7F1D1D, #F87171);
}
.aa-verdict--limited {
  background: #FBBF24; color: #422006; border-color: #B45309;
  background: light-dark(#FBBF24, #F59E0B); color: light-dark(#422006, #1C1300);
  border-color: light-dark(#B45309, #FCD34D);
}
.aa-verdict--out-of-scope {
  background: #4B5563; color: #FFFFFF; border-color: #1F2937;
  background: light-dark(#4B5563, #374151); color: light-dark(#FFFFFF, #F3F4F6);
  border-color: light-dark(#1F2937, #9CA3AF);
}
.aa-verdict--minimal {
  background: #15803D; color: #FFFFFF; border-color: #14532D;
  background: light-dark(#15803D, #166534); color: light-dark(#FFFFFF, #F0FDF4);
  border-color: light-dark(#14532D, #4ADE80);
}
__ICON_RULES__
</style>
"""


def _icon_rule(css_class: str, svg_path: str) -> str:
    # Percent-encoded: a raw "<svg" inside <style> makes the HTML sanitizer drop the
    # whole style block.
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='{svg_path}'/></svg>"
    return f'.aa-verdict--{css_class} {{ --aa-icon: url("data:image/svg+xml,{quote(svg)}"); }}'


VERDICT_CSS = VERDICT_CSS.replace(
    "__ICON_RULES__",
    "\n".join(_icon_rule(t.css_class, t.svg_path) for t in TIER_STYLES.values()),
)
# ============================================================================


def verdict_banner_html(tier: str) -> str:
    """Banner markup built only from the fixed TIER_STYLES entry for `tier`."""
    style = TIER_STYLES[tier]  # KeyError on anything that isn't a known tier
    return (
        f'{VERDICT_CSS}<div class="aa-verdict aa-verdict--{style.css_class}" role="status" '
        f'aria-label="Risk tier: {tier}">'
        f'<span class="aa-icon" aria-hidden="true"></span>'
        f'<div><div class="aa-kicker">EU AI Act tier</div>'
        f'<div class="aa-label">{style.label}</div>'
        f'<div class="aa-sub">{style.subtitle}</div></div></div>'
    )


# --- Copy ----------------------------------------------------------------------

NOTICE = (
    "**Educational decision-support tool implementing a simplified subset of the EU AI "
    "Act. Not legal advice or a compliance certification.**"
)
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
# Cited by document only: paragraph numbers are not yet verified against the primary text.
UNESCO_REF = "UNESCO Recommendation on the Ethics of AI (2021)"

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


# --- State and actions ---------------------------------------------------------

def init_state() -> None:
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("origin", None)  # "live" | "cached" | "fixture"
    st.session_state.setdefault("error", None)  # (title, message, icon)
    st.session_state.setdefault("live_count", 0)


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


def _clear_output() -> None:
    st.session_state.result = None
    st.session_state.origin = None
    st.session_state.error = None


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
    _clear_output()
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
    st.session_state.result = result
    st.session_state.origin = "live" if misses else "cached"
    if misses and own_key is None:
        st.session_state.live_count = used + 1


def run_quick_pick(label: str) -> None:
    _clear_output()
    try:
        st.session_state.result = pipeline.analyze_quick_pick(label)
        st.session_state.origin = "fixture"
    except Exception as exc:
        _set_error(exc)


# --- Rendering -----------------------------------------------------------------

def _value_str(value) -> str:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return "[" + ", ".join(_value_str(v) for v in value) + "]"
    return str(value)


def _quote(name: str, snippet: str) -> None:
    st.markdown(f"> **{name}** — “{snippet}”")


def render_header() -> None:
    st.title("ActAudit", icon=":material/balance:")
    st.info(NOTICE, icon=":material/school:")


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
    with st.container(border=True, key="verdict"):
        hero, why = st.columns([5, 6], gap="large")
        with hero:
            st.html(verdict_banner_html(c.tier.value))
            origin = st.session_state.origin
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
            origin_text = {
                "fixture": "recorded example (no live API call)",
                "cached": "cached result (no new API call)",
                "live": "live analysis",
            }[origin or "live"]
            st.caption(f"Source: **{result.source_label}** · {origin_text}")
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
                _quote(name, snippet)


def _render_flags(flags, empty_text: str) -> None:
    if not flags:
        st.caption(empty_text)
    for flag in flags:
        with st.container(border=True):
            st.markdown(f"**{flag.ieee}** :blue-badge[{flag.ieee_ref}]")
            st.markdown(f"**{flag.unesco}** :gray-badge[{UNESCO_REF}]")
            st.markdown(flag.explanation)
            for name, snippet in flag.evidence.items():
                _quote(name, snippet)


def render_principles(result) -> None:
    if not result.principles:
        st.success("No UNESCO/IEEE principle concerns were flagged.", icon=":material/verified_user:")
        return
    fact_based = [f for f in result.principles if not f.documentation_gap]
    gaps = [f for f in result.principles if f.documentation_gap]
    facts_col, gaps_col = st.columns(2, gap="large")
    with facts_col:
        st.markdown("##### Flagged from stated facts")
        _render_flags(fact_based, "None — no principle concern follows from a stated fact.")
    with gaps_col:
        st.markdown("##### Documentation gaps")
        st.caption("Raised because the documentation doesn't say something, not because of a stated fact.")
        _render_flags(gaps, "None.")


def render_facts(result) -> None:
    facts = result.extraction.facts
    if facts.extraction_confidence.value == "low":
        st.warning(
            "The documentation contained little relevant information, so this "
            "classification rests on incomplete documentation — itself a finding worth noting.",
            title="Low extraction confidence", icon=":material/warning:",
        )
    rows = [
        {
            "Field": name,
            "Value": _value_str(getattr(facts, name)),
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
        st.caption(f"Fetched from {result.readme.source_url}")
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
    # st.table wraps long conditions (st.dataframe truncates them) and renders Markdown.
    # Condition text is fixed rule-table data, never user input.
    st.table(
        {
            "Order": [rule["number"] for rule in pipeline.rule_table()],
            # Plain text, not code: the code font's ligatures would draw "==" as one glyph.
            "Applies when": [rule["condition"] for rule in pipeline.rule_table()],
            "Tier": [rule["tier"] for rule in pipeline.rule_table()],
            "Provision": [rule["provision"] for rule in pipeline.rule_table()],
            "This result": [
                ":blue-badge[:material/check_circle: Decided]" if rule["number"] == fired else ""
                for rule in pipeline.rule_table()
            ],
        },
        hide_index=True,
        border="horizontal",
    )


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


# --- Page ----------------------------------------------------------------------

st.set_page_config(page_title="ActAudit", page_icon=":material/balance:", layout="wide")
init_state()

render_header()
render_input()  # may run an analysis and update session state
render_error()

result = st.session_state.result
if result is not None:
    render_result(result)
render_how_it_works(expanded=result is None)
render_sidebar()  # last, so its usage counter reflects this run's analysis
