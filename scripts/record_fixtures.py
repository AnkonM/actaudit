"""Manual Phase 3 check: run live extraction on real READMEs and save fixtures.

Usage: python scripts/record_fixtures.py
Writes tests/fixtures/<owner>__<repo>.json with the source README and extracted facts,
so extraction behavior stays reproducible if the live API changes (blueprint §12).
"""
import json
import sys
import time
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from extractor import (  # noqa: E402
    ExtractionAPIError,
    extract_with_details,
    prepare_llm_text,
)
from github_fetch import fetch_readme  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# (repo URL, what it is, domain we expect the routing to produce)
REPOS = [
    ("https://github.com/ageitgey/face_recognition", "face recognition library", "biometric_id"),
    ("https://github.com/OmkarPathak/pyresparser", "resume parser (hiring)", "hiring"),
    ("https://github.com/ayhandis/creditR", "credit risk scoring package", "essential_services"),
    ("https://github.com/RasaHQ/rasa", "chatbot framework", "general_consumer or other"),
    ("https://github.com/arnoweng/CheXNet", "clinical: chest X-ray disease detection", "other"),
    ("https://github.com/Vinaya-Sharma/TriageAI", "healthcare access: 911 dispatch triage", "essential_services"),
    ("https://github.com/DataSorcerer/Predicting-Insurance-Premium", "healthcare access: medical insurance premium prediction", "essential_services"),
    ("https://github.com/oarriaga/face_classification", "real-time emotion + gender classification", "biometric_id or other"),
    ("https://github.com/twitter/the-algorithm", "social media recommendation algorithm", "content_moderation or general_consumer"),
    ("https://github.com/psf/requests", "plain HTTP utility library", "other"),
]


def _jsonable(value):
    return value.value if isinstance(value, Enum) else value


def _extract_with_backoff(text: str, attempts: int = 4):
    """Retry transient API failures (e.g. 503) here, in the script, not in extractor.py."""
    for attempt in range(1, attempts + 1):
        try:
            return extract_with_details(text)
        except ExtractionAPIError as exc:
            if attempt == attempts:
                raise
            wait = 10 * attempt
            print(f"  API error ({exc}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)


def main() -> None:
    load_dotenv()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for url, label, expected in REPOS:
        readme = fetch_readme(url)
        path = FIXTURE_DIR / f"{readme.owner}__{readme.repo}.json"
        if path.exists():
            print(f"skip {path.name} (already recorded)", file=sys.stderr)
            continue
        result = _extract_with_backoff(readme.text)
        facts = result.facts
        _, truncated = prepare_llm_text(readme.text)
        facts_dict = {k: _jsonable(v) for k, v in asdict(facts).items()}
        record = {
            "source_url": readme.source_url,
            "label": label,
            "expected_domain": expected,
            "model": result.model,
            "recorded_on": date.today().isoformat(),
            "llm_input_truncated": truncated,
            "readme_text": readme.text,
            "raw_model_response": result.raw_response,
            "extracted_facts": facts_dict,
        }
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"repo": f"{readme.owner}/{readme.repo}", "label": label,
                          "expected_domain": expected, "model": result.model,
                          "truncated": truncated,
                          "facts": facts_dict}, ensure_ascii=False))


if __name__ == "__main__":
    main()
