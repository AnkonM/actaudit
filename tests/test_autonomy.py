"""analysis/autonomy.py: scope, autonomy and Art. 14/15 documentation checks."""
from analysis import autonomy as au
from rules import RiskTier
from schema import DecisionAutonomy as A
from tests.test_rules import make_facts


def test_scope_follows_military_use():
    assert au.scope_result(make_facts(military_defence_use=True)).out_of_scope
    result = au.scope_result(make_facts())
    assert not result.out_of_scope and result.citation == "EU AI Act Art. 2(3)" and result.citation_verified


def test_checks_map_to_the_three_fields_and_tier_status():
    checks = au.documentation_checks(make_facts(robustness_testing_mentioned=True,
                                                evidence_snippets={"robustness_testing_mentioned": "99% on LFW"}),
                                     RiskTier.HIGH_RISK)
    assert [c.field for c in checks] == ["human_oversight_mentioned", "robustness_testing_mentioned",
                                         "failsafe_mentioned"]
    assert [c.documented for c in checks] == [False, True, False]
    assert checks[1].evidence == "99% on LFW"
    assert {c.status for c in checks} == {"Required for high-risk systems"}
    assert au.documentation_checks(make_facts(), RiskTier.LIMITED_RISK)[0].status.startswith("Good practice")
    assert au.documentation_checks(make_facts(), RiskTier.OUT_OF_SCOPE)[0].status.startswith("Not required")
    assert all("Art. 1" in c.provision for c in checks)


def test_findings_flag_unsupervised_autonomy():
    lines = au.autonomy_findings(make_facts(decision_autonomy=A.FULLY_AUTONOMOUS), RiskTier.HIGH_RISK)
    assert au.AUTONOMY_TEXT[A.FULLY_AUTONOMOUS].startswith("Decisions are described as taken with no human review")
    assert any("most needs a human in control" in x for x in lines)
    assert any("doesn't show 3 of them" in x for x in lines)
