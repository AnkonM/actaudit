"""Chart helpers for the experiment tabs (native Altair via st.altair_chart).

Colour follows the dataviz method: categorical hues in a fixed order from the
validated reference palette, stepped separately for light and dark surfaces
(validated with the dataviz skill's validate_palette.js against this app's surfaces
#FFFFFF and #0F1117: all hard checks pass; slot 3's light step is below 3:1, so every
chart here is shown next to its data table). Thresholds are dashed, labelled rules in
neutral grey; values and labels use the theme's text colour, never a series colour.
"""
import altair as alt
import pandas as pd
import streamlit as st

_SERIES = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a"],
    "dark": ["#3987e5", "#d95926", "#199e70"],
}
_RULE = {"light": "#5B6270", "dark": "#9AA1AF"}  # the theme's grayColor per mode


def _mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # noqa: BLE001 - no browser context (tests): default to light
        return "light"


def series_colours(n: int) -> list[str]:
    return _SERIES[_mode()][:n]


def _rules(rules: list[tuple[float, str]], field: str, horizontal: bool) -> list[alt.Chart]:
    layers = []
    for value, label in rules:
        data = pd.DataFrame({field: [value], "label": [label]})
        enc = {"x": f"{field}:Q"} if horizontal else {"y": f"{field}:Q"}
        line = alt.Chart(data).mark_rule(strokeDash=[4, 3], strokeWidth=1.5,
                                         color=_RULE[_mode()]).encode(**enc)
        text = alt.Chart(data).mark_text(align="left", dx=4, dy=-6 if not horizontal else 0,
                                         baseline="bottom", color=_RULE[_mode()], fontSize=11)
        text = text.encode(**enc, text="label:N", **({"y": alt.value(2)} if horizontal else {}))
        layers += [line, text]
    return layers


def hbar(df: pd.DataFrame, category: str, value: str, value_title: str,
         rules: list[tuple[float, str]] = (), percent: bool = True,
         tooltip: list[str] | None = None, height: int | None = None) -> None:
    """One series of horizontal bars, sorted by value, with optional threshold rules."""
    fmt = ".1%" if percent else ".3f"
    axis = alt.Axis(format=".0%" if percent else "~g", grid=True, gridOpacity=0.35)
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, color=series_colours(1)[0]).encode(
        y=alt.Y(f"{category}:N", sort="-x", title=None),
        x=alt.X(f"{value}:Q", title=value_title, axis=axis),
        tooltip=tooltip or [alt.Tooltip(f"{category}:N"), alt.Tooltip(f"{value}:Q", format=fmt)],
    )
    # Height per band (alt.Step): Streamlit sizes the element to the chart's content, and
    # a fixed chart height is not honoured there, so the bands set the height instead.
    chart = alt.layer(bars, *_rules(list(rules), value, horizontal=True))
    st.altair_chart(chart.properties(height=alt.Step(height or 28)), width="stretch")


def grouped_hbar(df: pd.DataFrame, category: str, series: str, value: str, value_title: str,
                 series_order: list[str], rules: list[tuple[float, str]] = (),
                 percent: bool = True, domain: tuple[float, float] | None = None) -> None:
    """Up to three series side by side per category (fixed colour order, legend on top)."""
    colours = series_colours(len(series_order))
    fmt = ".1%" if percent else ".3f"
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y(f"{category}:N", title=None, sort=None),
        yOffset=alt.YOffset(f"{series}:N", sort=series_order),
        x=alt.X(f"{value}:Q", title=value_title,
                scale=alt.Scale(domain=list(domain)) if domain else alt.Undefined,
                axis=alt.Axis(format=".0%" if percent else "~g", grid=True, gridOpacity=0.35)),
        color=alt.Color(f"{series}:N", scale=alt.Scale(domain=series_order, range=colours),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip(f"{category}:N"), alt.Tooltip(f"{series}:N"),
                 alt.Tooltip(f"{value}:Q", format=fmt)],
    )
    chart = alt.layer(bars, *_rules(list(rules), value, horizontal=True))
    st.altair_chart(chart.properties(height=alt.Step(14 * len(series_order) + 10)), width="stretch")
