"""Tab 7A · Autonomy and scope (Experiment 7): the Rule 0 scope result, the system's
documented autonomy, and documentation checks against Art. 14 (human oversight) and
Art. 15 (accuracy, robustness and cybersecurity).

Article text verified against the Official Journal text of Regulation (EU) 2024/1689:
- Art. 2(3): the Regulation does not apply to AI systems placed on the market, put into
  service or used exclusively for military, defence or national-security purposes.
- Art. 14(1): high-risk systems shall be designed so they can be effectively overseen by
  natural persons; 14(4)(d)–(e): the overseer can disregard, override or reverse the
  output, and interrupt the system through a 'stop' button or similar procedure that
  brings it to a halt in a safe state.
- Art. 15(1): an appropriate level of accuracy, robustness and cybersecurity; 15(3):
  accuracy levels and metrics declared in the instructions of use; 15(4): robustness
  "may be achieved through technical redundancy solutions, which may include backup or
  fail-safe plans"; 15(5): resilience against attempts to exploit vulnerabilities,
  including adversarial examples.
"""
from dataclasses import dataclass

from rules import RiskTier
from schema import DecisionAutonomy, ExtractedFacts

SCOPE_CITATION = "EU AI Act Art. 2(3)"
MEANINGFUL_HUMAN_CONTROL = (
    "Context note (not a legal citation): for military and security uses, international "
    "discussions on autonomous weapons centre on keeping meaningful human control over "
    "the selection and engagement of targets. The AI Act leaves these uses out of scope, "
    "so ActAudit can only report what the documentation says about autonomy and oversight."
)


@dataclass(frozen=True)
class ScopeResult:
    out_of_scope: bool
    text: str
    citation: str
    citation_verified: bool


def scope_result(facts: ExtractedFacts) -> ScopeResult:
    if facts.military_defence_use:
        return ScopeResult(True, "The documentation describes exclusively military, defence or "
                           "national-security use, so the EU AI Act does not apply (Rule 0). "
                           "The principle flags and the checks below still describe the system.",
                           SCOPE_CITATION, True)
    return ScopeResult(False, "No exclusively military, defence or national-security use was "
                       "extracted, so the Art. 2(3) exclusion does not apply.", SCOPE_CITATION, True)


AUTONOMY_TEXT = {
    DecisionAutonomy.HUMAN_IN_LOOP: "A human approves each decision before it takes effect.",
    DecisionAutonomy.HUMAN_ON_LOOP: "A human can monitor and override, but doesn't approve "
                                    "each decision (also the default when the documentation is silent).",
    DecisionAutonomy.FULLY_AUTONOMOUS: "Decisions are described as taken with no human review.",
}


@dataclass(frozen=True)
class DocCheck:
    provision: str
    requirement: str
    field: str
    documented: bool
    evidence: str | None
    status: str  # "Required for high-risk systems" | "Good practice" | "Not required"
    citation_verified: bool = True


_CHECKS = [
    ("EU AI Act Art. 14(1), 14(4)(d)", "Human oversight: people can oversee the system and "
     "disregard, override or reverse its output.", "human_oversight_mentioned"),
    ("EU AI Act Art. 15(1), 15(3), 15(5)", "Accuracy, robustness and cybersecurity are "
     "evaluated and declared, including resilience to adversarial inputs.",
     "robustness_testing_mentioned"),
    ("EU AI Act Art. 15(4), 14(4)(e)", "Fail-safe behaviour: backup or fail-safe plans, and a "
     "way to stop the system in a safe state.", "failsafe_mentioned"),
]


def documentation_checks(facts: ExtractedFacts, tier: RiskTier) -> list[DocCheck]:
    if tier == RiskTier.OUT_OF_SCOPE:
        status = "Not required (the Act doesn't apply)"
    elif tier == RiskTier.HIGH_RISK:
        status = "Required for high-risk systems"
    elif tier == RiskTier.PROHIBITED:
        status = "Not applicable (prohibited practice)"
    else:
        status = "Good practice (not required for this tier)"
    return [
        DocCheck(provision, requirement, field, getattr(facts, field),
                 facts.evidence_snippets.get(field), status)
        for provision, requirement, field in _CHECKS
    ]


def autonomy_findings(facts: ExtractedFacts, tier: RiskTier) -> list[str]:
    """Rule-generated summary lines (the autonomy value itself is shown separately)."""
    checks = documentation_checks(facts, tier)
    missing = [c for c in checks if not c.documented]
    out = []
    if facts.decision_autonomy == DecisionAutonomy.FULLY_AUTONOMOUS and not facts.human_oversight_mentioned:
        out.append("It runs without human review and the documentation describes no way for a "
                   "person to intervene — the combination that most needs a human in control.")
    if tier == RiskTier.HIGH_RISK and missing:
        out.append(f"As a high-risk system it must meet all three checks; the documentation "
                   f"doesn't show {len(missing)} of them.")
    elif not missing:
        out.append("The documentation covers oversight, robustness testing and fail-safe behaviour.")
    return out
