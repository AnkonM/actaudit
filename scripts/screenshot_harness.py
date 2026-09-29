"""Dev-only: app.py with a hand-built Out-of-scope analysis preloaded, used by
scripts/screenshot_tabs.py to capture the Out-of-scope verdict while the military
sample text (quick-pick) is not recorded yet. Never deployed; the source label says
the facts are hand-built, so the screenshot can't be mistaken for a live extraction.

Run with: streamlit run scripts/screenshot_harness.py
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

import pipeline  # noqa: E402
from examples.quick_picks import QUICK_PICKS  # noqa: E402
from extractor import ExtractionResult  # noqa: E402
from schema import ExtractedFacts  # noqa: E402
from scripts.record_fixtures import TEXT_EXAMPLES  # noqa: E402

TEXT = next(t for stem, _, _, t in TEXT_EXAMPLES if stem == "text__military_target_recognition")
FACTS = {
    "system_purpose": "Object-recognition module that detects and classifies military vehicles and personnel in live drone video.",
    "deployment_domain": "other", "data_sensitivity": "personal", "biometric_use": False,
    "decision_autonomy": "human_in_loop", "affected_population": "general_public",
    "emotion_inference": False, "social_scoring": False, "real_time_biometric_public": False,
    "human_oversight_mentioned": True, "transparency_mentioned": False,
    "extraction_confidence": "high",
    "evidence_snippets": {
        "military_defence_use": "developed under contract for a national defence ministry and used exclusively in the ministry's military surveillance drones",
        "decision_autonomy": "A trained operator reviews every highlighted target before any action is taken.",
        "human_oversight_mentioned": "A trained operator reviews every highlighted target before any action is taken.",
    },
    "target_variable": "military vehicles and personnel in live drone video", "target_type": "direct_outcome",
    "generates_synthetic_media": False, "synthetic_media_types": [], "impersonation_capable": False,
    "output_marking_mentioned": False, "consent_safeguards_mentioned": False,
    "military_defence_use": True, "robustness_testing_mentioned": False, "failsafe_mentioned": False,
}

if "harness_loaded" not in st.session_state:
    stem = dict(QUICK_PICKS)["Military drone target recognition (sample text)"]
    origin = "fixture"
    if pipeline.example_status(stem) != "not_recorded":
        result = pipeline.load_example(stem)
        source = "Tab 1 quick-pick"
    else:
        extraction = ExtractionResult(ExtractedFacts.from_dict(FACTS), "{}", "hand-built (no model)")
        result = pipeline._assemble("text", "Military drone sample: HAND-BUILT facts, screenshot only",
                                    TEXT, None, extraction)
        source = "screenshot harness"
        origin = "handbuilt"
    st.session_state.current_analysis = result
    st.session_state.analysis_origin = origin
    st.session_state.analysis_source = source
    st.session_state.harness_loaded = True

runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
