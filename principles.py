"""UNESCO / IEEE principle mapping (Blueprint Section 7).

Separate from the EU AI Act tier. Unlike RULES in rules.py this is NOT first-match:
every principle whose condition holds is flagged. A principle with several triggers
("or" in the Section 7 table) is flagged if any trigger fires, and every trigger that
fired is reported. Zero LLM involvement.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from schema import AffectedPopulation, DataSensitivity, DecisionAutonomy, ExtractedFacts


@dataclass(frozen=True)
class Trigger:
    field: str
    condition: Callable[[ExtractedFacts], bool]
    reasoning: str
    # True when the trigger fires on the documentation NOT saying something, rather
    # than on a fact it states. Shown separately in the dashboard (blueprint §7/§8).
    documentation_gap: bool = False


@dataclass(frozen=True)
class Principle:
    unesco: str
    ieee: str
    # Numbered identifier, verified against IEEE "Ethically Aligned Design", First
    # Edition, General Principles (standards.ieee.org ead1e_general_principles.pdf).
    ieee_ref: str
    triggers: tuple[Trigger, ...]


@dataclass(frozen=True)
class PrincipleFlag:
    unesco: str
    ieee: str
    ieee_ref: str
    fired_fields: tuple[tuple[str, str], ...]
    explanation: str
    evidence: dict[str, str]
    documentation_gap: bool  # every trigger that fired is a documentation gap


PRINCIPLES: list[Principle] = [
    Principle(
        unesco="Human oversight and determination",
        ieee="Accountability",
        ieee_ref="IEEE EAD General Principle 6",
        # Two independent signals: documentation silence, or an explicitly
        # fully-autonomous pipeline. Either is sufficient (Section 7 rationale).
        triggers=(
            Trigger(
                field="human_oversight_mentioned",
                condition=lambda f: not f.human_oversight_mentioned,
                reasoning="the documentation doesn't mention any human review, override or appeal mechanism",
                documentation_gap=True,
            ),
            Trigger(
                field="decision_autonomy",
                condition=lambda f: f.decision_autonomy == DecisionAutonomy.FULLY_AUTONOMOUS,
                reasoning="decisions are described as taken with no human review",
            ),
        ),
    ),
    Principle(
        unesco="Transparency and explainability",
        ieee="Transparency",
        ieee_ref="IEEE EAD General Principle 5",
        triggers=(
            Trigger(
                field="transparency_mentioned",
                condition=lambda f: not f.transparency_mentioned,
                reasoning="the documentation doesn't mention telling end users they are interacting with an AI system",
                documentation_gap=True,
            ),
        ),
    ),
    Principle(
        unesco="Fairness and non-discrimination",
        ieee="Human Rights",
        ieee_ref="IEEE EAD General Principle 1",
        triggers=(
            Trigger(
                field="affected_population",
                condition=lambda f: f.affected_population == AffectedPopulation.VULNERABLE_GROUPS,
                reasoning="the system affects vulnerable groups",
            ),
        ),
    ),
    Principle(
        unesco="Right to privacy and data protection",
        ieee="Data Agency",
        ieee_ref="IEEE EAD General Principle 3",
        triggers=(
            Trigger(
                field="data_sensitivity",
                condition=lambda f: f.data_sensitivity == DataSensitivity.SENSITIVE,
                reasoning="the system processes sensitive data (health, biometric, criminal, political, religious or union-affiliation)",
            ),
        ),
    ),
    Principle(
        unesco="Human dignity and autonomy",
        ieee="Well-being",
        ieee_ref="IEEE EAD General Principle 2",
        triggers=(
            Trigger(
                field="social_scoring",
                condition=lambda f: f.social_scoring,
                reasoning="the system scores or ranks individuals for general trustworthiness or eligibility",
            ),
            Trigger(
                field="real_time_biometric_public",
                condition=lambda f: f.real_time_biometric_public,
                reasoning="the system performs real-time biometric identification in publicly accessible spaces",
            ),
        ),
    ),
]


def _value_str(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def evaluate_principles(facts: ExtractedFacts) -> list[PrincipleFlag]:
    """Return one flag per implicated principle, in Section 7 table order."""
    flags = []
    for principle in PRINCIPLES:
        fired = [t for t in principle.triggers if t.condition(facts)]
        if not fired:
            continue
        fired_fields = tuple((t.field, _value_str(getattr(facts, t.field))) for t in fired)
        reasons = "; and ".join(
            f"{name}={value} → {t.reasoning}" for (name, value), t in zip(fired_fields, fired)
        )
        flags.append(
            PrincipleFlag(
                unesco=principle.unesco,
                ieee=principle.ieee,
                ieee_ref=principle.ieee_ref,
                fired_fields=fired_fields,
                explanation=f"Flagged because {reasons}.",
                evidence={
                    t.field: facts.evidence_snippets[t.field]
                    for t in fired
                    if t.field in facts.evidence_snippets
                },
                documentation_gap=all(t.documentation_gap for t in fired),
            )
        )
    return flags
