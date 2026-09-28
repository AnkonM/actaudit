"""Demo quick-picks (Blueprint §8 point 4), served from recorded fixtures.

Each entry points at a file in tests/fixtures/ recorded by scripts/record_fixtures.py,
so choosing a quick-pick needs no network or Gemini call during a presentation.
"""

QUICK_PICKS: list[tuple[str, str]] = [
    # (button label, fixture file stem). Together these must cover all four tiers.
    ("Classroom emotion tracker (sample text)", "text__classroom_emotion_tracker"),  # Prohibited
    ("Face recognition library", "ageitgey__face_recognition"),
    ("Résumé parser (hiring)", "OmkarPathak__pyresparser"),
    ("Chest X-ray diagnosis", "arnoweng__CheXNet"),
    ("HTTP utility library", "psf__requests"),  # Limited-Risk
    ("On-device tab organizer (sample text)", "text__tab_grouping_extension"),  # Minimal-Risk
]
