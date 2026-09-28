"""Offline extractor tests: a fake Gemini client returns scripted responses."""
import json

import pytest
from google.genai import errors

from extractor import (
    MAX_INPUT_CHARS,
    RESPONSE_SCHEMA,
    TRUNCATION_NOTICE,
    EmptyInputError,
    ExtractionAPIError,
    MalformedExtractionError,
    extract_facts,
    prepare_llm_text,
)
from schema import DeploymentDomain, ExtractionConfidence

VALID = {
    "system_purpose": "Screens CVs and ranks job applicants.",
    "deployment_domain": "hiring",
    "data_sensitivity": "personal",
    "biometric_use": False,
    "decision_autonomy": "fully_autonomous",
    "affected_population": "vulnerable_groups",
    "emotion_inference": False,
    "social_scoring": False,
    "real_time_biometric_public": False,
    "human_oversight_mentioned": False,
    "transparency_mentioned": False,
    "extraction_confidence": "high",
    "evidence_snippets": {"deployment_domain": "ranks job applicants", "social_scoring": ""},
}


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return FakeResponse(out)


class FakeClient:
    def __init__(self, *outputs):
        self.models = FakeModels(outputs)


def test_valid_json():
    client = FakeClient(json.dumps(VALID))
    facts = extract_facts("A hiring tool README.", client=client)
    assert facts.deployment_domain is DeploymentDomain.HIRING
    assert facts.extraction_confidence is ExtractionConfidence.HIGH
    assert facts.evidence_snippets == {"deployment_domain": "ranks job applicants"}
    assert len(client.models.calls) == 1


def test_config_disables_afc_and_constrains_json():
    client = FakeClient(json.dumps(VALID))
    extract_facts("text", client=client)
    config = client.models.calls[0]["config"]
    assert config.automatic_function_calling.disable is True
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == RESPONSE_SCHEMA
    assert "risk" not in json.dumps(RESPONSE_SCHEMA["properties"]).lower()


def test_malformed_then_valid_succeeds_on_retry():
    client = FakeClient("{not json", json.dumps(VALID))
    facts = extract_facts("text", client=client)
    assert facts.deployment_domain is DeploymentDomain.HIRING
    assert len(client.models.calls) == 2
    assert "invalid JSON" in client.models.calls[1]["contents"]
    assert "Return ONLY valid JSON" in client.models.calls[1]["contents"]


def test_malformed_twice_raises():
    client = FakeClient("{not json", "still not json")
    with pytest.raises(MalformedExtractionError, match="twice"):
        extract_facts("text", client=client)
    assert len(client.models.calls) == 2


def test_out_of_enum_value_is_retried():
    bad = {**VALID, "deployment_domain": "healthcare"}
    client = FakeClient(json.dumps(bad), json.dumps(VALID))
    facts = extract_facts("text", client=client)
    assert facts.deployment_domain is DeploymentDomain.HIRING
    assert "deployment_domain='healthcare'" in client.models.calls[1]["contents"]


def test_out_of_enum_twice_raises():
    bad = json.dumps({**VALID, "decision_autonomy": "sometimes"})
    with pytest.raises(MalformedExtractionError, match="decision_autonomy"):
        extract_facts("text", client=FakeClient(bad, bad))


def test_missing_field_is_retried():
    partial = {k: v for k, v in VALID.items() if k != "social_scoring"}
    client = FakeClient(json.dumps(partial), json.dumps(VALID))
    extract_facts("text", client=client)
    assert len(client.models.calls) == 2


def test_api_error_is_not_retried_on_same_model():
    err = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    client = FakeClient(err)
    with pytest.raises(ExtractionAPIError, match="rate-limited or out of quota") as exc_info:
        extract_facts("text", client=client, models=["gemini-3.8-flash"])
    assert exc_info.value.code == 429
    assert len(client.models.calls) == 1


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_input(text):
    with pytest.raises(EmptyInputError):
        extract_facts(text, client=FakeClient())


def test_truncation_applies_to_llm_copy_only():
    original = "a" * (MAX_INPUT_CHARS + 500)
    llm_text, truncated = prepare_llm_text(original)
    assert truncated is True
    assert llm_text == "a" * MAX_INPUT_CHARS + TRUNCATION_NOTICE
    assert len(original) == MAX_INPUT_CHARS + 500

    client = FakeClient(json.dumps(VALID))
    extract_facts(original, client=client)
    assert client.models.calls[0]["contents"].endswith("(truncated)")


def test_short_text_not_truncated():
    assert prepare_llm_text("  short  ") == ("short", False)


def test_snippets_for_defaulted_fields_are_dropped():
    raw = {**VALID, "evidence_snippets": {
        "deployment_domain": "ranks job applicants",   # hiring != default: kept
        "transparency_mentioned": "none",              # false == default: dropped
        "data_sensitivity": "none_default_omit_guard",  # personal != default: kept
        "system_purpose": "Screens CVs",                # no default: kept
    }}
    facts = extract_facts("text", client=FakeClient(json.dumps(raw)))
    assert set(facts.evidence_snippets) == {"deployment_domain", "data_sensitivity", "system_purpose"}


def test_human_in_loop_is_not_the_absent_default():
    from extractor import ABSENT_DEFAULTS, SYSTEM_INSTRUCTION
    from schema import DecisionAutonomy
    assert ABSENT_DEFAULTS["decision_autonomy"] is DecisionAutonomy.HUMAN_ON_LOOP
    assert '- decision_autonomy: "human_on_loop"' in SYSTEM_INSTRUCTION


def test_raw_response_returned_is_the_accepted_one():
    from extractor import extract_with_details
    good = json.dumps(VALID)
    result = extract_with_details("text", client=FakeClient("{bad", good))
    assert result.raw_response == good
    assert result.model == "gemini-3.8-flash"


def _api_error(code):
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"message": "x", "status": "X"}})


def test_falls_back_to_next_model_on_quota_and_overload():
    from extractor import MODEL_CHAIN, extract_with_details
    client = FakeClient(_api_error(429), _api_error(503), json.dumps(VALID))
    result = extract_with_details("text", client=client)
    assert [c["model"] for c in client.models.calls] == list(MODEL_CHAIN[:3])
    assert result.model == MODEL_CHAIN[2]


def test_server_deadline_504_falls_back():
    from extractor import MODEL_CHAIN, extract_with_details
    client = FakeClient(_api_error(504), json.dumps(VALID))
    assert extract_with_details("text", client=client).model == MODEL_CHAIN[1]


def test_malformed_retry_stays_on_the_model_that_answered():
    from extractor import MODEL_CHAIN
    client = FakeClient(_api_error(429), "{bad", json.dumps(VALID))
    extract_facts("text", client=client)
    assert [c["model"] for c in client.models.calls] == [MODEL_CHAIN[0], MODEL_CHAIN[1], MODEL_CHAIN[1]]


def test_all_models_exhausted_raises():
    from extractor import MODEL_CHAIN
    client = FakeClient(*[_api_error(429)] * len(MODEL_CHAIN))
    with pytest.raises(ExtractionAPIError, match="Every configured Gemini model"):
        extract_facts("text", client=client)


def test_non_quota_api_error_does_not_fall_back():
    client = FakeClient(_api_error(401), json.dumps(VALID))
    with pytest.raises(ExtractionAPIError, match="HTTP 401"):
        extract_facts("text", client=client)
    assert len(client.models.calls) == 1


def test_transport_failure_becomes_extraction_api_error():
    client = FakeClient(ConnectionError("Server disconnected"))
    with pytest.raises(ExtractionAPIError, match="Couldn't reach the Gemini API") as exc_info:
        extract_facts("text", client=client)
    assert exc_info.value.code is None
    assert len(client.models.calls) == 1



@pytest.mark.parametrize("codes,quota,phrase", [
    ((429, 429, 429, 429), True, "rate-limited or out of quota"),
    ((503, 503, 503, 503), False, "temporarily overloaded"),
    ((503, 429, 504, 503), True, "rate-limited or out of quota"),  # any 429 means quota
    ((504, 503, 504, 503), False, "temporarily overloaded"),
])
def test_exhausted_chain_records_codes_and_words_message(codes, quota, phrase):
    from extractor import AllModelsUnavailableError, MODEL_CHAIN
    client = FakeClient(*[_api_error(c) for c in codes])
    with pytest.raises(AllModelsUnavailableError) as exc_info:
        extract_facts("text", client=client)
    err = exc_info.value
    assert err.codes == codes and len(codes) == len(MODEL_CHAIN)
    assert err.quota_exhausted is quota
    assert phrase in str(err)



def _invalid_key_error():
    return errors.ClientError(400, {"error": {
        "code": 400, "message": "API key not valid. Please pass a valid API key.",
        "status": "INVALID_ARGUMENT",
        "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}],
    }})


def test_invalid_key_raises_specific_error_without_fallback():
    from extractor import InvalidAPIKeyError
    client = FakeClient(_invalid_key_error(), json.dumps(VALID))
    with pytest.raises(InvalidAPIKeyError, match="rejected the API key") as exc_info:
        extract_facts("text", client=client)
    assert exc_info.value.code == 400
    assert len(client.models.calls) == 1  # a bad key is not worth trying on other models


@pytest.mark.parametrize("code", [401, 403])
def test_auth_failures_are_invalid_key_errors(code):
    from extractor import InvalidAPIKeyError
    with pytest.raises(InvalidAPIKeyError):
        extract_facts("text", client=FakeClient(errors.ClientError(code, {"error": {"message": "denied"}})))


def test_other_400s_are_not_treated_as_bad_keys():
    from extractor import InvalidAPIKeyError
    bad_request = errors.ClientError(400, {"error": {"message": "Invalid schema", "status": "INVALID_ARGUMENT"}})
    with pytest.raises(ExtractionAPIError) as exc_info:
        extract_facts("text", client=FakeClient(bad_request))
    assert not isinstance(exc_info.value, InvalidAPIKeyError)
