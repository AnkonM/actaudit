"""End-to-end pipeline: fetch/clean → extract → rules → principles (Blueprint §4, §12 Phase 5).

Decoupled from Streamlit so it can be tested on its own. Errors from each stage
propagate unchanged (GitHubFetchError, ExtractionError subclasses) so the UI can show
the specific, actionable message each one carries (§8.1).
"""
import re
from dataclasses import dataclass
from typing import Any, Literal

import requests

from extractor import ExtractionResult, extract_with_details, prepare_llm_text
from github_fetch import FetchedReadme, fetch_readme
from principles import PrincipleFlag, evaluate_principles
from rules import Classification, classify


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
    extraction = extract_with_details(text, client=client)
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
    )


def analyze_github(
    url: str, client: Any = None, session: requests.Session | None = None
) -> AnalysisResult:
    readme = fetch_readme(url, session=session)
    return _analyze("github", f"{readme.owner}/{readme.repo}", readme.text, readme, client)


def analyze_text(text: str, client: Any = None) -> AnalysisResult:
    return _analyze("text", "Pasted text", clean_pasted_text(text or ""), None, client)
