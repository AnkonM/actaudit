"""Record live extractions as fixtures in tests/fixtures/ (blueprint §12 Phase 3, §15.6).

Usage:
    python scripts/record_fixtures.py [--set quick_picks|synthetic|cases|legacy|all]
                                      [--rerecord-older-schema] [--pace SECONDS]

Each fixture stores the source text and the extracted facts, so extraction behaviour
stays reproducible if the live API changes. The script is safe to rerun at any time:

- fixtures that already exist are skipped (with --rerecord-older-schema, fixtures
  recorded under an older SCHEMA_VERSION are re-recorded from their stored text);
- requests are paced (--pace, default 6 s) to respect free-tier per-minute limits;
- when every model is out of quota it stops cleanly and prints the command to resume;
- a re-recording that would change the fixture's tier or deciding rule does not
  replace it: the new output goes to tests/fixtures/_candidates/ for review
  (blueprint §14, experiment-tabs decisions).

Only GEMINI_API_KEY from the environment / .env is used, never a visitor's key.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from examples.quick_picks import EXAMPLE_SETS, QUICK_PICKS  # noqa: E402
from extractor import (  # noqa: E402
    AllModelsUnavailableError,
    ExtractionAPIError,
    InvalidAPIKeyError,
    extract_with_details,
    prepare_llm_text,
)
from github_fetch import fetch_readme, parse_repo_url  # noqa: E402
from pipeline import clean_pasted_text, facts_from_record  # noqa: E402
from rules import classify  # noqa: E402
from schema import SCHEMA_VERSION  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures"
CANDIDATE_DIR = FIXTURE_DIR / "_candidates"
CASES_FILE = ROOT / "data" / "cases" / "cases.json"
RESUME_HINT = "python scripts/record_all.py"

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
    # Tab 3 (synthetic media) examples
    ("https://github.com/CorentinJ/Real-Time-Voice-Cloning", "synthetic media: voice cloning", "other or general_consumer; generates audio, impersonation"),
    ("https://github.com/deepfakes/faceswap", "synthetic media: face swapping", "other or general_consumer; generates image/video, impersonation"),
    ("https://github.com/huggingface/pytorch-image-models", "non-generative image classification models", "other; no synthetic media"),
]

# Fictional pasted-text descriptions, added so the quick-picks cover every tier
# (no clean public repo exists for these). (fixture stem, label, expected rule, text)
TEXT_EXAMPLES = [
    (
        "text__classroom_emotion_tracker",
        "fictional: classroom emotion recognition",
        "Prohibited, rule 3 (emotion_inference + education)",
        "ClassPulse is a classroom analytics tool for schools. A webcam in each classroom "
        "continuously analyses students' facial expressions to infer their emotions, such "
        "as boredom, confusion and engagement, and sends teachers a live engagement score "
        "for every pupil. Scores are logged to each student's record.",
    ),
    (
        "text__tab_grouping_extension",
        "fictional: on-device tab grouping browser extension",
        "Minimal-Risk, rule 7 (general_consumer + no data + human_in_loop)",
        "TidyTabs is a free browser extension for everyday users that suggests how to "
        "group your open tabs by topic. It runs entirely on your device and collects no "
        "personal data. It never acts on its own: every suggested grouping is shown to "
        "you and is only applied when you click Accept.",
    ),
    (
        "text__military_target_recognition",
        "fictional: military drone target recognition",
        "Out of scope, rule 0 (military_defence_use)",
        "SentinelView is an object-recognition module developed under contract for a "
        "national defence ministry and used exclusively in the ministry's military "
        "surveillance drones. It analyses live drone video to detect and classify "
        "military vehicles and personnel in a designated area of operations, and "
        "highlights candidate targets on the operator's screen. A trained operator "
        "reviews every highlighted target before any action is taken. SentinelView is "
        "not sold or licensed for civilian use.",
    ),
]


@dataclass(frozen=True)
class Source:
    stem: str
    kind: str  # "github" | "text"
    value: str  # repo URL or the text itself
    label: str
    expected: str


class QuotaExhausted(Exception):
    """Every model is out of quota (HTTP 429): stop and resume later."""


def _repo_stem(url: str) -> str:
    owner, repo = parse_repo_url(url)
    return f"{owner}__{repo}"


def _case_sources() -> list[Source]:
    if not CASES_FILE.exists():
        return []
    cases = json.loads(CASES_FILE.read_text())["cases"]
    return [
        Source(c["fixture"], "text", c["system_description"], f"case: {c['title']}", "see cases.json")
        for c in cases
    ]


def all_sources() -> dict[str, Source]:
    sources = {
        _repo_stem(url): Source(_repo_stem(url), "github", url, label, expected)
        for url, label, expected in REPOS
    }
    for stem, label, expected, text in TEXT_EXAMPLES:
        sources[stem] = Source(stem, "text", text, label, expected)
    for source in _case_sources():
        sources[source.stem] = source
    return sources


def set_stems(name: str) -> list[str]:
    """Fixture stems in one recording set, in recording-priority order."""
    quick = [stem for _, stem in QUICK_PICKS]
    synthetic = [stem for _, stem in EXAMPLE_SETS["synthetic_media"]]
    cases = [s.stem for s in _case_sources()]
    if name == "quick_picks":
        return quick
    if name == "synthetic":
        return synthetic
    if name == "cases":
        return cases
    if name == "legacy":  # every other known fixture (not a quick-pick, example or case)
        taken = set(quick) | set(synthetic) | set(cases)
        return [stem for stem in all_sources() if stem not in taken]
    if name == "all":
        return quick + synthetic + cases + set_stems("legacy")
    raise ValueError(f"unknown set {name!r}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


def _existing_version(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(json.loads(path.read_text()).get("schema_version", 1))


def needs_recording(path: Path, rerecord_older: bool) -> bool:
    version = _existing_version(path)
    if version is None:
        return True
    return rerecord_older and version < SCHEMA_VERSION


def extract_with_backoff(text: str, client: Any = None, attempts: int = 4,
                         sleep: Callable[[float], None] = time.sleep):
    """Retry transient failures (overload/deadline) here, in the script; stop on quota."""
    for attempt in range(1, attempts + 1):
        try:
            return extract_with_details(text, client=client)
        except InvalidAPIKeyError:
            raise
        except AllModelsUnavailableError as exc:
            if exc.quota_exhausted:
                raise QuotaExhausted(str(exc)) from exc
            if attempt == attempts:
                raise
            wait = 20 * attempt
            print(f"  models overloaded; retrying in {wait}s", file=sys.stderr)
            sleep(wait)
        except ExtractionAPIError as exc:
            if attempt == attempts:
                raise
            wait = 10 * attempt
            print(f"  API error ({exc}); retrying in {wait}s", file=sys.stderr)
            sleep(wait)


def _tier_rule(record: dict[str, Any]) -> tuple[str, int]:
    facts, _ = facts_from_record(record)
    c = classify(facts)
    return c.tier.value, c.rule_number


def record_one(source: Source, path: Path, client: Any = None,
               fetch: Callable = fetch_readme,
               sleep: Callable[[float], None] = time.sleep) -> str:
    """Record one fixture. Returns "recorded", "candidate" or raises QuotaExhausted."""
    old = json.loads(path.read_text()) if path.exists() else None
    if source.kind == "github":
        if old is not None:  # re-record from the stored README so only the schema changes
            src = {"source_url": old["source_url"], "readme_text": old["readme_text"]}
        else:
            readme = fetch(source.value)
            src = {"source_url": readme.source_url, "readme_text": readme.text}
        text = src["readme_text"]
    else:
        text = clean_pasted_text(source.value)  # same cleaning as the app's paste path
        src = {"source_kind": "text", "source_text": text}

    result = extract_with_backoff(text, client=client, sleep=sleep)
    _, truncated = prepare_llm_text(text)
    facts_dict = {k: _jsonable(v) for k, v in asdict(result.facts).items()}
    record = {
        **src,
        "label": source.label,
        "expected_domain": source.expected,
        "schema_version": SCHEMA_VERSION,
        "model": result.model,
        "recorded_on": date.today().isoformat(),
        "llm_input_truncated": truncated,
        "raw_model_response": result.raw_response,
        "extracted_facts": facts_dict,
    }
    outcome = "recorded"
    if old is not None and _tier_rule(old) != _tier_rule(record):
        # Keep the approved fixture; park the new output for review (blueprint §14).
        CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
        path = CANDIDATE_DIR / path.name
        record["replaces"] = {"tier_rule_before": list(_tier_rule(old)),
                              "tier_rule_after": list(_tier_rule(record))}
        outcome = "candidate"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    tier, rule = _tier_rule(record)
    print(json.dumps({"fixture": source.stem, "outcome": outcome, "model": result.model,
                      "tier": tier, "rule": rule}, ensure_ascii=False))
    return outcome


def run(set_name: str, rerecord_older: bool = False, pace: float = 6.0, client: Any = None,
        fetch: Callable = fetch_readme, sleep: Callable[[float], None] = time.sleep) -> dict[str, list[str]]:
    """Record every pending fixture in a set. Returns stems by outcome."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    sources = all_sources()
    outcomes: dict[str, list[str]] = {"recorded": [], "candidate": [], "skipped": [],
                                      "failed": [], "pending": []}
    stems = set_stems(set_name)
    called = False
    for i, stem in enumerate(stems):
        path = FIXTURE_DIR / f"{stem}.json"
        if not needs_recording(path, rerecord_older):
            outcomes["skipped"].append(stem)
            continue
        if called and pace:
            sleep(pace)
        called = True
        try:
            outcomes[record_one(sources[stem], path, client=client, fetch=fetch, sleep=sleep)].append(stem)
        except QuotaExhausted as exc:
            outcomes["pending"] = [s for s in stems[i:]
                                   if needs_recording(FIXTURE_DIR / f"{s}.json", rerecord_older)]
            print(f"Quota exhausted ({exc}). Stopping cleanly; {len(outcomes['pending'])} "
                  f"fixture(s) pending. Resume later with: {RESUME_HINT}", file=sys.stderr)
            break
        except InvalidAPIKeyError:
            raise
        except Exception as exc:  # one bad source (e.g. README moved) shouldn't stop the set
            print(f"  failed {stem}: {type(exc).__name__}: {exc}", file=sys.stderr)
            outcomes["failed"].append(stem)
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", default="quick_picks",
                        choices=["quick_picks", "synthetic", "cases", "legacy", "all"])
    parser.add_argument("--rerecord-older-schema", action="store_true",
                        help=f"re-record fixtures recorded before schema v{SCHEMA_VERSION}")
    parser.add_argument("--pace", type=float, default=6.0, help="seconds between API calls")
    args = parser.parse_args(argv)
    load_dotenv()
    outcomes = run(args.set, args.rerecord_older_schema, args.pace)
    print(json.dumps({k: v for k, v in outcomes.items() if v}, indent=2), file=sys.stderr)
    return 3 if outcomes["pending"] else 0


if __name__ == "__main__":
    sys.exit(main())
