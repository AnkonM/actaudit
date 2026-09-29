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
    axis = alt.Axis(format=".1~%" if percent else "~g", grid=True, gridOpacity=0.35)
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, color=series_colours(1)[0]).encode(
        y=alt.Y(f"{category}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
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


# Fill and text colour per cell state for the stability matrix (text contrast >= 4.5:1).
_STATE_COLOURS = {
    "light": {"baseline": ("#3949AB", "#FFFFFF"), "unchanged": ("#D8DCE5", "#1F2330"),
              "changed": ("#B45309", "#FFFFFF"), "malformed output": ("#C62828", "#FFFFFF"),
              "not applicable": ("#F5F7FA", "#5B6270"), "not recorded": ("#F5F7FA", "#5B6270"),
              "no baseline": ("#F5F7FA", "#5B6270")},
    "dark": {"baseline": ("#3987e5", "#0F1117"), "unchanged": ("#2E3240", "#E6E8EE"),
             "changed": ("#FBBF24", "#0F1117"), "malformed output": ("#FF6B6B", "#0F1117"),
             "not applicable": ("#1A1D27", "#9AA1AF"), "not recorded": ("#1A1D27", "#9AA1AF"),
             "no baseline": ("#1A1D27", "#9AA1AF")},
}


def state_heatmap(df: pd.DataFrame, x: str, y: str, state: str, text: str,
                  x_order: list[str], y_order: list[str]) -> None:
    """A labelled grid: every cell shows its text, colour encodes its state (legend on top)."""
    colours = _STATE_COLOURS[_mode()]
    states = [s for s in colours if s in set(df[state])]
    data = df.assign(_fill=df[state].map(lambda s: colours[s][0]), _ink=df[state].map(lambda s: colours[s][1]))
    base = alt.Chart(data).encode(
        x=alt.X(f"{x}:N", sort=x_order, title=None,
                axis=alt.Axis(labelAngle=-30, labelLimit=200, labelOverlap=False, orient="top")),
        y=alt.Y(f"{y}:N", sort=y_order, title=None, axis=alt.Axis(labelLimit=220)),
    )
    cells = base.mark_rect(cornerRadius=3, stroke="transparent", strokeWidth=2).encode(
        color=alt.Color(f"{state}:N", scale=alt.Scale(domain=states, range=[colours[s][0] for s in states]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip(f"{y}:N"), alt.Tooltip(f"{x}:N"), alt.Tooltip(f"{text}:N", title="result"),
                 alt.Tooltip(f"{state}:N")],
    )
    labels = base.mark_text(fontSize=11).encode(text=f"{text}:N", color=alt.Color("_ink:N", scale=None))
    chart = alt.layer(cells, labels).properties(height=alt.Step(34))
    st.altair_chart(chart, width="stretch")
