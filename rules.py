"""Rule engine — deterministic, auditable core (Blueprint Section 6).

RULES is an ordered list; the first rule whose condition is true wins. Read it top
to bottom. There is no scoring, weighting or LLM involvement.

Citations were audited against Regulation (EU) 2024/1689 (EUR-Lex); see blueprint
Section 6.2 / 6.2.1. Rules 5, 7 and 8 are project heuristics and say so in their
provision text.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from schema import (
    AffectedPopulation,
    DataSensitivity,
    DecisionAutonomy,
    DeploymentDomain as D,
    ExtractedFacts,
)


class RiskTier(str, Enum):
    PROHIBITED = "Prohibited"
    HIGH_RISK = "High-Risk"
    LIMITED_RISK = "Limited-Risk"
    MINIMAL_RISK = "Minimal-Risk"


@dataclass(frozen=True)
class Rule:
    number: int
    condition: Callable[[ExtractedFacts], bool]
    trigger_fields: tuple[str, ...]
    tier: RiskTier
    reasoning: str
    provision: str
    citation_verified: bool = False


@dataclass(frozen=True)
class Classification:
    tier: RiskTier
    rule_number: int
    fired_fields: tuple[tuple[str, str], ...]
    justification: str
    provision: str
    citation_verified: bool
    evidence: dict[str, str]


# Rule 3: Art. 5(1)(f) "workplace and education institutions"; hiring stands in for workplace.
EMOTION_BANNED_DOMAINS = {D.EDUCATION, D.HIRING}

# Rule 4: Annex III areas representable in the schema (Art. 6(2)).
ANNEX_III_DOMAINS = {
    D.HIRING,
    D.ESSENTIAL_SERVICES,
    D.LAW_ENFORCEMENT,
    D.EDUCATION,
    D.MIGRATION_ASYLUM_BORDER,
    D.CRITICAL_INFRASTRUCTURE,
}


RULES: list[Rule] = [
    Rule(
        number=1,
        condition=lambda f: f.real_time_biometric_public
        and f.deployment_domain == D.LAW_ENFORCEMENT,
        trigger_fields=("real_time_biometric_public", "deployment_domain"),
        tier=RiskTier.PROHIBITED,
        reasoning="real-time remote biometric identification in publicly accessible spaces "
        "for the purposes of law enforcement is a prohibited practice (narrow statutory "
        "exceptions exist, not modeled here)",
        provision="EU AI Act Art. 5(1)(h)",
        citation_verified=True,
    ),
    Rule(
        number=2,
        condition=lambda f: f.social_scoring,
        trigger_fields=("social_scoring",),
        tier=RiskTier.PROHIBITED,
        reasoning="scoring people based on social behaviour or personal characteristics "
        "that leads to detrimental treatment is a prohibited practice, whoever operates it",
        provision="EU AI Act Art. 5(1)(c)",
        citation_verified=True,
    ),
    Rule(
        number=3,
        condition=lambda f: f.emotion_inference
        and f.deployment_domain in EMOTION_BANNED_DOMAINS,
        trigger_fields=("emotion_inference", "deployment_domain"),
        tier=RiskTier.PROHIBITED,
        reasoning="inferring emotions in the areas of workplace and education institutions "
        "is a prohibited practice, except for medical or safety reasons",
        provision="EU AI Act Art. 5(1)(f)",
        citation_verified=True,
    ),
    Rule(
        number=4,
        # decision_autonomy is deliberately NOT a condition: Annex III membership makes a
        # system high-risk regardless of human oversight (blueprint 6.2 note).
        # decision_autonomy feeds the "human oversight" UNESCO/IEEE principle flag in
        # principles.py instead of the tier — see blueprint Section 7.
        condition=lambda f: f.deployment_domain in ANNEX_III_DOMAINS,
        trigger_fields=("deployment_domain",),
        tier=RiskTier.HIGH_RISK,
        reasoning="the domain is a named Annex III high-risk area, which makes the system "
        "high-risk regardless of human oversight",
        provision="EU AI Act Annex III + Art. 6(2)",
        citation_verified=True,
    ),
    Rule(
        number=5,
        condition=lambda f: f.data_sensitivity == DataSensitivity.SENSITIVE
        and f.affected_population == AffectedPopulation.VULNERABLE_GROUPS,
        trigger_fields=("data_sensitivity", "affected_population"),
        tier=RiskTier.HIGH_RISK,
        reasoning="sensitive data is processed about vulnerable groups, warranting "
        "heightened-risk treatment",
        provision="project heuristic, not derived from a specific Act provision",
        citation_verified=True,
    ),
    Rule(
        number=6,
        condition=lambda f: f.biometric_use and f.deployment_domain == D.BIOMETRIC_ID,
        trigger_fields=("biometric_use", "deployment_domain"),
        tier=RiskTier.HIGH_RISK,
        reasoning="remote biometric identification and biometric categorisation systems "
        "are a named high-risk area",
        provision="EU AI Act Annex III point 1(a)/(b)",
        citation_verified=True,
    ),
    Rule(
        number=7,
        condition=lambda f: f.deployment_domain == D.GENERAL_CONSUMER
        and f.data_sensitivity == DataSensitivity.NONE
        and f.decision_autonomy == DecisionAutonomy.HUMAN_IN_LOOP,
        trigger_fields=("deployment_domain", "data_sensitivity", "decision_autonomy"),
        tier=RiskTier.MINIMAL_RISK,
        reasoning="no named high-risk area is implicated, no personal data is processed "
        "and a human approves each decision",
        provision="project heuristic, not derived from a specific Act provision",
        citation_verified=True,
    ),
    Rule(
        number=8,  # default — always matches, so it must stay last
        condition=lambda f: True,
        trigger_fields=(),
        tier=RiskTier.LIMITED_RISK,
        reasoning="",  # blueprint 6.2 fixes the default justification string exactly
        provision="project default tier — no specific Article; Art. 50(1) transparency "
        "duties may separately apply to systems that interact directly with people or "
        "generate synthetic content",
        citation_verified=True,
    ),
]


def _value_str(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _build(rule: Rule, facts: ExtractedFacts) -> Classification:
    fired = tuple((name, _value_str(getattr(facts, name))) for name in rule.trigger_fields)
    if fired:
        because = " and ".join(f"{name}={value}" for name, value in fired)
        justification = (
            f"Classified as {rule.tier.value} because {because} "
            f"→ {rule.reasoning} (see: {rule.provision})"
        )
    else:
        justification = (
            f"Classified as {rule.tier.value} because no higher- or lower-tier rule matched."
        )
    evidence = {
        name: facts.evidence_snippets[name]
        for name in rule.trigger_fields
        if name in facts.evidence_snippets
    }
    return Classification(
        tier=rule.tier,
        rule_number=rule.number,
        fired_fields=fired,
        justification=justification,
        provision=rule.provision,
        citation_verified=rule.citation_verified,
        evidence=evidence,
    )


def classify(facts: ExtractedFacts) -> Classification:
    """Walk RULES in order; return the first match."""
    for rule in RULES:
        if rule.condition(facts):
            return _build(rule, facts)
    raise AssertionError("unreachable: the final default rule always matches")
