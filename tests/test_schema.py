import pytest

from schema import DeploymentDomain, ExtractedFacts, SchemaValidationError
from tests.test_rules import BASELINE, make_facts

RAW = {k: (v.value if hasattr(v, "value") else v) for k, v in BASELINE.items()}


def test_from_dict_converts_valid_input():
    facts = ExtractedFacts.from_dict({**RAW, "deployment_domain": "hiring"})
    assert facts.deployment_domain is DeploymentDomain.HIRING


def test_from_dict_rejects_invalid_enum():
    with pytest.raises(SchemaValidationError, match="deployment_domain"):
        ExtractedFacts.from_dict({**RAW, "deployment_domain": "workplace"})


def test_from_dict_rejects_unknown_key():
    with pytest.raises(SchemaValidationError, match="unknown"):
        ExtractedFacts.from_dict({**RAW, "risk_tier": "High-Risk"})


def test_from_dict_rejects_missing_key():
    raw = dict(RAW)
    del raw["social_scoring"]
    with pytest.raises(SchemaValidationError, match="missing"):
        ExtractedFacts.from_dict(raw)


@pytest.mark.parametrize("bad", [1, "true", None])
def test_rejects_non_bool(bad):
    with pytest.raises(SchemaValidationError, match="biometric_use"):
        make_facts(biometric_use=bad)


def test_rejects_raw_string_for_enum_field():
    with pytest.raises(SchemaValidationError, match="deployment_domain"):
        make_facts(deployment_domain="hiring")


def test_rejects_long_purpose():
    with pytest.raises(SchemaValidationError, match="system_purpose"):
        make_facts(system_purpose="x" * 201)
    make_facts(system_purpose="x" * 200)


def test_rejects_unknown_evidence_key():
    with pytest.raises(SchemaValidationError, match="evidence_snippets"):
        make_facts(evidence_snippets={"not_a_field": "..."})
