"""The single command that completes every pending Gemini recording (blueprint §15.6).

Usage: python scripts/record_all.py [--pace SECONDS]

Runs the recording priorities in order, skipping anything already recorded:
  (1) quick-pick fixtures on the current schema (re-records older-schema ones);
  (2) Tab 3 synthetic-media examples;
  (3) Case Library descriptions;
  (4) the robustness study (scripts/robustness_study.py).
It stops cleanly when quota runs out; rerun it later (e.g. the next day, when the
free-tier daily quota resets) to continue where it left off. Exit code 0 means
everything is recorded, 3 means some recordings are still pending.
"""
import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from scripts import record_fixtures  # noqa: E402

FIXTURE_STEPS = [
    ("(1) quick-pick fixtures", "quick_picks", True),
    ("(2) synthetic-media examples", "synthetic", False),
    ("(3) Case Library", "cases", False),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pace", type=float, default=6.0, help="seconds between API calls")
    args = parser.parse_args(argv)
    load_dotenv()

    pending = False
    for title, set_name, rerecord in FIXTURE_STEPS:
        print(f"== {title}", file=sys.stderr)
        outcomes = record_fixtures.run(set_name, rerecord_older=rerecord, pace=args.pace)
        if outcomes["pending"]:
            print(f"Stopped at {title}: quota exhausted. Rerun: python scripts/record_all.py",
                  file=sys.stderr)
            return 3
        pending = pending or bool(outcomes["failed"])

    print("== (4) robustness study", file=sys.stderr)
    try:
        study = importlib.import_module("scripts.robustness_study")
    except ModuleNotFoundError:
        print("robustness_study.py not present yet; skipping", file=sys.stderr)
        return 3
    if study.main(["--pace", str(args.pace)]) != 0:
        return 3
    return 3 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
