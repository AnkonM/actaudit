"""Demo quick-picks (Blueprint §8 point 4) and per-tab example sets (§15), served
from recorded fixtures.

Each entry points at a file in tests/fixtures/ recorded by scripts/record_fixtures.py,
so choosing an example needs no network or Gemini call during a presentation. An
entry whose fixture isn't recorded yet is shown as "not recorded yet".
"""

QUICK_PICKS: list[tuple[str, str]] = [
    # (button label, fixture file stem). Together these must cover every tier.
    ("Classroom emotion tracker (sample text)", "text__classroom_emotion_tracker"),  # Prohibited
    ("Face recognition library", "ageitgey__face_recognition"),
    ("Résumé parser (hiring)", "OmkarPathak__pyresparser"),
    ("Chest X-ray diagnosis", "arnoweng__CheXNet"),
    ("HTTP utility library", "psf__requests"),  # Limited-Risk
    ("On-device tab organizer (sample text)", "text__tab_grouping_extension"),  # Minimal-Risk
    ("Military drone target recognition (sample text)", "text__military_target_recognition"),  # Out of scope
]

# Example selectors shown by individual tabs when nothing is loaded (Section 15).
EXAMPLE_SETS: dict[str, list[tuple[str, str]]] = {
    "synthetic_media": [
        ("Real-time voice cloning", "CorentinJ__Real-Time-Voice-Cloning"),
        ("Face-swap toolkit", "deepfakes__faceswap"),
        ("EfficientNet image classifier (non-generative)", "lukemelas__EfficientNet-PyTorch"),
    ],
    "autonomy": [
        ("Military drone target recognition (sample text)", "text__military_target_recognition"),
        ("911 dispatch triage", "Vinaya-Sharma__TriageAI"),
        ("Face recognition library", "ageitgey__face_recognition"),
    ],
}
