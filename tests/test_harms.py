"""analysis/harms.py: affected parties, harm categories and tab pointers."""
from analysis import harms
from rules import RiskTier
from schema import (
    AffectedPopulation as P,
    DataSensitivity as S,
    DecisionAutonomy as A,
    DeploymentDomain as D,
    TargetType,
)
from tests.test_rules import make_facts


def categories(**overrides):
    return {c: [f.fired_fields for f in fs]
            for c, fs in harms.findings_by_category(make_facts(**overrides)).items()}


def test_all_five_categories_always_listed_in_order():
    assert list(harms.findings_by_category(make_facts())) == list(harms.HARM_CATEGORIES)


def test_baseline_personal_data_only_raises_privacy():
    grouped = categories()  # BASELINE: data_sensitivity=personal, domain=other
    assert grouped[harms.PRIVACY] == [(("data_sensitivity", "personal"),)]
    assert all(not v for c, v in grouped.items() if c != harms.PRIVACY)


def test_hiring_is_allocative():
    assert (("deployment_domain", "hiring"),) in categories(deployment_domain=D.HIRING)[harms.ALLOCATIVE]


def test_face_recognition_hits_quality_representational_and_privacy():
    grouped = categories(biometric_use=True, deployment_domain=D.BIOMETRIC_ID, data_sensitivity=S.SENSITIVE)
    assert (("biometric_use", "true"),) in grouped[harms.QUALITY_OF_SERVICE]
    assert (("biometric_use", "true"),) in grouped[harms.REPRESENTATIONAL]  # only the set trigger
    assert (("biometric_use", "true"),) in grouped[harms.PRIVACY]


def test_capability_fields_map_to_autonomy_and_dignity():
    grouped = categories(impersonation_capable=True, military_defence_use=True,
                         decision_autonomy=A.FULLY_AUTONOMOUS)
    fired = [f[0][0] for f in grouped[harms.AUTONOMY_DIGNITY]]
    assert fired == ["decision_autonomy", "impersonation_capable", "military_defence_use"]


def test_proxy_target_is_allocative_and_engagement_is_representational():
    assert (("target_type", "cost_or_spending"),) in categories(
        target_type=TargetType.COST_OR_SPENDING)[harms.ALLOCATIVE]
    grouped = categories(target_type=TargetType.ENGAGEMENT_OR_CLICKS)
    assert (("target_type", "engagement_or_clicks"),) in grouped[harms.REPRESENTATIONAL]


def test_findings_carry_evidence_for_their_triggers():
    facts = make_facts(emotion_inference=True, evidence_snippets={"emotion_inference": "reads faces"})
    finding = next(f for f in harms.harm_findings(facts) if f.category == harms.QUALITY_OF_SERVICE)
    assert finding.evidence == {"emotion_inference": "reads faces"}


def test_every_rule_has_a_rationale_and_known_category():
    for rule in harms.HARM_RULES:
        assert rule.category in harms.HARM_CATEGORIES and rule.rationale and rule.harm.endswith(".")


def test_affected_parties_from_domain_population_and_capabilities():
    parties = harms.affected_parties(make_facts(deployment_domain=D.HIRING,
                                                affected_population=P.VULNERABLE_GROUPS,
                                                impersonation_capable=True))
    assert [p.reason for p in parties] == [
        "deployment_domain=hiring", "affected_population=vulnerable_groups", "impersonation_capable=true"]


def test_affected_parties_not_determinable_when_nothing_stated():
    (party,) = harms.affected_parties(make_facts())
    assert party.party.startswith("Not determinable from documentation")


def test_related_tab_pointers():
    facts = make_facts(generates_synthetic_media=True, target_type=TargetType.ARRESTS_OR_POLICE_CONTACT)
    tabs = [p.tab for p in harms.related_tabs(facts, RiskTier.HIGH_RISK)]
    assert tabs == [2, 3, 4]
    assert "Art. 10(2)(f)" in harms.related_tabs(facts, RiskTier.HIGH_RISK)[0].text
    assert harms.related_tabs(make_facts(target_type=TargetType.DIRECT_OUTCOME), RiskTier.LIMITED_RISK) == []
