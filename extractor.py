"""LLM fact extraction (Blueprint Sections 4 step 3, 5, 5.1, 6.4).

Takes README / pasted text, returns a validated ExtractedFacts. The model extracts
observable facts only; it never sees or produces a risk tier (Section 1.1).

Standalone: does not import github_fetch or rules.
"""
import json
from dataclasses import dataclass, replace
import os
from typing import Any, Sequence

from google import genai
from google.genai import errors, types

from schema import (
    BOOL_FIELDS,
    AffectedPopulation,
    DataSensitivity,
    DecisionAutonomy,
    DeploymentDomain,
    ENUM_FIELDS,
    FIELD_NAMES,
    MAX_PURPOSE_CHARS,
    ExtractedFacts,
    SchemaValidationError,
)

# Tried in order. Free-tier quotas are per model, so on a quota (429), overload (503)
# or server deadline (504)
# error the next model is used (blueprint §10). gemini-flash-latest is excluded: it
# shares gemini-3.8-flash's quota. Do not add gemini-2.5-flash.
MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
)
DEFAULT_MODEL = MODEL_CHAIN[0]
FALLBACK_STATUS_CODES = frozenset({429, 503, 504})
REQUEST_TIMEOUT_MS = 60_000
MAX_INPUT_CHARS = 8000
TRUNCATION_NOTICE = "\n\n(truncated)"

# Values used when the text has no signal for a field (blueprint §5.1). Lower-risk,
# except decision_autonomy: human_in_loop is a positive claim that feeds Rule 7
# (Minimal-Risk), so silence must not produce it.
ABSENT_DEFAULTS: dict[str, Any] = {
    "deployment_domain": DeploymentDomain.OTHER,
    "data_sensitivity": DataSensitivity.NONE,
    "decision_autonomy": DecisionAutonomy.HUMAN_ON_LOOP,
    "affected_population": AffectedPopulation.GENERAL_PUBLIC,
    **{name: False for name in BOOL_FIELDS},
}


class ExtractionError(Exception):
    """Base class. `str(err)` is a user-facing message."""


class EmptyInputError(ExtractionError):
    pass


class ExtractionAPIError(ExtractionError):
    """The Gemini API call itself failed (auth, rate limit, outage). Not retried."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class AllModelsUnavailableError(ExtractionAPIError):
    """Every model in MODEL_CHAIN hit a quota, overload or deadline error."""


class MalformedExtractionError(ExtractionError):
    """The model's output failed JSON parsing or schema validation twice."""


@dataclass(frozen=True)
class ExtractionResult:
    facts: ExtractedFacts
    raw_response: str
    model: str  # the model that produced the accepted response


SYSTEM_INSTRUCTION = """\
You are extracting observable facts only from software documentation (a README,
model card or product description). Do not assess risk, legality, or compliance.

If information for a field is not present in the text, use the safest 'unknown'
default for that field and lower extraction_confidence accordingly — do not guess.
The defaults for absent information are:
- deployment_domain: "other"
- data_sensitivity: "none"
- decision_autonomy: "human_on_loop" (only use "human_in_loop" when the text says a
  human approves each decision, and quote that text as evidence)
- affected_population: "general_public"
- every boolean field: false
If several fields had to fall back to these defaults, set extraction_confidence to "low".

Field meanings:
- system_purpose: one-sentence summary of what the system does, at most 200 characters.
- deployment_domain: the primary domain the system operates in.
  - "hiring": recruitment, candidate screening, CV/resume parsing, worker management.
  - "essential_services": access to essential private or public services and
    benefits — creditworthiness or credit scoring, public-benefit eligibility,
    life/health insurance risk assessment or pricing, emergency call triage or
    dispatch, patient triage or resource prioritization.
  - Healthcare routing: clinical/diagnostic tools (disease detection, treatment
    recommendation, medical imaging analysis) -> "other". Healthcare-ACCESS tools
    (insurance pricing, benefits eligibility, triage/resource prioritization)
    -> "essential_services".
  - "biometric_id": identifying or categorizing people from biometric data.
  - Biometric routing: face recognition, face detection, or facial identification
    libraries/tools (e.g. face_recognition, dlib-based face matching, facial biometric
    matching) -> deployment_domain "biometric_id" and biometric_use true, even if the
    README doesn't explicitly use the word "biometric".
  - "general_consumer": consumer-facing apps and assistants with none of the above roles.
  - "other": general-purpose libraries and developer tools with no specific
    application domain, research code, and anything else. A library or toolkit
    built for a specific domain (e.g. credit scoring, resume screening, face
    recognition) takes that domain, not "other".
- data_sensitivity: "sensitive" = health, biometric, criminal, political, religious
  or union-affiliation data; "personal" = other data about identifiable people;
  "none" = no personal data.
- biometric_use: processes biometric data for identification or categorization.
- decision_autonomy: "human_in_loop" = a human approves each decision;
  "human_on_loop" = a human can monitor/override but doesn't approve each one;
  "fully_autonomous" = the documentation describes decisions taken with no human review.
- affected_population: "vulnerable_groups" = children, job seekers, patients,
  asylum seekers, elderly people or persons with disabilities.
- emotion_inference: infers emotion or intent from biometric or behavioral signals.
- social_scoring: scores/ranks individuals for general trustworthiness or
  eligibility across unrelated contexts.
- real_time_biometric_public: real-time biometric identification in publicly
  accessible spaces.
- human_oversight_mentioned: the documentation explicitly mentions human review,
  override or appeal mechanisms.
- transparency_mentioned: the documentation mentions telling end users they are
  interacting with an AI system.
- extraction_confidence: how much relevant information the text actually contained.
- evidence_snippets: for each field you set to a non-default value, a short quote or
  paraphrase of the text that justified it. Omit fields left at their default.

Return only JSON matching the response schema."""

RETRY_REMINDER = """\
Your previous response was rejected: {problem}
Return ONLY valid JSON that matches the response schema exactly, using only the
allowed enum values."""


def _response_schema() -> dict[str, Any]:
    """JSON schema for the Gemini call, generated from schema.py so the two can't drift."""
    properties: dict[str, Any] = {
        "system_purpose": {"type": "string", "maxLength": MAX_PURPOSE_CHARS},
    }
    for name, enum_cls in ENUM_FIELDS.items():
        properties[name] = {"type": "string", "enum": [e.value for e in enum_cls]}
    for name in BOOL_FIELDS:
        properties[name] = {"type": "boolean"}
    # Fixed optional keys rather than an open-ended map: structured output handles
    # declared properties more reliably. Converted back to the §5 mapping on parse.
    snippet_fields = sorted(FIELD_NAMES - {"evidence_snippets"})
    properties["evidence_snippets"] = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in snippet_fields},
    }
    required = sorted(FIELD_NAMES)
    return {"type": "object", "properties": properties, "required": required}


RESPONSE_SCHEMA = _response_schema()


def prepare_llm_text(text: str) -> tuple[str, bool]:
    """Return (copy to send to the LLM, was_truncated). The caller keeps the original."""
    cleaned = text.strip()
    if len(cleaned) <= MAX_INPUT_CHARS:
        return cleaned, False
    return cleaned[:MAX_INPUT_CHARS] + TRUNCATION_NOTICE, True


def _parse(raw: str | None) -> ExtractedFacts:
    if not raw:
        raise SchemaValidationError("empty response")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"invalid JSON ({exc.msg})") from None
    if not isinstance(data, dict):
        raise SchemaValidationError("top-level JSON value is not an object")
    snippets = data.get("evidence_snippets") or {}
    if not isinstance(snippets, dict):
        raise SchemaValidationError("evidence_snippets is not an object")
    data["evidence_snippets"] = {
        k: v for k, v in snippets.items() if isinstance(v, str) and v.strip()
    }
    facts = ExtractedFacts.from_dict(data)
    # §5: snippets only for fields the model moved off their absent-signal default.
    kept = {
        name: snippet
        for name, snippet in facts.evidence_snippets.items()
        if name not in ABSENT_DEFAULTS or getattr(facts, name) != ABSENT_DEFAULTS[name]
    }
    return replace(facts, evidence_snippets=kept)


def _call(client: Any, model: str, contents: str) -> str | None:
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_json_schema=RESPONSE_SCHEMA,
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = client.models.generate_content(model=model, contents=contents, config=config)
    except errors.APIError as exc:
        if exc.code == 429:
            message = (
                "The Gemini API rate limit or quota was reached. Wait and try again; "
                "the free tier also caps requests per day."
            )
        else:
            message = f"The Gemini API request failed (HTTP {exc.code}). Try again shortly."
        raise ExtractionAPIError(message, code=exc.code) from exc
    except Exception as exc:  # transport failures (timeouts, dropped connections)
        raise ExtractionAPIError(
            f"Couldn't reach the Gemini API ({type(exc).__name__}). "
            "Check your connection and try again."
        ) from exc
    return response.text


def _call_with_fallback(client: Any, models: Sequence[str], contents: str) -> tuple[str | None, str]:
    """Try each model in order, moving on only for quota/overload errors."""
    last_error: ExtractionAPIError | None = None
    for model in models:
        try:
            return _call(client, model, contents), model
        except ExtractionAPIError as exc:
            if exc.code not in FALLBACK_STATUS_CODES:
                raise
            last_error = exc
    if last_error is None:
        raise ValueError("models must not be empty")
    raise AllModelsUnavailableError(
        "Every configured Gemini model is rate-limited, out of quota or overloaded. "
        "Try again later; the free tier also caps requests per day.",
        code=last_error.code,
    ) from last_error


def make_client(api_key: str) -> Any:
    """A Gemini client for the given key (the server's, or a visitor's own)."""
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))


def _default_client() -> Any:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ExtractionAPIError("GEMINI_API_KEY is not set. Add it to your .env file.")
    return make_client(key)


def extract_facts(
    text: str, client: Any = None, models: Sequence[str] = MODEL_CHAIN
) -> ExtractedFacts:
    """Extract and validate facts from text. One retry on malformed or off-schema output."""
    return extract_with_details(text, client=client, models=models).facts


def extract_with_details(
    text: str, client: Any = None, models: Sequence[str] = MODEL_CHAIN
) -> ExtractionResult:
    """As extract_facts, but also returns the accepted raw response and the model used."""
    if not text or not text.strip():
        raise EmptyInputError("There's no text to analyze. Paste some documentation first.")
    llm_text, _ = prepare_llm_text(text)
    client = client or _default_client()

    raw, model = _call_with_fallback(client, models, llm_text)
    try:
        return ExtractionResult(_parse(raw), raw, model)
    except SchemaValidationError as first:
        problem = str(first)

    # Retry from the model that answered, so both attempts normally use the same model.
    retry_contents = f"{llm_text}\n\n---\n{RETRY_REMINDER.format(problem=problem)}"
    remaining = list(models)[list(models).index(model):]
    raw, model = _call_with_fallback(client, remaining, retry_contents)
    try:
        return ExtractionResult(_parse(raw), raw, model)
    except SchemaValidationError as second:
        raise MalformedExtractionError(
            "The model returned invalid output twice, so no classification was made "
            f"(last problem: {second}). Try again."
        ) from second
