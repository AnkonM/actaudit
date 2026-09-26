"""Extraction schema — the LLM output contract (Blueprint Section 5).

The rule engine depends on these exact field names and enum values. If this file
changes, rules.py must be updated in the same commit.

This schema holds observable facts only. It must never contain a risk tier or any
judgment field (Blueprint Section 1.1).
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


class ExtractionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


MAX_PURPOSE_CHARS = 200

ENUM_FIELDS: dict[str, type[Enum]] = {
    "deployment_domain": DeploymentDomain,
    "data_sensitivity": DataSensitivity,
    "decision_autonomy": DecisionAutonomy,
    "affected_population": AffectedPopulation,
    "extraction_confidence": ExtractionConfidence,
}

BOOL_FIELDS: tuple[str, ...] = (
    "biometric_use",
    "emotion_inference",
    "social_scoring",
    "real_time_biometric_public",
    "human_oversight_mentioned",
    "transparency_mentioned",
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

    def __post_init__(self) -> None:
        if not isinstance(self.system_purpose, str):
            raise SchemaValidationError("system_purpose must be a string")
        if len(self.system_purpose) > MAX_PURPOSE_CHARS:
            raise SchemaValidationError(
                f"system_purpose exceeds {MAX_PURPOSE_CHARS} characters"
            )
        for name, enum_cls in ENUM_FIELDS.items():
            if not isinstance(getattr(self, name), enum_cls):
                raise SchemaValidationError(f"{name} must be a {enum_cls.__name__}")
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
        return cls(**values)


FIELD_NAMES: frozenset[str] = frozenset(f.name for f in fields(ExtractedFacts))
