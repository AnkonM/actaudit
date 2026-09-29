"""Robustness study of ActAudit itself (blueprint §15.4, Tab 7B).

Usage: python scripts/robustness_study.py [--pace SECONDS] [--reference-model MODEL]

For each subject in analysis/robustness.py (5 fixture READMEs spanning the tiers) it
records one extraction per perturbation into data/robustness/<subject>__<run>.json:
- model swap: the unmodified text on every model in MODEL_CHAIN (no fallback); the
  reference model's run is the baseline;
- information loss: truncation to 4,000 and 2,000 characters, and removal of the
  section most likely to describe intended use (reference model);
- adversarial injection: a false compliance claim and an instruction to set every
  boolean to false, inserted after the first paragraph (reference model).

Resumable: existing run files are skipped. A perturbation that leaves the text
unchanged (e.g. truncating a short text) is recorded as not applicable with no API call.
Quota-aware: when a model returns HTTP 429 it is retired for this run and its remaining
runs stay pending; the script carries on with the other models, then exits cleanly
with the command to resume. Only GEMINI_API_KEY from the environment / .env is used.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from analysis import robustness as rb  # noqa: E402
from extractor import (  # noqa: E402
    MODEL_CHAIN,
    AllModelsUnavailableError,
    ExtractionAPIError,
    InvalidAPIKeyError,
    MalformedExtractionError,
    extract_with_details,
)
from rules import classify  # noqa: E402
from schema import SCHEMA_VERSION, ExtractedFacts  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures"
RESUME_HINT = "python scripts/record_all.py"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


def subject_text(stem: str, fixture_dir: Path = FIXTURE_DIR) -> str:
    record = json.loads((fixture_dir / f"{stem}.json").read_text())
    return record.get("readme_text") or record["source_text"]


def planned_runs(reference: str, models: tuple[str, ...] = MODEL_CHAIN) -> list[tuple[str, str]]:
    """(perturbation, model) in recording order: baseline first, then the other models,
    then the text perturbations on the reference model."""
    order = [(rb.model_perturbation(reference), reference)]
    order += [(rb.model_perturbation(m), m) for m in models if m != reference]
    order += [(p, reference) for p in rb.TEXT_PERTURBATIONS]
    return order


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")


def _baseline_facts(stem: str, reference: str, runs_dir: Path) -> ExtractedFacts | None:
    runs = rb.load_runs(runs_dir)
    base = runs.get((stem, rb.model_perturbation(reference)))
    return base.facts if base and base.status == rb.OK else None


def run(reference: str = MODEL_CHAIN[0], pace: float = 8.0, client: Any = None,
        runs_dir: Path = rb.RUNS_DIR, fixture_dir: Path = FIXTURE_DIR,
        sleep: Callable[[float], None] = time.sleep,
        subjects: list[tuple[str, str]] = rb.SUBJECTS) -> dict[str, list[str]]:
    outcomes: dict[str, list[str]] = {"recorded": [], "not_applicable": [], "malformed": [],
                                      "skipped": [], "pending": [], "failed": []}
    retired: set[str] = set()
    called = False
    for stem, _ in subjects:
        original = subject_text(stem, fixture_dir)
        for perturbation, model in planned_runs(reference):
            path = rb.run_path(stem, perturbation, runs_dir)
            name = f"{stem}::{perturbation}"
            if path.exists():
                outcomes["skipped"].append(name)
                continue
            if perturbation.startswith("model:"):
                text, note = original, None
            else:
                text, note = rb.perturb(original, perturbation)
            base = {"subject": stem, "perturbation": perturbation, "reference_model": reference,
                    "schema_version": SCHEMA_VERSION,
                    "recorded_on": date.today().isoformat(), "input_chars": len(text), "note": note}
            if text == original and not perturbation.startswith("model:"):
                _write(path, {**base, "status": rb.NOT_APPLICABLE, "model": None, "facts": None,
                              "note": "the perturbation leaves this text unchanged"})
                outcomes["not_applicable"].append(name)
                continue
            if model in retired:
                outcomes["pending"].append(name)
                continue
            if called and pace:
                sleep(pace)
            called = True
            try:
                result = _extract(text, client, model, sleep)
            except MalformedExtractionError as exc:
                _write(path, {**base, "status": rb.MALFORMED, "model": model, "facts": None,
                              "error": str(exc)})
                outcomes["malformed"].append(name)
                continue
            except AllModelsUnavailableError as exc:
                if exc.quota_exhausted:
                    retired.add(model)
                    print(f"  {model} is out of quota; its remaining runs stay pending", file=sys.stderr)
                    outcomes["pending"].append(name)
                else:
                    outcomes["failed"].append(name)  # overloaded after retries: rerun later
                continue
            except InvalidAPIKeyError:
                raise
            except ExtractionAPIError as exc:
                print(f"  failed {name}: {exc}", file=sys.stderr)
                outcomes["failed"].append(name)
                continue
            facts = {k: _jsonable(v) for k, v in asdict(result.facts).items()}
            c = classify(result.facts)
            is_baseline = perturbation == rb.model_perturbation(reference)
            baseline = None if is_baseline else _baseline_facts(stem, reference, runs_dir)
            _write(path, {**base, "status": rb.OK, "model": result.model, "tier": c.tier.value,
                          "rule": c.rule_number, "facts": facts,
                          # Also recomputed by analysis/robustness.py, the source of truth.
                          "changed_from_baseline": (rb.changed_fields(baseline, result.facts)
                                                    if baseline is not None else None),
                          "raw_model_response": result.raw_response})
            outcomes["recorded"].append(name)
            print(json.dumps({"run": name, "model": result.model, "tier": c.tier.value,
                              "rule": c.rule_number}), flush=True)
    return outcomes


def _extract(text: str, client: Any, model: str, sleep: Callable[[float], None], attempts: int = 3):
    """One model, no fallback; retry brief overloads (503/504), never quota (429)."""
    for attempt in range(1, attempts + 1):
        try:
            return extract_with_details(text, client=client, model=model)
        except AllModelsUnavailableError as exc:
            if exc.quota_exhausted or attempt == attempts:
                raise
            sleep(20 * attempt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pace", type=float, default=8.0, help="seconds between API calls")
    parser.add_argument("--reference-model", default=MODEL_CHAIN[0], choices=MODEL_CHAIN)
    args = parser.parse_args(argv)
    load_dotenv()
    outcomes = run(args.reference_model, args.pace)
    print(json.dumps({k: len(v) for k, v in outcomes.items()}), file=sys.stderr)
    if outcomes["pending"] or outcomes["failed"]:
        print(f"Some runs are pending. Resume later with: {RESUME_HINT}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
