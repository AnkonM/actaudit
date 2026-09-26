import pytest

from rules import RULES, RiskTier, classify
from schema import (
    AffectedPopulation as P,
    DataSensitivity as S,
    DecisionAutonomy as A,
    DeploymentDomain as D,
    ExtractedFacts,
    ExtractionConfidence,
)

BASELINE = dict(
    system_purpose="Test system.",
    deployment_domain=D.OTHER,
    data_sensitivity=S.PERSONAL,
    biometric_use=False,
    decision_autonomy=A.HUMAN_ON_LOOP,
    affected_population=P.GENERAL_PUBLIC,
    emotion_inference=False,
    social_scoring=False,
    real_time_biometric_public=False,
    human_oversight_mentioned=False,
    transparency_mentioned=False,
    extraction_confidence=ExtractionConfidence.HIGH,
    evidence_snippets={},
)


def make_facts(**overrides) -> ExtractedFacts:
    return ExtractedFacts(**{**BASELINE, **overrides})


CASES = [
    ("T1", dict(real_time_biometric_public=True, biometric_use=True,
                deployment_domain=D.LAW_ENFORCEMENT), RiskTier.PROHIBITED, 1),
    # Rule 1 needs law enforcement (Art. 5(1)(h)); outside it, nothing else matches here.
    ("T1b", dict(real_time_biometric_public=True, biometric_use=True,
                 deployment_domain=D.GENERAL_CONSUMER), RiskTier.LIMITED_RISK, 8),
    ("T2", dict(social_scoring=True, deployment_domain=D.ESSENTIAL_SERVICES,
                decision_autonomy=A.FULLY_AUTONOMOUS), RiskTier.PROHIBITED, 2),
    ("T3", dict(biometric_use=True, emotion_inference=True,
                deployment_domain=D.EDUCATION), RiskTier.PROHIBITED, 3),
    # Art. 5(1)(f) does not require biometric data.
    ("T3b", dict(emotion_inference=True, biometric_use=False,
                 deployment_domain=D.HIRING), RiskTier.PROHIBITED, 3),
    ("T4", dict(deployment_domain=D.HIRING,
                decision_autonomy=A.FULLY_AUTONOMOUS), RiskTier.HIGH_RISK, 4),
    ("T5", dict(deployment_domain=D.ESSENTIAL_SERVICES,
                decision_autonomy=A.HUMAN_ON_LOOP), RiskTier.HIGH_RISK, 4),
    # Annex III membership is high-risk regardless of human oversight (Art. 6(2)).
    ("T10", dict(deployment_domain=D.HIRING,
                 decision_autonomy=A.HUMAN_IN_LOOP), RiskTier.HIGH_RISK, 4),
    ("T13", dict(deployment_domain=D.CRITICAL_INFRASTRUCTURE,
                 decision_autonomy=A.HUMAN_IN_LOOP), RiskTier.HIGH_RISK, 4),
    ("T6", dict(data_sensitivity=S.SENSITIVE, affected_population=P.VULNERABLE_GROUPS,
                deployment_domain=D.GENERAL_CONSUMER,
                decision_autonomy=A.HUMAN_IN_LOOP), RiskTier.HIGH_RISK, 5),
    ("T7", dict(biometric_use=True, deployment_domain=D.BIOMETRIC_ID), RiskTier.HIGH_RISK, 6),
    ("T8", dict(deployment_domain=D.GENERAL_CONSUMER, data_sensitivity=S.NONE,
                decision_autonomy=A.HUMAN_IN_LOOP), RiskTier.MINIMAL_RISK, 7),
    ("T9", dict(), RiskTier.LIMITED_RISK, 8),
    ("T11", dict(deployment_domain=D.BIOMETRIC_ID, biometric_use=False), RiskTier.LIMITED_RISK, 8),
    ("T12", dict(biometric_use=True, emotion_inference=True,
                 deployment_domain=D.GENERAL_CONSUMER), RiskTier.LIMITED_RISK, 8),
]


@pytest.mark.parametrize("case_id,overrides,tier,rule_number", CASES, ids=[c[0] for c in CASES])
def test_classification(case_id, overrides, tier, rule_number):
    result = classify(make_facts(**overrides))
    assert result.tier == tier
    assert result.rule_number == rule_number
    assert result.justification.startswith(f"Classified as {tier.value} because")
    if rule_number != 8:
        assert result.justification.endswith(f"(see: {result.provision})")
    assert result.citation_verified is True


def test_t4_full_trace():
    facts = make_facts(
        deployment_domain=D.HIRING,
        decision_autonomy=A.FULLY_AUTONOMOUS,
        evidence_snippets={"deployment_domain": "screens job applicants",
                           "decision_autonomy": "no human review"},
    )
    result = classify(facts)
    assert result.fired_fields == (("deployment_domain", "hiring"),)
    assert result.provision == "EU AI Act Annex III + Art. 6(2)"
    assert result.justification == (
        "Classified as High-Risk because deployment_domain=hiring → the domain is a "
        "named Annex III high-risk area, which makes the system high-risk regardless "
        "of human oversight (see: EU AI Act Annex III + Art. 6(2))"
    )
    # decision_autonomy no longer drives the tier, so its evidence is not surfaced here.
    assert result.evidence == {"deployment_domain": "screens job applicants"}


def test_decision_autonomy_does_not_change_annex_iii_tier():
    tiers = {classify(make_facts(deployment_domain=D.EDUCATION, decision_autonomy=a)).tier
             for a in A}
    assert tiers == {RiskTier.HIGH_RISK}


def test_boolean_values_render_lowercase():
    result = classify(make_facts(social_scoring=True))
    assert result.fired_fields == (("social_scoring", "true"),)


def test_default_rule_justification():
    result = classify(make_facts())
    assert result.fired_fields == ()
    assert result.justification == (
        "Classified as Limited-Risk because no higher- or lower-tier rule matched."
    )


def test_rule_table_structure():
    assert [r.number for r in RULES] == list(range(1, 9))
    assert RULES[-1].trigger_fields == ()
    assert all(r.citation_verified is True for r in RULES)
