"""Case Library data (validated against its schema) and the rule-generated verdict line."""
import copy
import json

import pytest

from analysis import case_library as cl
from rules import RiskTier
from schema import DeploymentDomain as D
from tests.test_rules import make_facts

RAW = json.loads(cl.CASES_FILE.read_text())


def test_case_file_is_valid():
    cases = cl.load_cases()
    assert 6 <= len(cases) <= 8
    for case in cases:
        assert cl.MIN_WORDS <= len(case.system_description.split()) <= cl.MAX_WORDS
        assert len(case.sources) >= 2 and all(s.url.startswith("https://") for s in case.sources)
        assert case.fixture == f"text__case_{case.id}"


def test_schema_documentation_matches_the_validator():
    schema = json.loads((cl.CASES_FILE.parent / "cases.schema.json").read_text())
    item = schema["properties"]["cases"]["items"]
    assert set(item["required"]) == cl.REQUIRED
    assert set(item["properties"]["sources"]["items"]["required"]) == cl.SOURCE_KEYS


@pytest.mark.parametrize("mutate,message", [
    (lambda c: c.pop("harm"), "missing or unknown"),
    (lambda c: c.update(extra="x"), "missing or unknown"),
    (lambda c: c.update(system_description="too short"), "words"),
    (lambda c: c.update(sources=c["sources"][:1]), "two sources"),
    (lambda c: c["sources"][0].update(url="http://insecure.example"), "https"),
    (lambda c: c.update(date="2016"), "YYYY-MM"),
    (lambda c: c.update(fixture="text__other"), "fixture"),
])
def test_invalid_cases_are_rejected(tmp_path, mutate, message):
    data = copy.deepcopy(RAW)
    mutate(data["cases"][0])
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))
    with pytest.raises(cl.CaseDataError, match=message):
        cl.load_cases(path)


def test_duplicate_ids_are_rejected(tmp_path):
    data = copy.deepcopy(RAW)
    data["cases"].append(copy.deepcopy(data["cases"][0]))
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))
    with pytest.raises(cl.CaseDataError, match="unique"):
        cl.load_cases(path)


def case(date="2016-05"):
    return cl.Case(id="x", title="X", date=date, jurisdiction="EU", fixture="text__case_x",
                   system_description="", what_happened="", harm="", what_followed="",
                   sources=(), unverified=())


@pytest.mark.parametrize("tier,start", [
    (RiskTier.PROHIBITED, "Yes"), (RiskTier.HIGH_RISK, "Partly"), (RiskTier.LIMITED_RISK, "Probably not"),
    (RiskTier.MINIMAL_RISK, "Probably not"), (RiskTier.OUT_OF_SCOPE, "No"),
])
def test_verdict_line_by_tier(tier, start):
    line = cl.would_act_catch(case(), tier, "EU AI Act Art. 5(1)(c)", make_facts())
    assert line.startswith(start)
    assert "not retroactive" in line and "this case (2016) predates it" in line


def test_cases_after_entry_into_force_are_not_called_earlier():
    line = cl.would_act_catch(case("2025-03"), RiskTier.HIGH_RISK, "p", make_facts())
    assert "predates" not in line and line.endswith("from 2 August 2026.")
    assert "predates it" in cl.would_act_catch(case("2024-01"), RiskTier.HIGH_RISK, "p", make_facts())


def test_capability_notes():
    deepfake = cl.would_act_catch(case(), RiskTier.LIMITED_RISK, "p",
                                  make_facts(generates_synthetic_media=True, impersonation_capable=True))
    assert "Art. 50" in deepfake and "already a crime" in deepfake
    biometric = cl.would_act_catch(case(), RiskTier.HIGH_RISK, "p",
                                   make_facts(biometric_use=True, deployment_domain=D.BIOMETRIC_ID))
    assert "Art. 5(1)(e)" in biometric
