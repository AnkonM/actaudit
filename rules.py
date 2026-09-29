"""Rule engine — deterministic, auditable core (Blueprint Section 6).

RULES is an ordered list; the first rule whose condition is true wins. Read it top
to bottom. There is no scoring, weighting or LLM involvement.

Citations were audited against Regulation (EU) 2024/1689 (EUR-Lex); see blueprint
Section 6.2 / 6.2.1. Rules 5, 7 and 8 are project heuristics and say so in their
provision text. Rule 0 (Art. 2(3), experiment tabs) runs before all others.

Each rule also lists its condition as clauses (field + allowed values). classify()
uses only `condition`; classify_with_trace() uses the clauses to report which part of
each condition held or failed. tests/test_rules.py checks the two always agree.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from schema import (
    AffectedPopulation,
    DataSensitivity,
    DecisionAutonomy,
    DeploymentDomain as D,
    ExtractedFacts,
)


class RiskTier(str, Enum):
    OUT_OF_SCOPE = "Out of scope"  # Rule 0: the Act does not apply (Art. 2(3))
    PROHIBITED = "Prohibited"
    HIGH_RISK = "High-Risk"
    LIMITED_RISK = "Limited-Risk"
    MINIMAL_RISK = "Minimal-Risk"


def _value_str(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, tuple):
        return "[" + ", ".join(_value_str(v) for v in value) + "]"
    return str(value)


@dataclass(frozen=True)
class Clause:
    """One conjunct of a rule condition: `field` must take one of `allowed`."""
    field: str
    allowed: tuple[Any, ...]

    @property
    def text(self) -> str:
        if len(self.allowed) == 1:
            return f"{self.field} == {_value_str(self.allowed[0])}"
        return f"{self.field} in [{', '.join(_value_str(v) for v in self.allowed)}]"

    def holds(self, facts: ExtractedFacts) -> bool:
        return getattr(facts, self.field) in self.allowed


@dataclass(frozen=True)
class Rule:
    number: int
    condition: Callable[[ExtractedFacts], bool]
    trigger_fields: tuple[str, ...]
    tier: RiskTier
    reasoning: str
    provision: str
    citation_verified: bool = False
    # Human-readable condition shown in the UI's rule table. Mirrors blueprint §6.2
    # word for word (enforced by tests/test_rules.py).
    condition_text: str = ""
    # The same condition as clauses, for classify_with_trace(). Empty = always true.
    clauses: tuple[Clause, ...] = ()


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
        number=0,  # evaluated before all others: the Act does not apply at all
        condition=lambda f: f.military_defence_use,
        trigger_fields=("military_defence_use",),
        tier=RiskTier.OUT_OF_SCOPE,
        reasoning="the EU AI Act does not apply to AI systems placed on the market, put "
        "into service or used exclusively for military, defence or national-security "
        "purposes; the UNESCO/IEEE principle flags are still shown",
        provision="EU AI Act Art. 2(3)",
        citation_verified=True,
        condition_text='military_defence_use == true',
        clauses=(Clause("military_defence_use", (True,)),),
    ),
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
        condition_text='real_time_biometric_public == true and deployment_domain == law_enforcement',
        clauses=(Clause("real_time_biometric_public", (True,)), Clause("deployment_domain", (D.LAW_ENFORCEMENT,))),
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
        condition_text='social_scoring == true',
        clauses=(Clause("social_scoring", (True,)),),
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
        condition_text='emotion_inference == true and deployment_domain in [education, hiring]',
        clauses=(Clause("emotion_inference", (True,)), Clause("deployment_domain", (D.EDUCATION, D.HIRING))),
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
        condition_text='deployment_domain in [hiring, essential_services, law_enforcement, education, migration_asylum_border, critical_infrastructure]',
        clauses=(Clause("deployment_domain", (D.HIRING, D.ESSENTIAL_SERVICES, D.LAW_ENFORCEMENT, D.EDUCATION, D.MIGRATION_ASYLUM_BORDER, D.CRITICAL_INFRASTRUCTURE)),),
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
        condition_text='data_sensitivity == sensitive and affected_population == vulnerable_groups',
        clauses=(Clause("data_sensitivity", (DataSensitivity.SENSITIVE,)), Clause("affected_population", (AffectedPopulation.VULNERABLE_GROUPS,))),
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
        condition_text='biometric_use == true and deployment_domain == biometric_id',
        clauses=(Clause("biometric_use", (True,)), Clause("deployment_domain", (D.BIOMETRIC_ID,))),
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
        condition_text='deployment_domain == general_consumer and data_sensitivity == none and decision_autonomy == human_in_loop',
        clauses=(Clause("deployment_domain", (D.GENERAL_CONSUMER,)), Clause("data_sensitivity", (DataSensitivity.NONE,)), Clause("decision_autonomy", (DecisionAutonomy.HUMAN_IN_LOOP,))),
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
        condition_text='(default — no other rule fired)',
    ),
]


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


@dataclass(frozen=True)
class ClauseResult:
    text: str  # e.g. "deployment_domain in [education, hiring]"
    field: str
    actual: str  # the fact's value, rendered like the justification strings
    holds: bool


@dataclass(frozen=True)
class RuleTraceEntry:
    number: int
    tier: RiskTier
    condition_text: str
    provision: str
    citation_verified: bool
    matched: bool  # its whole condition holds for these facts
    decided: bool  # the first matching rule: the one that set the tier
    clauses: tuple[ClauseResult, ...]

    @property
    def failed(self) -> tuple[ClauseResult, ...]:
        return tuple(c for c in self.clauses if not c.holds)


@dataclass(frozen=True)
class RuleTrace:
    classification: Classification
    entries: tuple[RuleTraceEntry, ...]


def classify_with_trace(facts: ExtractedFacts) -> RuleTrace:
    """classify(), plus every rule in order: matched or not, and which clauses failed.

    Rules after the deciding one are still evaluated, so the trace can show that a
    later rule would also have matched had an earlier one not decided first.
    """
    classification = classify(facts)
    entries = []
    for rule in RULES:
        results = tuple(
            ClauseResult(c.text, c.field, _value_str(getattr(facts, c.field)), c.holds(facts))
            for c in rule.clauses
        )
        entries.append(
            RuleTraceEntry(
                number=rule.number,
                tier=rule.tier,
                condition_text=rule.condition_text,
                provision=rule.provision,
                citation_verified=rule.citation_verified,
                matched=rule.condition(facts),
                decided=rule.number == classification.rule_number,
                clauses=results,
            )
        )
    return RuleTrace(classification, tuple(entries))
