import json
from pathlib import Path

import pytest

from principles import PRINCIPLES, evaluate_principles
from schema import (
    AffectedPopulation as P,
    DataSensitivity as S,
    DecisionAutonomy as A,
    ExtractedFacts,
)
from tests.test_rules import make_facts

OVERSIGHT = "Human oversight and determination"
TRANSPARENCY = "Transparency and explainability"
FAIRNESS = "Fairness and non-discrimination"
PRIVACY = "Right to privacy and data protection"
DIGNITY = "Human dignity and autonomy"

# A fact-set that implicates no principle at all.
CLEAN = dict(human_oversight_mentioned=True, transparency_mentioned=True)


def flagged(**overrides):
    return {f.unesco: f for f in evaluate_principles(make_facts(**{**CLEAN, **overrides}))}


def test_clean_facts_raise_no_flags():
    assert flagged() == {}


@pytest.mark.parametrize("overrides,unesco,ieee,fields", [
    (dict(human_oversight_mentioned=False), OVERSIGHT, "Accountability",
     (("human_oversight_mentioned", "false"),)),
    (dict(decision_autonomy=A.FULLY_AUTONOMOUS), OVERSIGHT, "Accountability",
     (("decision_autonomy", "fully_autonomous"),)),
    (dict(transparency_mentioned=False), TRANSPARENCY, "Transparency",
     (("transparency_mentioned", "false"),)),
    (dict(affected_population=P.VULNERABLE_GROUPS), FAIRNESS, "Human Rights",
     (("affected_population", "vulnerable_groups"),)),
    (dict(data_sensitivity=S.SENSITIVE), PRIVACY, "Data Agency",
     (("data_sensitivity", "sensitive"),)),
    (dict(social_scoring=True), DIGNITY, "Well-being", (("social_scoring", "true"),)),
    (dict(real_time_biometric_public=True), DIGNITY, "Well-being",
     (("real_time_biometric_public", "true"),)),
])
def test_each_trigger_alone_flags_only_its_principle(overrides, unesco, ieee, fields):
    flags = flagged(**overrides)
    assert list(flags) == [unesco]
    assert flags[unesco].ieee == ieee
    assert flags[unesco].fired_fields == fields
    assert flags[unesco].explanation.startswith("Flagged because ")


def test_both_oversight_triggers_are_reported():
    flag = flagged(human_oversight_mentioned=False, decision_autonomy=A.FULLY_AUTONOMOUS)[OVERSIGHT]
    assert flag.fired_fields == (
        ("human_oversight_mentioned", "false"),
        ("decision_autonomy", "fully_autonomous"),
    )
    assert flag.explanation == (
        "Flagged because human_oversight_mentioned=false → the documentation doesn't "
        "mention any human review, override or appeal mechanism; and "
        "decision_autonomy=fully_autonomous → decisions are described as taken with "
        "no human review."
    )


@pytest.mark.parametrize("autonomy", [A.HUMAN_IN_LOOP, A.HUMAN_ON_LOOP])
def test_non_autonomous_values_do_not_flag_oversight(autonomy):
    assert OVERSIGHT not in flagged(decision_autonomy=autonomy)


def test_all_principles_flag_together_in_table_order():
    flags = evaluate_principles(make_facts(
        decision_autonomy=A.FULLY_AUTONOMOUS,
        affected_population=P.VULNERABLE_GROUPS,
        data_sensitivity=S.SENSITIVE,
        social_scoring=True,
    ))
    assert [f.unesco for f in flags] == [p.unesco for p in PRINCIPLES]


@pytest.mark.parametrize("overrides,unesco,gap", [
    (dict(human_oversight_mentioned=False), OVERSIGHT, True),
    (dict(transparency_mentioned=False), TRANSPARENCY, True),
    (dict(decision_autonomy=A.FULLY_AUTONOMOUS), OVERSIGHT, False),
    # A stated fact outweighs silence: mixed triggers are not a documentation gap.
    (dict(human_oversight_mentioned=False, decision_autonomy=A.FULLY_AUTONOMOUS), OVERSIGHT, False),
    (dict(data_sensitivity=S.SENSITIVE), PRIVACY, False),
    (dict(social_scoring=True), DIGNITY, False),
])
def test_documentation_gap_marker(overrides, unesco, gap):
    assert flagged(**overrides)[unesco].documentation_gap is gap


def test_evidence_only_for_fired_fields():
    flag = flagged(
        data_sensitivity=S.SENSITIVE,
        evidence_snippets={"data_sensitivity": "chest X-rays", "system_purpose": "x"},
    )[PRIVACY]
    assert flag.evidence == {"data_sensitivity": "chest X-rays"}


FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_recorded_fixtures_evaluate(path):
    facts = ExtractedFacts.from_dict(json.loads(path.read_text())["extracted_facts"])
    for flag in evaluate_principles(facts):
        assert flag.fired_fields and flag.explanation.endswith(".")


def test_ieee_identifiers_match_ead_general_principles():
    """Numbers verified against IEEE EAD First Edition, General Principles (primary PDF)."""
    expected = {"Human Rights": 1, "Well-being": 2, "Data Agency": 3, "Transparency": 5, "Accountability": 6}
    assert {p.ieee: p.ieee_ref for p in PRINCIPLES} == {
        name: f"IEEE EAD General Principle {n}" for name, n in expected.items()
    }
    flag = flagged(data_sensitivity=S.SENSITIVE)[PRIVACY]
    assert flag.ieee_ref == "IEEE EAD General Principle 3"
