"""End-to-end pipeline: fetch/clean → extract → rules → principles (Blueprint §4, §12 Phase 5).

Decoupled from Streamlit so it can be tested on its own. Errors from each stage
propagate unchanged (GitHubFetchError, ExtractionError subclasses) so the UI can show
the specific, actionable message each one carries (§8.1).

This module is the UI's only interface to the backend: app.py imports nothing else,
so the error types and quick-pick loading it needs are re-exported here.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import requests

from examples.quick_picks import QUICK_PICKS
from extractor import (  # noqa: F401  (error types re-exported for the UI)
    MAX_INPUT_CHARS,
    MODEL_CHAIN,
    AllModelsUnavailableError,
    InvalidAPIKeyError,
    EmptyInputError,
    ExtractionAPIError,
    ExtractionError,
    ExtractionResult,
    MalformedExtractionError,
    extract_with_details,
    make_client,
    prepare_llm_text,
)
from github_fetch import (  # noqa: F401  (error types re-exported for the UI)
    FetchedReadme,
    GitHubFetchError,
    InvalidRepoURLError,
    NetworkError,
    RateLimitedError,
    ReadmeNotFoundError,
    RepoNotFoundError,
    fetch_readme,
)
from principles import PrincipleFlag, evaluate_principles
from rules import (  # noqa: F401
    RULES,
    Classification,
    RiskTier,
    RuleTrace,
    RuleTraceEntry,
    classify,
    classify_with_trace,
)
from schema import DISPLAY_ORDER, SCHEMA_VERSION, ExtractedFacts, upgrade_facts_dict  # noqa: F401

FIXTURE_DIR = Path(__file__).resolve().parent / "tests" / "fixtures"


@dataclass(frozen=True)
class AnalysisResult:
    source_kind: Literal["github", "text"]
    source_label: str  # repo "owner/repo" or "Pasted text"
    source_text: str  # full, untruncated text, for the raw-source toggle (§6.4, §8)
    readme: FetchedReadme | None
    llm_input_truncated: bool
    extraction: ExtractionResult
    classification: Classification
    principles: list[PrincipleFlag]
    # Schema the facts were extracted under. Below SCHEMA_VERSION means a fixture
    # recorded before schema v2: its v2 fields hold absent defaults, not extractions.
    schema_version: int = SCHEMA_VERSION


def clean_pasted_text(text: str) -> str:
    """§4 paste path: use as-is, strip excess whitespace."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def _analyze(
    kind: Literal["github", "text"],
    label: str,
    text: str,
    readme: FetchedReadme | None,
    client: Any,
) -> AnalysisResult:
    return _assemble(kind, label, text, readme, extract_with_details(text, client=client))


def _assemble(
    kind: Literal["github", "text"],
    label: str,
    text: str,
    readme: FetchedReadme | None,
    extraction: ExtractionResult,
    schema_version: int = SCHEMA_VERSION,
) -> AnalysisResult:
    _, truncated = prepare_llm_text(text)
    return AnalysisResult(
        source_kind=kind,
        source_label=label,
        source_text=text,
        readme=readme,
        llm_input_truncated=truncated,
        extraction=extraction,
        classification=classify(extraction.facts),
        principles=evaluate_principles(extraction.facts),
        schema_version=schema_version,
    )


def _client_for(client: Any, api_key: str | None) -> Any:
    """An explicit client wins; else a visitor's own key; else the server key (default)."""
    if client is None and api_key:
        return make_client(api_key)
    return client


def analyze_github(
    url: str,
    client: Any = None,
    session: requests.Session | None = None,
    api_key: str | None = None,
) -> AnalysisResult:
    readme = fetch_readme(url, session=session)
    return _analyze(
        "github", f"{readme.owner}/{readme.repo}", readme.text, readme, _client_for(client, api_key)
    )


def analyze_text(text: str, client: Any = None, api_key: str | None = None) -> AnalysisResult:
    return _analyze(
        "text", "Pasted text", clean_pasted_text(text or ""), None, _client_for(client, api_key)
    )


class NotRecordedError(LookupError):
    """An example's fixture hasn't been recorded yet (see scripts/record_all.py)."""


def fixture_path(stem: str) -> Path:
    return FIXTURE_DIR / f"{stem}.json"


def facts_from_record(record: dict[str, Any]) -> tuple[ExtractedFacts, int]:
    """Parse a fixture's facts, upgrading an older-schema record. Returns (facts, version).

    Fixtures written before schema v2 carry no schema_version and lack the v2 fields;
    those are filled with their absent defaults (blueprint §5, schema v2 additions).
    """
    data, legacy = upgrade_facts_dict(record["extracted_facts"])
    # A record missing v2 fields is v1 whatever it claims; else trust its stated version.
    version = 1 if legacy else int(record.get("schema_version", 1))
    return ExtractedFacts.from_dict(data), version


def example_status(stem: str) -> Literal["recorded", "older_schema", "not_recorded"]:
    path = fixture_path(stem)
    if not path.exists():
        return "not_recorded"
    record = json.loads(path.read_text())
    return "recorded" if int(record.get("schema_version", 1)) >= SCHEMA_VERSION else "older_schema"


def load_example(stem: str, label: str | None = None) -> AnalysisResult:
    """Build a result from a recorded fixture: no network, no Gemini call.

    Rules and principles are re-run on the recorded facts, so the result always
    reflects the current rule table. `label` overrides the source label shown in the
    UI (e.g. a Case Library title). Raises NotRecordedError if there is no fixture.
    """
    path = fixture_path(stem)
    if not path.exists():
        raise NotRecordedError(f"The example '{stem}' has not been recorded yet.")
    record = json.loads(path.read_text())
    facts, version = facts_from_record(record)
    extraction = ExtractionResult(
        facts=facts,
        raw_response=record["raw_model_response"],
        model=record["model"],
    )
    if record.get("source_kind") == "text":
        return _assemble(
            "text", label or "Pasted text (sample)", record["source_text"], None, extraction, version
        )
    owner, repo, branch, filename = record["source_url"].split("/")[3:7]
    readme = FetchedReadme(owner, repo, branch, filename, record["source_url"], record["readme_text"])
    return _assemble("github", label or f"{owner}/{repo}", readme.text, readme, extraction, version)


def quick_pick_labels() -> list[str]:
    return [label for label, _ in QUICK_PICKS]


def quick_pick_status(label: str) -> Literal["recorded", "older_schema", "not_recorded"]:
    return example_status(dict(QUICK_PICKS)[label])


def analyze_quick_pick(label: str) -> AnalysisResult:
    """A quick-pick's recorded result (see load_example)."""
    return load_example(dict(QUICK_PICKS)[label])


def rule_table() -> list[dict[str, Any]]:
    """The ordered rule table (first match wins), for display in the UI."""
    return [
        {
            "number": rule.number,
            "condition": rule.condition_text,
            "tier": rule.tier.value,
            "provision": rule.provision,
        }
        for rule in RULES
    ]
