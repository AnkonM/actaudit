"""analysis/whatif.py: edits re-run rules and principles with no LLM."""
from analysis import whatif
from rules import RiskTier
from schema import DecisionAutonomy as A, DeploymentDomain as D
from tests.test_rules import make_facts

PRESET = next(iter(whatif.PRESETS.values()))


def test_disclosure_preset_removes_documentation_gaps_but_not_the_tier():
    original = make_facts(deployment_domain=D.HIRING)
    edited = whatif.edit_facts(original, PRESET)
    diff = whatif.compare(original, edited)
    assert not diff.tier_changed and diff.edited_tier is RiskTier.HIGH_RISK
    assert diff.removed_flags == ["Human oversight and determination", "Transparency and explainability"]
    assert "The tier stays High-Risk (rule 4)." in whatif.describe(diff)


def test_disclosure_does_not_clear_a_fact_based_oversight_flag():
    original = make_facts(decision_autonomy=A.FULLY_AUTONOMOUS)
    diff = whatif.compare(original, whatif.edit_facts(original, PRESET))
    assert "Human oversight and determination" not in diff.removed_flags  # autonomy still fires it


def test_military_edit_moves_to_out_of_scope():
    original = make_facts(deployment_domain=D.LAW_ENFORCEMENT)
    diff = whatif.compare(original, whatif.edit_facts(original, {"military_defence_use": True}))
    assert diff.tier_changed and (diff.original_rule, diff.edited_rule) == (4, 0)
    assert whatif.describe(diff)[0] == ("The tier changes from High-Risk (rule 4) to Out of scope (rule 0).")
    assert diff.changed_fields == [("military_defence_use", False, True)]


def test_edit_drops_evidence_only_for_changed_fields():
    original = make_facts(deployment_domain=D.HIRING,
                          evidence_snippets={"deployment_domain": "ranks CVs", "data_sensitivity": "names"})
    edited = whatif.edit_facts(original, {"deployment_domain": D.EDUCATION, "data_sensitivity": original.data_sensitivity})
    assert edited.evidence_snippets == {"data_sensitivity": "names"}


def test_no_change_message():
    f = make_facts()
    assert whatif.describe(whatif.compare(f, f)) == ["No fact has been changed yet: edit a value to see its effect."]
