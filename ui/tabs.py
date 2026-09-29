"""The eight experiment tabs: label, verbatim course caption, one-sentence blurb and
render function (blueprint §15.2). tests/test_tabs.py checks labels and captions
against the course wording, so edit them only if the course wording changes.
"""
from dataclasses import dataclass
from typing import Callable

import streamlit as st

from ui import (
    tab1_audit,
    tab2_dataset_bias,
    tab3_synthetic_media,
    tab4_proxy,
    tab5_fairness,
    tab6_impact,
    tab7_robustness,
    tab8_cases,
)
from ui.components import safe_section, tab_intro


@dataclass(frozen=True)
class TabSpec:
    label: str
    caption: str  # the experiment title, exactly as the course words it
    blurb: str  # one plain sentence on what the tab does
    render: Callable[[], None]


TABS: list[TabSpec] = [
    TabSpec(
        "1 · System Audit",
        "Experiment 1 — Ethical Analysis of AI Applications",
        "Audits a system from its README or documentation: an LLM extracts facts, fixed rules "
        "assign an EU AI Act tier, and the facts are mapped to UNESCO/IEEE principles, "
        "affected parties and harms.",
        tab1_audit.render,
    ),
    TabSpec(
        "2 · Dataset Bias",
        "Experiment 2 — Detecting Dataset Bias in AI System",
        "Checks a tabular dataset for under-represented groups, small intersectional groups, "
        "uneven missing data and unequal label rates across protected attributes.",
        tab2_dataset_bias.render,
    ),
    TabSpec(
        "3 · Synthetic Media",
        "Experiment 3 — Deepfake Vulnerability Assessment and Ethical Analysis",
        "Assesses whether the loaded system can generate synthetic media or impersonate real "
        "people, which AI Act transparency duties apply, and how exposed it is to misuse.",
        tab3_synthetic_media.render,
    ),
    TabSpec(
        "4 · Proxy Audit",
        'Experiment 4 — Auditing the "Cost-as-a-Proxy" Resource Bias',
        "Checks whether the system predicts a proxy (such as cost standing in for need) and "
        "whether a dataset's other columns can stand in for a protected attribute.",
        tab4_proxy.render,
    ),
    TabSpec(
        "5 · Fairness & Explainability",
        "Experiment 5 — Implementing AI Fairness and Explainability Dashboard",
        "Measures how a model's predictions differ across groups, and explains ActAudit's own "
        "verdict with a full rule trace and a what-if explorer.",
        tab5_fairness.render,
    ),
    TabSpec(
        "6 · Impact Assessment",
        "Experiment 6 — Operationalizing UNESCO & IEEE Frameworks via Algorithmic Impact Assessments",
        "Builds a structured algorithmic impact assessment from the loaded audit, with "
        "principle flags, an impact level, recommended actions and a downloadable report.",
        tab6_impact.render,
    ),
    TabSpec(
        "7 · Robustness & Autonomy",
        "Experiment 7 — Autonomous Target Selection and System Degradation Auditing",
        "Checks the loaded system's scope, autonomy and documented oversight, and shows how "
        "stable ActAudit's own verdicts are when its input is degraded or attacked.",
        tab7_robustness.render,
    ),
    TabSpec(
        "8 · Case Library",
        "Experiment 8 — Case Study on AI Ethics and Regulations",
        "Runs ActAudit on documented real-world AI incidents and compares its verdict with "
        "what actually happened.",
        tab8_cases.render,
    ),
]

TABS_KEY = "main_tabs"


def render_tabs() -> None:
    """Lazy tabs: only the selected tab runs (on_change="rerun" + .open), so a heavy
    tab never slows the others. Each section's unexpected errors stay inside it."""
    containers = st.tabs([t.label for t in TABS], key=TABS_KEY, on_change="rerun")
    for spec, container in zip(TABS, containers):
        if container.open:
            with container:
                tab_intro(spec.caption, spec.blurb)
                if spec.render is tab1_audit.render:
                    spec.render()  # Tab 1 handles its own errors (§8.1)
                else:
                    safe_section(spec.label, spec.render)
