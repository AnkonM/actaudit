import pytest

from rules import RULES, RiskTier, classify
from schema import (
    AffectedPopulation as P,
    DataSensitivity as S,
    DecisionAutonomy as A,
    DeploymentDomain as D,
    ExtractedFacts,
    ExtractionConfidence,
    TargetType,
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
    # schema v2 fields, at their absent defaults
    target_variable="",
    target_type=TargetType.UNKNOWN,
    generates_synthetic_media=False,
    synthetic_media_types=(),
    impersonation_capable=False,
    output_marking_mentioned=False,
    consent_safeguards_mentioned=False,
    military_defence_use=False,
    robustness_testing_mentioned=False,
    failsafe_mentioned=False,
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
    assert [r.number for r in RULES] == list(range(0, 9))  # Rule 0 (Art. 2(3)) first
    assert RULES[-1].trigger_fields == ()
    assert all(r.citation_verified is True for r in RULES)


def test_condition_text_mirrors_blueprint_rule_table():
    """The UI's rule table shows condition_text; it must match blueprint §6.2 exactly."""
    import re
    from pathlib import Path

    blueprint = (Path(__file__).resolve().parent.parent / "docs" / "ActAudit_Project_Blueprint.md").read_text()
    section = blueprint.split("### 6.2 v1 Rule Table")[1].split("**Note on why")[0]
    rows = re.findall(r"^\| (\d) \| (.+?) \| \*\*", section, re.M)
    assert [int(n) for n, _ in rows] == [r.number for r in RULES]
    for (number, condition), rule in zip(rows, RULES):
        assert rule.condition_text == condition.strip("`*"), f"rule {number}"


# --- Rule 0 (Art. 2(3)) and classify_with_trace (experiment tabs) --------------------

import itertools  # noqa: E402

from rules import classify_with_trace  # noqa: E402


def test_rule_0_out_of_scope_precedes_every_other_rule():
    # Would otherwise be Prohibited by rule 1 and rule 2.
    facts = make_facts(military_defence_use=True, social_scoring=True,
                       real_time_biometric_public=True, deployment_domain=D.LAW_ENFORCEMENT)
    result = classify(facts)
    assert result.tier is RiskTier.OUT_OF_SCOPE
    assert result.rule_number == 0
    assert result.provision == "EU AI Act Art. 2(3)"
    assert result.citation_verified is True


def test_rule_0_justification_says_the_act_does_not_apply():
    result = classify(make_facts(military_defence_use=True,
                                 evidence_snippets={"military_defence_use": "defence ministry only"}))
    assert result.justification == (
        "Classified as Out of scope because military_defence_use=true → the EU AI Act does "
        "not apply to AI systems placed on the market, put into service or used exclusively "
        "for military, defence or national-security purposes; the UNESCO/IEEE principle "
        "flags are still shown (see: EU AI Act Art. 2(3))"
    )
    assert result.evidence == {"military_defence_use": "defence ministry only"}


def test_without_military_use_classification_is_unchanged():
    for _, overrides, tier, rule_number in CASES:
        result = classify(make_facts(**overrides, military_defence_use=False))
        assert (result.tier, result.rule_number) == (tier, rule_number)


def test_new_capability_fields_do_not_change_rules_1_to_8():
    facts = make_facts(generates_synthetic_media=True, impersonation_capable=True,
                       robustness_testing_mentioned=True, failsafe_mentioned=True,
                       target_type=TargetType.COST_OR_SPENDING)
    assert classify(facts).rule_number == 8


def _grid():
    """Every combination of the values the rule conditions test."""
    domains = list(D)
    for domain, sens, auton, pop, rtb, social, emotion, bio, mil in itertools.product(
        domains, list(S), list(A), list(P), *([(False, True)] * 5)
    ):
        yield make_facts(deployment_domain=domain, data_sensitivity=sens, decision_autonomy=auton,
                         affected_population=pop, real_time_biometric_public=rtb,
                         social_scoring=social, emotion_inference=emotion, biometric_use=bio,
                         military_defence_use=mil)


def test_clauses_agree_with_conditions_on_every_combination():
    """The trace explains conditions through clauses; they must never disagree."""
    count = 0
    for facts in _grid():
        count += 1
        for rule in RULES:
            if rule.clauses:
                assert all(c.holds(facts) for c in rule.clauses) == rule.condition(facts), rule.number
    assert count == len(D) * 3 * 3 * 2 * 32


def test_clause_text_reproduces_condition_text():
    for rule in RULES:
        if rule.clauses:
            assert " and ".join(c.text for c in rule.clauses) == rule.condition_text
    assert RULES[-1].clauses == ()  # the default rule always matches


def test_trace_lists_every_rule_and_marks_the_decider():
    facts = make_facts(deployment_domain=D.HIRING, emotion_inference=False)
    trace = classify_with_trace(facts)
    assert [e.number for e in trace.entries] == [r.number for r in RULES]
    assert [e.number for e in trace.entries if e.decided] == [4]
    assert trace.classification == classify(facts)
    rule3 = trace.entries[4 - 1 + 0]  # entries start at rule 0
    assert rule3.number == 3 and not rule3.matched
    assert [c.text for c in rule3.failed] == ["emotion_inference == true"]
    assert rule3.clauses[1].holds and rule3.clauses[1].actual == "hiring"
    default = trace.entries[-1]
    assert default.matched and not default.decided  # would match, but rule 4 decided first


def test_trace_reports_actual_values():
    trace = classify_with_trace(make_facts(military_defence_use=True))
    entry = trace.entries[0]
    assert entry.decided and entry.matched and entry.tier is RiskTier.OUT_OF_SCOPE
    assert entry.clauses[0].actual == "true"
