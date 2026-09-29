import pytest

from schema import DeploymentDomain, ExtractedFacts, SchemaValidationError
from tests.test_rules import BASELINE, make_facts

RAW = {k: (v.value if hasattr(v, "value") else list(v) if isinstance(v, tuple) else v)
       for k, v in BASELINE.items()}


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


# --- Schema v2 (blueprint §5, "Schema v2 additions") ---------------------------------

from schema import (  # noqa: E402
    ABSENT_DEFAULTS,
    DISPLAY_ORDER,
    FIELD_NAMES,
    SCHEMA_VERSION,
    V2_FIELDS,
    SyntheticMediaType,
    TargetType,
    upgrade_facts_dict,
)


def test_schema_version_is_2():
    assert SCHEMA_VERSION == 2


def test_no_judgment_fields_in_the_llm_contract():
    """§1.1: the extraction schema holds observable facts only."""
    for name in FIELD_NAMES:
        for word in ("risk", "tier", "fair", "harm", "compliant", "compliance", "legal"):
            assert word not in name, name


def test_v2_fields_default_to_absent_signal_values():
    facts = make_facts()
    for name in V2_FIELDS:
        assert getattr(facts, name) == ABSENT_DEFAULTS[name], name
    assert facts.target_type is TargetType.UNKNOWN
    assert facts.synthetic_media_types == ()


def test_display_order_lists_every_fact_once():
    assert sorted(DISPLAY_ORDER) == sorted(FIELD_NAMES - {"evidence_snippets"})


def test_from_dict_converts_media_types_and_drops_repeats():
    facts = ExtractedFacts.from_dict({**RAW, "generates_synthetic_media": True,
                                      "synthetic_media_types": ["audio", "video", "audio"]})
    assert facts.synthetic_media_types == (SyntheticMediaType.AUDIO, SyntheticMediaType.VIDEO)


@pytest.mark.parametrize("bad", [["hologram"], "audio", None])
def test_from_dict_rejects_bad_media_types(bad):
    with pytest.raises(SchemaValidationError, match="synthetic_media_types"):
        ExtractedFacts.from_dict({**RAW, "synthetic_media_types": bad})


def test_from_dict_rejects_invalid_target_type():
    with pytest.raises(SchemaValidationError, match="target_type"):
        ExtractedFacts.from_dict({**RAW, "target_type": "risk_score"})


def test_rejects_long_target_variable():
    with pytest.raises(SchemaValidationError, match="target_variable"):
        make_facts(target_variable="x" * 201)


def test_rejects_list_instead_of_tuple_for_media_types():
    with pytest.raises(SchemaValidationError, match="synthetic_media_types"):
        make_facts(synthetic_media_types=[SyntheticMediaType.IMAGE])


def test_from_dict_still_requires_v2_fields():
    """Live extraction stays strict; only fixtures are upgraded."""
    v1 = {k: v for k, v in RAW.items() if k not in V2_FIELDS}
    with pytest.raises(SchemaValidationError, match="missing"):
        ExtractedFacts.from_dict(v1)


def test_upgrade_fills_v1_dicts_with_defaults():
    v1 = {k: v for k, v in RAW.items() if k not in V2_FIELDS}
    upgraded, legacy = upgrade_facts_dict(v1)
    assert legacy is True
    facts = ExtractedFacts.from_dict(upgraded)
    assert facts.military_defence_use is False and facts.target_type is TargetType.UNKNOWN
    assert upgrade_facts_dict(RAW) == (dict(RAW), False)
