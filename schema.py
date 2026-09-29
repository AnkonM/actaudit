"""Extraction schema — the LLM output contract (Blueprint Section 5).

The rule engine depends on these exact field names and enum values. If this file
changes, rules.py must be updated in the same commit.

This schema holds observable facts only. It must never contain a risk tier or any
judgment field (Blueprint Section 1.1).

Schema v2 (blueprint §5, "Schema v2 additions") appends ten capability fields for the
experiment tabs. They come after evidence_snippets, each defaulting to its absent-signal
value, so v1 fact-sets (older fixtures) can be upgraded with upgrade_facts_dict().
"""
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Mapping


class SchemaValidationError(ValueError):
    """Raised when a fact-set violates the Section 5 contract."""


class DeploymentDomain(str, Enum):
    HIRING = "hiring"
    ESSENTIAL_SERVICES = "essential_services"  # Annex III point 5: credit, benefits, insurance, triage
    LAW_ENFORCEMENT = "law_enforcement"
    BIOMETRIC_ID = "biometric_id"
    EDUCATION = "education"
    CONTENT_MODERATION = "content_moderation"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    MIGRATION_ASYLUM_BORDER = "migration_asylum_border"
    GENERAL_CONSUMER = "general_consumer"
    OTHER = "other"


class DataSensitivity(str, Enum):
    NONE = "none"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"


class DecisionAutonomy(str, Enum):
    HUMAN_IN_LOOP = "human_in_loop"
    HUMAN_ON_LOOP = "human_on_loop"
    FULLY_AUTONOMOUS = "fully_autonomous"


class AffectedPopulation(str, Enum):
    GENERAL_PUBLIC = "general_public"
    VULNERABLE_GROUPS = "vulnerable_groups"


class TargetType(str, Enum):
    """Factual category of what the system predicts or optimises (not a judgment)."""
    COST_OR_SPENDING = "cost_or_spending"
    ARRESTS_OR_POLICE_CONTACT = "arrests_or_police_contact"
    ENGAGEMENT_OR_CLICKS = "engagement_or_clicks"
    PAST_HUMAN_DECISIONS = "past_human_decisions"
    DIRECT_OUTCOME = "direct_outcome"
    OTHER = "other"
    UNKNOWN = "unknown"


class SyntheticMediaType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TEXT = "text"


class ExtractionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SCHEMA_VERSION = 2  # 1 = original §5 table; 2 = with the experiment-tab fields

MAX_PURPOSE_CHARS = 200
MAX_TARGET_CHARS = 200

ENUM_FIELDS: dict[str, type[Enum]] = {
    "deployment_domain": DeploymentDomain,
    "data_sensitivity": DataSensitivity,
    "decision_autonomy": DecisionAutonomy,
    "affected_population": AffectedPopulation,
    "extraction_confidence": ExtractionConfidence,
    "target_type": TargetType,
}

# Fields holding a list of enum values (stored as a tuple, in the order given).
LIST_ENUM_FIELDS: dict[str, type[Enum]] = {
    "synthetic_media_types": SyntheticMediaType,
}

BOOL_FIELDS: tuple[str, ...] = (
    "biometric_use",
    "emotion_inference",
    "social_scoring",
    "real_time_biometric_public",
    "human_oversight_mentioned",
    "transparency_mentioned",
    "generates_synthetic_media",
    "impersonation_capable",
    "output_marking_mentioned",
    "consent_safeguards_mentioned",
    "military_defence_use",
    "robustness_testing_mentioned",
    "failsafe_mentioned",
)

# Fields added in schema v2, in dataclass order.
V2_FIELDS: tuple[str, ...] = (
    "target_variable",
    "target_type",
    "generates_synthetic_media",
    "synthetic_media_types",
    "impersonation_capable",
    "output_marking_mentioned",
    "consent_safeguards_mentioned",
    "military_defence_use",
    "robustness_testing_mentioned",
    "failsafe_mentioned",
)


@dataclass(frozen=True)
class ExtractedFacts:
    system_purpose: str
    deployment_domain: DeploymentDomain
    data_sensitivity: DataSensitivity
    biometric_use: bool
    decision_autonomy: DecisionAutonomy
    affected_population: AffectedPopulation
    emotion_inference: bool
    social_scoring: bool
    real_time_biometric_public: bool
    human_oversight_mentioned: bool
    transparency_mentioned: bool
    extraction_confidence: ExtractionConfidence
    evidence_snippets: Mapping[str, str] = field(default_factory=dict)
    # --- schema v2 (defaults are the absent-signal values, blueprint §5) ---
    target_variable: str = ""
    target_type: TargetType = TargetType.UNKNOWN
    generates_synthetic_media: bool = False
    synthetic_media_types: tuple[SyntheticMediaType, ...] = ()
    impersonation_capable: bool = False
    output_marking_mentioned: bool = False
    consent_safeguards_mentioned: bool = False
    military_defence_use: bool = False
    robustness_testing_mentioned: bool = False
    failsafe_mentioned: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.system_purpose, str):
            raise SchemaValidationError("system_purpose must be a string")
        if len(self.system_purpose) > MAX_PURPOSE_CHARS:
            raise SchemaValidationError(
                f"system_purpose exceeds {MAX_PURPOSE_CHARS} characters"
            )
        if not isinstance(self.target_variable, str):
            raise SchemaValidationError("target_variable must be a string")
        if len(self.target_variable) > MAX_TARGET_CHARS:
            raise SchemaValidationError(
                f"target_variable exceeds {MAX_TARGET_CHARS} characters"
            )
        for name, enum_cls in ENUM_FIELDS.items():
            if not isinstance(getattr(self, name), enum_cls):
                raise SchemaValidationError(f"{name} must be a {enum_cls.__name__}")
        for name, enum_cls in LIST_ENUM_FIELDS.items():
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(isinstance(v, enum_cls) for v in values):
                raise SchemaValidationError(f"{name} must be a tuple of {enum_cls.__name__}")
            if len(set(values)) != len(values):
                raise SchemaValidationError(f"{name} contains duplicates")
        for name in BOOL_FIELDS:
            if type(getattr(self, name)) is not bool:
                raise SchemaValidationError(f"{name} must be a bool")
        if not isinstance(self.evidence_snippets, Mapping):
            raise SchemaValidationError("evidence_snippets must be a mapping")
        for key, snippet in self.evidence_snippets.items():
            if key not in FIELD_NAMES or key == "evidence_snippets":
                raise SchemaValidationError(f"evidence_snippets has unknown field {key!r}")
            if not isinstance(snippet, str):
                raise SchemaValidationError(f"evidence_snippets[{key!r}] must be a string")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExtractedFacts":
        """Build from raw JSON-like data, converting enum strings. Rejects anything off-contract."""
        unknown = set(data) - FIELD_NAMES
        if unknown:
            raise SchemaValidationError(f"unknown fields: {sorted(unknown)}")
        missing = FIELD_NAMES - set(data) - {"evidence_snippets"}
        if missing:
            raise SchemaValidationError(f"missing fields: {sorted(missing)}")
        values = dict(data)
        for name, enum_cls in ENUM_FIELDS.items():
            try:
                values[name] = enum_cls(values[name])
            except ValueError:
                raise SchemaValidationError(
                    f"{name}={values[name]!r} is not one of "
                    f"{[e.value for e in enum_cls]}"
                ) from None
        for name, enum_cls in LIST_ENUM_FIELDS.items():
            raw = values[name]
            if not isinstance(raw, (list, tuple)):
                raise SchemaValidationError(f"{name} must be a list")
            converted: list[Enum] = []
            for item in raw:
                try:
                    value = enum_cls(item)
                except ValueError:
                    raise SchemaValidationError(
                        f"{name} item {item!r} is not one of {[e.value for e in enum_cls]}"
                    ) from None
                if value not in converted:  # repeated values carry no extra fact
                    converted.append(value)
            values[name] = tuple(converted)
        return cls(**values)


FIELD_NAMES: frozenset[str] = frozenset(f.name for f in fields(ExtractedFacts))


# Values used when the text has no signal for a field (blueprint §5.1). Lower-risk,
# except decision_autonomy: human_in_loop is a positive claim that feeds Rule 7
# (Minimal-Risk), so silence must not produce it.
ABSENT_DEFAULTS: dict[str, Any] = {
    "deployment_domain": DeploymentDomain.OTHER,
    "data_sensitivity": DataSensitivity.NONE,
    "decision_autonomy": DecisionAutonomy.HUMAN_ON_LOOP,
    "affected_population": AffectedPopulation.GENERAL_PUBLIC,
    "target_variable": "",
    "target_type": TargetType.UNKNOWN,
    "synthetic_media_types": (),
    **{name: False for name in BOOL_FIELDS},
}

# Order in which the UI lists the facts: v2 fields sit next to the v1 fields they
# relate to, rather than at the end where the dataclass keeps them.
DISPLAY_ORDER: tuple[str, ...] = (
    "system_purpose",
    "deployment_domain",
    "target_variable",
    "target_type",
    "data_sensitivity",
    "biometric_use",
    "decision_autonomy",
    "affected_population",
    "emotion_inference",
    "social_scoring",
    "real_time_biometric_public",
    "generates_synthetic_media",
    "synthetic_media_types",
    "impersonation_capable",
    "military_defence_use",
    "human_oversight_mentioned",
    "transparency_mentioned",
    "output_marking_mentioned",
    "consent_safeguards_mentioned",
    "robustness_testing_mentioned",
    "failsafe_mentioned",
    "extraction_confidence",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_default(v) for v in value]
    return value


def upgrade_facts_dict(data: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Fill v2 fields missing from an older (v1) fact dict with their absent defaults.

    Returns (upgraded dict, was_legacy). Used only for recorded fixtures, so the app
    works with fixtures recorded before schema v2; live extraction stays strict.
    """
    upgraded = dict(data)
    missing = [name for name in V2_FIELDS if name not in upgraded]
    for name in missing:
        upgraded[name] = _json_default(ABSENT_DEFAULTS[name])
    return upgraded, bool(missing)
