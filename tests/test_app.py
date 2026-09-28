"""Offline UI tests: drive the real app.py with Streamlit's AppTest.

No network or Gemini calls: quick-picks use recorded fixtures, error cases fail
before any request, and the paste path uses a fake Gemini client.
"""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import extractor
import pipeline
from tests.test_extractor import VALID, FakeClient
from tests.test_github_fetch import FakeSession

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def badge(at: AppTest) -> str:
    html = next(m.value for m in at.markdown if "border-radius" in m.value)
    return html.split(">")[1].split("<")[0]


def test_initial_render_has_no_errors():
    at = run_app()
    assert not at.exception
    assert not at.warning


@pytest.mark.parametrize("label,tier,rule", [
    ("Classroom emotion tracker (sample text)", "Prohibited", 3),
    ("Face recognition library", "High-Risk", 6),
    ("Résumé parser (hiring)", "High-Risk", 4),
    ("Chest X-ray diagnosis", "High-Risk", 5),
    ("HTTP utility library", "Limited-Risk", 8),
    ("On-device tab organizer (sample text)", "Minimal-Risk", 7),
])
def test_quick_picks_render_from_fixtures(label, tier, rule):
    at = run_app()
    at.button(key=f"qp_{label}").click().run()
    assert not at.exception and not at.warning
    assert badge(at) == tier
    assert any(c.value == f"Rule {rule} of the ordered rule table fired (first match wins)." for c in at.caption)
    assert any(m.value.startswith("**Provision:**") for m in at.markdown)
    assert any(m.value == "##### Documentation gaps" for m in at.markdown)
    assert any("recorded example (no live API call)" in c.value for c in at.caption)
    assert len(at.dataframe[0].value) == 12


def test_quick_picks_cover_all_four_tiers():
    tiers = {pipeline.analyze_quick_pick(label).classification.tier.value
             for label in pipeline.quick_pick_labels()}
    assert tiers == {"Prohibited", "High-Risk", "Limited-Risk", "Minimal-Risk"}


def test_truncated_source_is_stated_and_full_text_shown():
    at = run_app()
    at.button(key="qp_Face recognition library").click().run()
    assert any("Model saw a truncated copy (8,000 of 19,443 characters)" in i.value for i in at.info)
    assert len(at.code[0].value) > 19_000


@pytest.mark.parametrize("url,title", [
    ("https://gitlab.com/foo/bar", "That doesn't look like a GitHub repository URL"),
    ("", "That doesn't look like a GitHub repository URL"),
])
def test_invalid_url_warning(url, title):
    at = run_app()
    at.text_input[0].input(url)
    at.button(key="analyze_url").click().run()
    assert not at.exception
    assert at.warning[0].value.startswith(f"**{title}.**")


def test_empty_paste_warning():
    at = run_app()
    at.radio[0].set_value("Paste text").run()
    at.text_area[0].input("   ")
    at.button(key="analyze_text").click().run()
    assert at.warning[0].value.startswith("**Nothing to analyze.**")


def _patch(monkeypatch, **fakes):
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline, name, fake)


def test_repo_not_found_warning(monkeypatch):
    real = pipeline.fetch_readme
    _patch(monkeypatch, fetch_readme=lambda url, session=None: real(url, session=FakeSession()))
    at = run_app()
    at.text_input[0].input("https://github.com/octo/missing")
    at.button(key="analyze_url").click().run()
    assert at.warning[0].value.startswith("**Repository not found.**")


@pytest.mark.parametrize("error,title", [
    (pipeline.ReadmeNotFoundError("x"), "No README found"),
    (pipeline.RateLimitedError("x"), "GitHub is rate-limiting requests"),
    (pipeline.NetworkError("x"), "Couldn't reach GitHub"),
    (pipeline.ExtractionAPIError("x", code=429), "The Gemini API is unavailable"),
    (pipeline.MalformedExtractionError("x"), "The model returned unusable output"),
    (RuntimeError("boom"), "Something went wrong"),
])
def test_each_error_type_gets_a_specific_warning(monkeypatch, error, title):
    def fail(*args, **kwargs):
        raise error
    _patch(monkeypatch, analyze_github=fail)
    at = run_app()
    at.text_input[0].input("https://github.com/octo/repo")
    at.button(key="analyze_url").click().run()
    assert not at.exception  # never a raw stack trace
    assert at.warning[0].value.startswith(f"**{title}.**")


def test_paste_path_renders_with_fake_model(monkeypatch):
    fake = FakeClient(json.dumps(VALID))
    _patch(monkeypatch, extract_with_details=lambda text, client=None: extractor.extract_with_details(text, client=fake))
    at = run_app()
    at.radio[0].set_value("Paste text").run()
    at.text_area[0].input("HireBot ranks job applicants automatically.")
    at.button(key="analyze_text").click().run()
    assert not at.exception and not at.warning
    assert badge(at) == "High-Risk"
    assert any("Pasted text" in c.value and "live analysis" in c.value for c in at.caption)
