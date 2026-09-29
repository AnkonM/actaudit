"""analysis/impact_assessment.py: Art. 27 elements, impact level, actions, reports."""
from datetime import date

import pytest

from analysis import impact_assessment as ia
from rules import RULES, RiskTier
from schema import AffectedPopulation as P, DataSensitivity as S, DecisionAutonomy as A, DeploymentDomain as D
from tests.helpers import make_result


def build(**kw):
    return ia.build(make_result(**kw), today=date(2026, 9, 29))


def test_all_six_art27_elements_in_order():
    a = build()
    assert [e.point for e in a.elements] == list("abcdef")
    b = a.elements[1]
    assert b.lines == [ia.NOT_DETERMINABLE] and not b.determinable


def test_elements_fill_only_from_facts():
    a = build(deployment_domain=D.HIRING, human_oversight_mentioned=True, failsafe_mentioned=True,
              evidence_snippets={"human_oversight_mentioned": "recruiters review every ranking"})
    el = {e.point: e for e in a.elements}
    assert el["a"].determinable and "Deployment domain: hiring" in el["a"].lines[1]
    assert "Job applicants and employees" in el["c"].lines[0]
    assert any(line.startswith("Allocative:") for line in el["d"].lines)
    assert 'recruiters review every ranking' in el["e"].lines[0]
    assert el["f"].determinable


def test_undocumented_oversight_is_not_determinable():
    el = {e.point: e for e in build().elements}
    assert el["e"].lines[0].startswith(ia.NOT_DETERMINABLE) and not el["f"].determinable


def test_dataset_findings_join_element_d():
    a = ia.build(make_result(), "Adult", ["Gap of 19.6%."], True)
    assert "Dataset: Gap of 19.6%." in {e.point: e for e in a.elements}["d"].lines
    assert any("dataset issues" in x.action for x in a.actions)


@pytest.mark.parametrize("kw,level,score", [
    (dict(data_sensitivity=S.NONE, decision_autonomy=A.HUMAN_IN_LOOP), "I", 0),
    (dict(deployment_domain=D.HIRING), "II", 3 + 1 + 1),  # domain + personal data + on-loop
    (dict(deployment_domain=D.HIRING, affected_population=P.VULNERABLE_GROUPS), "III", 3 + 1 + 1 + 2),
])
def test_impact_level_bands(kw, level, score):
    lvl = ia.impact_level(make_result(**kw).extraction.facts, RiskTier.HIGH_RISK)
    assert (lvl.score, lvl.level) == (score, level)


def test_impact_level_hand_example_and_mitigation():
    facts = make_result(deployment_domain=D.HIRING, decision_autonomy=A.FULLY_AUTONOMOUS,
                        human_oversight_mentioned=True).extraction.facts
    lvl = ia.impact_level(facts, RiskTier.HIGH_RISK)
    # hiring 3 + personal 1 + fully autonomous 3 = 7; oversight documented -1 -> 6: level III
    assert (lvl.impact_points, lvl.mitigation_points, lvl.score, lvl.level) == (7, 1, 6, "III")


def test_prohibited_forces_level_iv():
    facts = make_result(social_scoring=True).extraction.facts
    lvl = ia.impact_level(facts, RiskTier.PROHIBITED)
    assert lvl.level == "IV" and lvl.override


def test_actions_by_rule():
    a = build(deployment_domain=D.HIRING, data_sensitivity=S.SENSITIVE)
    citations = [x.citation for x in a.actions]
    assert "EU AI Act Art. 9(1)" in citations and "EU AI Act Art. 50(1)" in citations
    assert "GDPR (Regulation (EU) 2016/679) Art. 35(1), 35(3)(b)" in citations
    assert not any("proxy" in x.action for x in a.actions)


def test_citation_flags_are_honest_everywhere():
    """§15.1: a verified flag or an explicit project-heuristic / unverified label, never neither."""
    for rule in ia.ACTION_RULES:
        if rule.citation_verified:
            assert "(unverified)" not in rule.citation
        else:
            assert "(unverified)" in rule.citation
        assert rule.citation.startswith(("EU AI Act", "GDPR")) or rule.citation == ia.PROJECT_HEURISTIC
    for rule in RULES:
        assert rule.citation_verified and "(unverified)" not in rule.provision


def test_markdown_report_has_every_section_and_escapes_values():
    hostile = "[x](javascript:alert(1)) <img src=x>"
    a = ia.build(make_result(label=hostile, system_purpose="<b>purpose</b>"), hostile, [hostile], True,
                 today=date(2026, 9, 29))
    md = ia.to_markdown(a)
    for heading in ("# ActAudit algorithmic impact assessment", "## EU AI Act classification",
                    "## UNESCO and IEEE principle flags", "## Impact assessment",
                    "## Impact level", "## Recommended actions", "## Dataset results"):
        assert heading in md
    assert ia.DISCLAIMER in md and "(citation verified)" in md
    import re
    # Only escaped forms may appear: no unescaped link syntax or HTML tag anywhere.
    assert not re.search(r"(?<!\\)\]\(javascript", md)
    assert not re.search(r"(?<!\\)<(img|b)\b", md)
    assert "\\[x\\]\\(javascript" in md


def test_pdf_report_is_a_pdf_with_latin1_safe_text():
    a = build(system_purpose="Screens CVs → ranks — “quoted” 你好")
    pdf = ia.to_pdf(a)
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1500
