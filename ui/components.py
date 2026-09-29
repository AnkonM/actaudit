"""ActAudit design system, shared by every tab (blueprint §8 "As shipped", §15).

Keeps the existing look: native Streamlit elements themed in .streamlit/config.toml,
plus one marked CSS block used only by the verdict banner. Everything new extends
these pieces (captions, badges, alerts, containers) rather than restyling.

Only fixed template strings ever go into st.html. User-derived text shown as Markdown
(repository names, dataset names and values, model output) goes through md_escape().
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from urllib.parse import quote

import streamlit as st

import pipeline
from ui import state

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



# --- Shared copy -------------------------------------------------------------------

NOTICE = (
    "**Educational decision-support tool implementing a simplified subset of the EU AI "
    "Act. Not legal advice or a compliance certification.**"
)
# Cited by document only: paragraph numbers are not yet verified against the primary text.
UNESCO_REF = "UNESCO Recommendation on the Ethics of AI (2021)"
PROJECT_HEURISTIC_BADGE = ":gray-badge[project heuristic]"


# --- Text helpers ------------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def md_escape(text: Any) -> str:
    """Render arbitrary text literally inside Markdown (no links, emphasis, directives
    such as :red[...], LaTeX or HTML). Newlines become spaces."""
    return _MD_SPECIAL.sub(r"\\\1", " ".join(str(text).split()))


def value_str(value: Any) -> str:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return "[" + ", ".join(value_str(v) for v in value) + "]"
    return str(value)


def quote_evidence(name: str, snippet: str) -> None:
    st.markdown(f"> **{name}** — “{md_escape(snippet)}”")


def threshold_note(*keys: str) -> None:
    """Show the thresholds a result uses, right next to it (blueprint §15.1)."""
    for key in keys:
        t = pipeline.config.THRESHOLDS[key]
        shown = f"{t.value:g}" if isinstance(t.value, float) else f"{t.value:,}"
        st.caption(f":material/tune: **{t.label}: {shown}** — {t.meaning} "
                   f"Source: {t.source}.")


def tier_badge(tier: str) -> None:
    """Native, theme-aware tier badge for compact places (case cards, tables)."""
    colour = {"Prohibited": "red", "High-Risk": "red", "Limited-Risk": "orange",
              "Minimal-Risk": "green", "Out of scope": "gray"}[tier]
    st.badge(tier, icon=TIER_STYLES[tier].icon, color=colour)


# --- Tab frame ------------------------------------------------------------------------

def tab_intro(caption: str, blurb: str) -> None:
    """The experiment title (verbatim course wording) and one sentence on the tab."""
    st.caption(caption)
    st.markdown(blurb)


def loaded_line() -> None:
    """'Currently loaded' line under the header, visible from every tab."""
    result = state.analysis()
    ds = state.dataset()
    if result is None:
        system = "none"
    else:
        source = st.session_state.analysis_source or ""
        system = f"**{md_escape(result.source_label)}**" + (f" ({md_escape(source)})" if source else "")
    data = "none" if ds is None else f"**{md_escape(ds.name)}**"
    st.caption(f":material/inventory_2: Currently loaded — System: {system} · Dataset: {data}")


# --- Loading analyses from examples ------------------------------------------------------

STATUS_HELP = {
    "not_recorded": "Not recorded yet.",
    "older_schema": "Recorded with an older schema: the newer fields show default values.",
}


def example_buttons(key: str, examples: list[tuple[str, str]], source: str) -> None:
    """One button per recorded example; unrecorded ones are shown disabled."""
    with st.container(horizontal=True, gap="small"):
        for label, stem in examples:
            status = pipeline.example_status(stem)
            if status == "not_recorded":
                st.button(label, key=f"{key}_{stem}", icon=":material/hourglass_empty:",
                          disabled=True, help=STATUS_HELP["not_recorded"])
                continue
            if st.button(label, key=f"{key}_{stem}", icon=":material/upload_file:",
                         help=STATUS_HELP.get(status)):
                try:
                    state.set_analysis(pipeline.load_example(stem), "fixture", f"{source} example")
                except Exception:  # a broken fixture must not crash the page
                    st.warning("That example couldn't be loaded.", icon=":material/error:")


def quick_pick_examples() -> list[tuple[str, str]]:
    return list(pipeline.QUICK_PICKS)


def require_analysis(key: str, examples: list[tuple[str, str]] | None = None,
                     source: str = "Quick-pick") -> Any:
    """Top of every analysis-reading section: the loaded system, or an empty state.

    With nothing loaded: a short prompt pointing to Tab 1 plus this tab's example
    selector, so every tab can be demoed on its own. Returns the result or None.
    """
    examples = examples if examples is not None else quick_pick_examples()
    result = state.analysis()
    if result is None:
        st.info("No system is loaded yet. Run an audit in **Tab 1 · System Audit**, or load "
                "an example here (recorded results, no API call).", icon=":material/info:")
        example_buttons(key, examples, source)
        return state.analysis()  # set if a button was just clicked
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.caption(f":material/description: Analysing **{md_escape(result.source_label)}** — "
                   f"{TIER_STYLES[result.classification.tier.value].label.lower()}")
        with st.popover("Load another example", icon=":material/swap_horiz:"):
            example_buttons(f"{key}_pop", examples, source)
    return state.analysis()


# --- Principle cards (Tabs 1 and 6) ----------------------------------------------------

def _render_flags(flags, empty_text: str) -> None:
    if not flags:
        st.caption(empty_text)
    for flag in flags:
        with st.container(border=True):
            st.markdown(f"**{flag.ieee}** :blue-badge[{flag.ieee_ref}]")
            st.markdown(f"**{flag.unesco}** :gray-badge[{UNESCO_REF}]")
            st.markdown(flag.explanation)
            for name, snippet in flag.evidence.items():
                quote_evidence(name, snippet)


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




def safe_section(title: str, render: Callable[[], None]) -> None:
    """Run one section; on an unexpected error show a friendly message, never a trace."""
    try:
        render()
    except Exception as exc:  # noqa: BLE001 - the UI must never show a stack trace
        st.warning(f"This section couldn't be shown ({type(exc).__name__}). The rest of the "
                   "page still works.", title=f"{title}: something went wrong",
                   icon=":material/error:")
