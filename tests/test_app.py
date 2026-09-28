"""Offline UI tests: drive the real app.py with Streamlit's AppTest.

No network or Gemini calls: quick-picks use recorded fixtures, error cases fail
before any request, and the paste path uses a fake Gemini client.
"""
import json
import re
from pathlib import Path

import pytest
import streamlit as st
from google.genai import errors
from streamlit.testing.v1 import AppTest

import extractor
import pipeline
from tests.test_extractor import VALID, FakeClient
from tests.test_github_fetch import FakeSession

APP = str(Path(__file__).resolve().parent.parent / "app.py")


FAKE_KEY = "fake-visitor-key-not-real-0000"


@pytest.fixture(autouse=True)
def _clear_cache():
    """The analysis cache is process-global; isolate every test from the others."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def badge_html(at: AppTest) -> str:
    return next(m.value for m in at.markdown if 'class="aa-badge' in m.value)


def badge(at: AppTest) -> str:
    return re.search(r'class="aa-tier-name">([^<]+)<', badge_html(at)).group(1)


def all_text(at: AppTest) -> str:
    parts = [e.value for group in (at.markdown, at.caption, at.warning, at.info, at.success)
             for e in group]
    return "\n".join(str(p) for p in parts)


def paste(at: AppTest, text: str) -> AppTest:
    at.radio[0].set_value("Paste text").run()
    at.text_area[0].input(text)
    return at.button(key="analyze_text").click().run()


def counting_fake(monkeypatch, *outputs):
    """Route the paste path to a fake Gemini client; return the fake to inspect calls."""
    fake = FakeClient(*outputs)
    monkeypatch.setattr(
        pipeline, "extract_with_details",
        lambda text, client=None: extractor.extract_with_details(text, client=fake),
    )
    return fake


def test_initial_render_has_no_errors():
    at = run_app()
    assert not at.exception
    assert not at.warning


def test_idle_screen_shows_intro_and_persistent_notice():
    at = run_app()
    text = all_text(at)
    assert "An LLM only *extracts* observable facts" in text
    assert ("Educational decision-support tool implementing a simplified subset of the EU AI "
            "Act. Not legal advice or a compliance certification.") in text
    assert any("simplifications" in e.label.lower() for e in at.expander)
    assert "0 of 5" in text


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
    assert f'aria-label="Risk tier: {tier}"' in badge_html(at)
    assert any(c.value == f"Rule {rule} of the ordered rule table fired (first match wins)." for c in at.caption)
    assert any(m.value.startswith("**Provision:**") for m in at.markdown)
    assert any(m.value == "##### Documentation gaps" for m in at.markdown)
    assert any("recorded example (no live API call)" in c.value for c in at.caption)
    assert len(at.dataframe[0].value) == 12


def test_prohibited_and_high_risk_badges_differ_beyond_colour():
    at = run_app()
    at.button(key="qp_Classroom emotion tracker (sample text)").click().run()
    prohibited = badge_html(at)
    at.button(key="qp_Résumé parser (hiring)").click().run()
    high = badge_html(at)
    assert "aa-prohibited" in prohibited and "aa-prohibited" not in high
    assert "⛔" in prohibited and "⚠️" in high
    assert "Banned practice" in prohibited and "strict obligations" in high


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
    at = paste(run_app(), "   ")
    assert at.warning[0].value.startswith("**Nothing to analyze.**")
    assert "0 of 5" in all_text(at)  # a failed analysis doesn't use up the cap


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
    (pipeline.ExtractionAPIError("x", code=401), "The Gemini API is unavailable"),
    (pipeline.AllModelsUnavailableError("x", code=429), "All Gemini models are out of quota or busy"),
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
    points_to_quick_picks = "pre-loaded examples below still work" in at.warning[0].value
    assert points_to_quick_picks == isinstance(error, pipeline.ExtractionAPIError)


def test_paste_path_renders_with_fake_model(monkeypatch):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert not at.exception and not at.warning
    assert badge(at) == "High-Risk"
    assert any("Pasted text" in c.value and "live analysis" in c.value for c in at.caption)
    assert not any("fallback model answered" in c.value for c in at.caption)
    assert "1 of 5" in all_text(at)


def test_result_sections_in_order(monkeypatch):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    subheaders = [h.value for h in at.subheader]
    assert subheaders == ["Why this tier", "UNESCO / IEEE principles", "Extracted facts"]


# --- Quota protection -------------------------------------------------------

def test_repeat_submission_is_served_from_cache(monkeypatch):
    fake = counting_fake(monkeypatch, json.dumps(VALID))  # only ONE response scripted
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    at.button(key="analyze_text").click().run()
    # Whitespace differences clean to the same key, so this is a cache hit too.
    at.text_area[0].input("  HireBot ranks job applicants automatically.  \n")
    at.button(key="analyze_text").click().run()
    assert not at.exception and not at.warning
    assert len(fake.models.calls) == 1
    assert any("cached result (no new API call)" in c.value for c in at.caption)
    assert "1 of 5" in all_text(at)  # cache hits don't count toward the cap


def test_session_cap_blocks_live_analysis_and_points_to_quick_picks(monkeypatch):
    fake = counting_fake(monkeypatch)  # any API call would fail: no responses scripted
    at = run_app()
    at.session_state["live_count"] = 5
    at = paste(at, "Some new documentation text.")
    assert at.warning[0].value.startswith("**Live analysis limit reached for this session.**")
    assert "pre-loaded examples below work without limits" in at.warning[0].value
    assert fake.models.calls == []
    at.button(key="qp_HTTP utility library").click().run()  # quick-picks still work
    assert badge(at) == "Limited-Risk"


def test_cap_counts_each_new_live_analysis(monkeypatch):
    responses = [json.dumps({**VALID, "system_purpose": f"System {i}"}) for i in range(5)]
    counting_fake(monkeypatch, *responses)
    at = run_app()
    for i in range(5):
        at = paste(at, f"Distinct system number {i}.")
        assert not at.warning
    at = paste(at, "A sixth distinct system.")
    assert at.warning[0].value.startswith("**Live analysis limit reached")


# --- Bring-your-own key ----------------------------------------------------

def test_byo_key_is_used_and_lifts_the_cap(monkeypatch):
    seen_keys = []
    fake = FakeClient(json.dumps(VALID))

    def fake_make_client(api_key):
        seen_keys.append(api_key)
        return fake

    monkeypatch.setattr(pipeline, "make_client", fake_make_client)
    at = run_app()
    at.session_state["live_count"] = 5  # cap already hit on the shared key
    at.sidebar.text_input(key="byo_key").input(FAKE_KEY).run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert not at.exception and not at.warning
    assert seen_keys == [FAKE_KEY]
    assert len(fake.models.calls) == 1
    assert badge(at) == "High-Risk"
    assert "Using your own key" in all_text(at)
    assert at.session_state["live_count"] == 5  # own-key analyses don't count


def test_byo_key_is_never_rendered(monkeypatch):
    monkeypatch.setattr(pipeline, "make_client", lambda api_key: FakeClient(json.dumps(VALID)))
    at = run_app()
    at.sidebar.text_input(key="byo_key").input(FAKE_KEY).run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert FAKE_KEY not in all_text(at)
    assert all(FAKE_KEY not in str(d.value) for d in at.dataframe)
    assert all(FAKE_KEY not in c.value for c in at.code)


def test_blank_byo_key_falls_back_to_shared_key(monkeypatch):
    monkeypatch.setattr(pipeline, "make_client", lambda api_key: pytest.fail("must not build a BYO client"))
    counting_fake(monkeypatch, json.dumps(VALID))
    at = run_app()
    at.sidebar.text_input(key="byo_key").input("   ").run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert badge(at) == "High-Risk"
    assert "1 of 5" in all_text(at)


# --- Trust signals -----------------------------------------------------------

def test_fallback_model_caption(monkeypatch):
    quota = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    counting_fake(monkeypatch, quota, json.dumps(VALID))  # primary 429s, next model answers
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert any("Extracted by `gemini-3.7-flash`" in c.value for c in at.caption)
    assert any(c.value.startswith("⚠️ A fallback model answered") for c in at.caption)


def test_all_models_exhausted_points_to_quick_picks(monkeypatch):
    quota = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    counting_fake(monkeypatch, *[quota] * len(pipeline.MODEL_CHAIN))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert not at.exception
    assert at.warning[0].value.startswith("**All Gemini models are out of quota or busy.**")
    assert "pre-loaded examples below still work" in at.warning[0].value
    assert "0 of 5" in all_text(at)
