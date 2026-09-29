"""Offline UI tests: drive the real app.py with Streamlit's AppTest.

No network or Gemini calls: quick-picks use recorded fixtures, error cases fail
before any request, and live paths use a fake Gemini client.
"""
import json
import re
import tomllib
from pathlib import Path

import pytest
import streamlit as st
from google.genai import errors
from streamlit.testing.v1 import AppTest

import extractor
import pipeline
from tests.test_extractor import VALID, FakeClient
from tests.test_github_fetch import FakeSession

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
FAKE_KEY = "fake-visitor-key-not-real-0000"
FAKE_SERVER_KEY = "fake-server-key-not-real-1111"
TIERS = {
    # tier: (css modifier, banner label, quick-pick / native icon)
    "Prohibited": ("prohibited", "Prohibited practice", ":material/block:"),
    "High-Risk": ("high", "High-risk system", ":material/warning:"),
    "Limited-Risk": ("limited", "Limited-risk system", ":material/info:"),
    "Minimal-Risk": ("minimal", "Minimal-risk system", ":material/check_circle:"),
    "Out of scope": ("out-of-scope", "Outside the AI Act's scope", ":material/do_not_disturb_on:"),
}
MILITARY_PICK = "Military drone target recognition (sample text)"
QUICK_PICKS = [
    ("Classroom emotion tracker (sample text)", "Prohibited", 3),
    ("Face recognition library", "High-Risk", 6),
    ("Résumé parser (hiring)", "High-Risk", 4),
    ("Chest X-ray diagnosis", "High-Risk", 5),
    ("HTTP utility library", "Limited-Risk", 8),
    ("On-device tab organizer (sample text)", "Minimal-Risk", 7),
]


@pytest.fixture(autouse=True)
def _clear_cache():
    """The analysis cache is process-global; isolate every test from the others."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture(autouse=True)
def client_keys(monkeypatch):
    """A fake shared key in the environment (load_dotenv never overrides it, so a
    developer's real .env is never used) and a record of every key the pipeline
    builds a Gemini client with. Tests may re-patch make_client."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_SERVER_KEY)
    keys: list[str] = []

    def recording_make_client(api_key):
        keys.append(api_key)
        return FakeClient()  # never used for calls: counting_fake replaces extraction

    monkeypatch.setattr(pipeline, "make_client", recording_make_client)
    return keys


# --- Helpers -----------------------------------------------------------------

def run_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def banner(at: AppTest) -> str:
    return at.get_by_key("verdict").get("html")[0].value


def banner_tier(at: AppTest) -> str:
    return re.search(r'aria-label="Risk tier: ([^"]+)"', banner(at)).group(1)


def banner_label(at: AppTest) -> str:
    return re.search(r'class="aa-label">([^<]+)<', banner(at)).group(1)


DECIDED = ":blue-badge[:material/check_circle: Decided]"


def rule_table_rows(at: AppTest):
    return next(t.value for t in at.table if "Applies when" in t.value.columns)


def alert_title(alert) -> str:
    return alert.proto.title


def all_text(at: AppTest) -> str:
    parts = [e.value for group in (at.markdown, at.caption, at.warning, at.info, at.success)
             for e in group]
    return "\n".join(str(p) for p in parts)


def expander(at: AppTest, label: str):
    # Expanders with an icon are reported as "status" blocks by AppTest.
    return next(e for e in at.status if e.proto.label == label)


def paste(at: AppTest, text: str) -> AppTest:
    at.button_group[0].set_value("Paste text").run()
    at.text_area[0].input(text)
    return at.button(key="analyze_text").click().run()


def enter_url(at: AppTest, url: str) -> AppTest:
    at.text_input[0].input(url)
    return at.button(key="analyze_url").click().run()


def counting_fake(monkeypatch, *outputs):
    """Route live analyses to a fake Gemini client; return the fake to inspect calls."""
    fake = FakeClient(*outputs)
    monkeypatch.setattr(
        pipeline, "extract_with_details",
        lambda text, client=None: extractor.extract_with_details(text, client=fake),
    )
    return fake


def _patch(monkeypatch, **fakes):
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline, name, fake)


# --- Idle page -------------------------------------------------------------------

def test_initial_render_has_no_errors():
    at = run_app()
    assert not at.exception
    assert not at.warning


def test_idle_screen_shows_notice_explainer_and_steps():
    at = run_app()
    text = all_text(at)
    assert ("Educational decision-support tool implementing a simplified subset of the EU AI "
            "Act. Not legal advice or a compliance certification.") in at.info[0].value
    assert "An LLM only *extracts* observable facts" in text
    assert "deterministic rule table then decides the tier" in text
    for step in ("1 · Extract facts", "2 · Apply rule table", "3 · Explain the tier"):
        assert step in text
    assert expander(at, "How ActAudit works").proto.expanded is True
    assert "What's simplified" not in text
    assert [e.proto.label for e in at.status] == ["How ActAudit works"]
    assert "0 of 5" in text


def test_explainer_collapses_once_a_result_exists():
    at = run_app()
    at.button(key="qp_Résumé parser (hiring)").click().run()
    assert expander(at, "How ActAudit works").proto.expanded is False
    assert at.info[0].value.startswith("**Educational decision-support tool")  # notice persists


def test_quick_pick_buttons_carry_their_tier_icon():
    at = run_app()
    for label, tier, _ in QUICK_PICKS:
        assert at.button(key=f"qp_{label}").proto.icon == TIERS[tier][2]


def test_quick_picks_cover_every_tier():
    """All five tiers once the Out-of-scope sample is recorded; the four Act tiers before."""
    recorded = [label for label in pipeline.quick_pick_labels()
                if pipeline.quick_pick_status(label) != "not_recorded"]
    tiers = {pipeline.analyze_quick_pick(label).classification.tier.value for label in recorded}
    expected = set(TIERS) if MILITARY_PICK in recorded else set(TIERS) - {"Out of scope"}
    assert tiers == expected


def test_out_of_scope_quick_pick_is_disabled_until_recorded():
    at = run_app()
    button = at.button(key=f"qp_{MILITARY_PICK}")
    if pipeline.quick_pick_status(MILITARY_PICK) == "not_recorded":
        assert button.disabled and button.proto.help == "Not recorded yet."
    else:
        assert not button.disabled
        button.click().run()
        assert banner_tier(at) == "Out of scope"


def test_out_of_scope_banner_from_live_analysis(monkeypatch):
    counting_fake(monkeypatch, json.dumps({**VALID, "military_defence_use": True,
                                           "evidence_snippets": {"military_defence_use": "defence only"}}))
    at = paste(run_app(), "Targeting module used only by a defence ministry.")
    assert not at.exception
    assert banner_tier(at) == "Out of scope"
    assert "aa-verdict--out-of-scope" in banner(at)
    assert banner_label(at) == "Outside the AI Act's scope"
    assert "Art. 2(3)" in banner(at)
    table = rule_table_rows(at)
    assert table.loc[table["This result"] == DECIDED, "Order"].tolist() == [0]
    # Principle flags are still shown for out-of-scope systems.
    assert any(m.value == "##### Documentation gaps" for m in at.markdown)


def test_older_schema_fixture_is_badged():
    at = run_app()
    at.button(key="qp_HTTP utility library").click().run()
    older = pipeline.quick_pick_status("HTTP utility library") == "older_schema"
    assert (":gray-badge[:material/history_toggle_off: Recorded with an older schema]"
            in all_text(at)) is older


# --- Results -----------------------------------------------------------------------

@pytest.mark.parametrize("label,tier,rule", QUICK_PICKS)
def test_quick_picks_render_from_fixtures(label, tier, rule):
    at = run_app()
    at.button(key=f"qp_{label}").click().run()
    assert not at.exception
    # The only warning a recorded example may show is the low-confidence finding (§9).
    assert all(alert_title(w) == "Low extraction confidence" for w in at.warning)
    assert banner_tier(at) == tier
    css_class, banner_text, _ = TIERS[tier]
    assert f"aa-verdict--{css_class}" in banner(at)
    assert banner_label(at) == banner_text
    assert tier.split("-")[0].lower() in banner_text.lower()  # tier name always visible text
    assert not re.search(r"\bRule \d\b", all_text(at))  # rule numbers stay out of the verdict
    assert any("see the **Rule table** tab" in c.value for c in at.caption)
    table = rule_table_rows(at)
    assert table.loc[table["This result"] == DECIDED, "Order"].tolist() == [rule]
    assert any(m.value.startswith("**Provision:**") for m in at.markdown)
    assert any(m.value == "##### Documentation gaps" for m in at.markdown)
    assert any("recorded example (no live API call)" in c.value for c in at.caption)
    assert len(at.dataframe[0].value) == len(pipeline.DISPLAY_ORDER)


def test_justification_and_provision_are_separate_lines():
    at = run_app()
    at.button(key="qp_HTTP utility library").click().run()  # rule 8: no provision in the justification
    verdict = at.get_by_key("verdict")
    justification = next(m.value for m in verdict.markdown if m.value.startswith("Classified as"))
    provision = next(m.value for m in verdict.markdown if m.value.startswith("**Provision:**"))
    assert justification != provision
    assert "project default tier" in provision


def test_prohibited_and_high_risk_banners_are_distinguishable():
    at = run_app()
    at.button(key="qp_Classroom emotion tracker (sample text)").click().run()
    prohibited = banner(at)
    at.button(key="qp_Résumé parser (hiring)").click().run()
    high = banner(at)
    assert "aa-verdict--prohibited" in prohibited and "aa-verdict--high" in high
    assert "Prohibited practice" in prohibited and "High-risk system" in high
    assert "Banned under EU AI Act Art. 5" in prohibited and "strict obligations" in high


def test_result_layout_verdict_then_tabs(monkeypatch):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert at.get_by_key("verdict") is not None
    assert [h.value for h in at.subheader] == ["Why this tier"]
    assert [t.label for t in at.tabs] == [
        ":material/verified_user: Principles (3)",
        ":material/table_rows: Extracted facts",
        ":material/rule: Rule table",
        ":material/description: Raw source",
    ]


def test_rule_table_tab_lists_every_rule_in_order():
    at = run_app()
    at.button(key="qp_Classroom emotion tracker (sample text)").click().run()
    table = rule_table_rows(at)
    expected = pipeline.rule_table()
    assert table["Order"].tolist() == [r["number"] for r in expected] == list(range(0, 9))
    assert table["Applies when"].tolist() == [r["condition"] for r in expected]
    assert table["Tier"].tolist() == [r["tier"] for r in expected]
    assert table["Provision"].tolist() == [r["provision"] for r in expected]
    assert (table["This result"] == DECIDED).sum() == 1
    assert table.loc[table["This result"] == DECIDED, "Order"].item() == 3


def test_principle_cards_state_identifiers():
    at = run_app()
    at.button(key="qp_Chest X-ray diagnosis").click().run()  # flags Human Rights + Data Agency (facts)
    text = all_text(at)
    assert "**Human Rights** :blue-badge[IEEE EAD General Principle 1]" in text
    assert "**Data Agency** :blue-badge[IEEE EAD General Principle 3]" in text
    assert "**Accountability** :blue-badge[IEEE EAD General Principle 6]" in text  # documentation gap
    assert ":gray-badge[UNESCO Recommendation on the Ethics of AI (2021)]" in text


def test_truncated_source_is_stated_and_full_text_shown():
    at = run_app()
    at.button(key="qp_Face recognition library").click().run()
    assert any("Model saw a truncated copy (8,000 of 19,443 characters)" in i.value for i in at.info)
    assert ":gray-badge[:material/content_cut: Input truncated]" in all_text(at)
    assert len(at.code[0].value) > 19_000


def test_low_confidence_is_flagged_on_verdict_and_facts(monkeypatch):
    counting_fake(monkeypatch, json.dumps({**VALID, "extraction_confidence": "low"}))
    at = paste(run_app(), "A vague one-line description.")
    assert ":orange-badge[:material/warning: Low extraction confidence]" in all_text(at)
    assert any(alert_title(w) == "Low extraction confidence" for w in at.warning)


# --- Verdict banner safety and contrast ------------------------------------------

def test_banner_html_contains_no_untrusted_text(monkeypatch):
    hostile = '<img src=x onerror=alert(1)> "quoted" HireBot'
    counting_fake(monkeypatch, json.dumps({**VALID, "system_purpose": hostile[:200],
                                           "evidence_snippets": {"deployment_domain": hostile}}))
    at = paste(run_app(), hostile)
    html = banner(at)
    assert "onerror" not in html and "HireBot" not in html and "quoted" not in html
    assert html.count("<style>") == 1  # the single marked CSS block


def _contrast(a: str, b: str) -> float:
    def lum(h):
        r, g, b_ = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b_)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _theme_colours(block: str, prop: str) -> tuple[str, str]:
    """(light, dark) for `prop` from its light-dark() declaration, or a plain one."""
    pair = re.search(rf"(?<![-\w]){prop}: light-dark\((#[0-9A-Fa-f]{{6}}), (#[0-9A-Fa-f]{{6}})\)", block)
    if pair:
        return pair.group(1), pair.group(2)
    plain = re.findall(rf"(?<![-\w]){prop}: (#[0-9A-Fa-f]{{6}});", block)[-1]
    return plain, plain


@pytest.mark.parametrize("css_class", ["prohibited", "high", "limited", "minimal", "out-of-scope"])
def test_banner_colours_meet_wcag_aa_in_both_themes(css_class):
    source = (ROOT / "app.py").read_text()
    block = re.search(rf"\.aa-verdict--{css_class} \{{(.*?)\}}", source, re.S).group(1)
    fills = _theme_colours(block, "background")
    texts = _theme_colours(block, "color")
    for theme, fill, text in zip(("light", "dark"), fills, texts):
        assert _contrast(text, fill) >= 4.5, f"{css_class} {theme}: {text} on {fill}"


def test_banner_css_has_no_markup_inside_style():
    at = run_app()
    at.button(key="qp_Résumé parser (hiring)").click().run()
    style = banner(at).split("<style>")[1].split("</style>")[0]
    assert "<" not in style and ">" not in style  # the sanitizer drops styles containing markup


def test_theme_defines_light_and_dark():
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    for mode in ("light", "dark"):
        assert config["theme"][mode]["primaryColor"]
        assert config["theme"][mode]["backgroundColor"]
        assert "base" not in config["theme"][mode]  # not a valid key in a mode section
    # Indigo primary, so the Analyze button never looks like a tier verdict.
    assert config["theme"]["light"]["primaryColor"] == "#3949AB"


# --- Error states ----------------------------------------------------------------

@pytest.mark.parametrize("url,title", [
    ("https://gitlab.com/foo/bar", "That doesn't look like a GitHub repository URL"),
    ("", "That doesn't look like a GitHub repository URL"),
])
def test_invalid_url_warning(url, title):
    at = enter_url(run_app(), url)
    assert not at.exception
    assert alert_title(at.warning[0]) == title


def test_empty_paste_warning():
    at = paste(run_app(), "   ")
    assert alert_title(at.warning[0]) == "Nothing to analyze"
    assert "0 of 5" in all_text(at)  # a failed analysis doesn't use up the cap


def test_repo_not_found_warning(monkeypatch):
    real = pipeline.fetch_readme
    _patch(monkeypatch, fetch_readme=lambda url, session=None: real(url, session=FakeSession()))
    at = enter_url(run_app(), "https://github.com/octo/missing")
    assert alert_title(at.warning[0]) == "Repository not found"


@pytest.mark.parametrize("error,title", [
    (pipeline.ReadmeNotFoundError("x"), "No README found"),
    (pipeline.RateLimitedError("x"), "GitHub is rate-limiting requests"),
    (pipeline.NetworkError("x"), "Couldn't reach GitHub"),
    (pipeline.ExtractionAPIError("x", code=401), "The Gemini API is unavailable"),
    (pipeline.InvalidAPIKeyError("x", code=400), "The Gemini API key was rejected"),
    (pipeline.AllModelsUnavailableError("x", code=429, codes=(429, 429, 429, 429)),
     "All Gemini models are out of quota or busy"),
    (pipeline.AllModelsUnavailableError("x", code=503, codes=(503, 503, 503, 503)),
     "Gemini is overloaded right now"),
    (pipeline.MalformedExtractionError("x"), "The model returned unusable output"),
    (RuntimeError("boom"), "Something went wrong"),
])
def test_each_error_type_gets_a_specific_warning(monkeypatch, error, title):
    def fail(*args, **kwargs):
        raise error
    _patch(monkeypatch, analyze_github=fail)
    at = enter_url(run_app(), "https://github.com/octo/repo")
    assert not at.exception  # never a raw stack trace
    warning = at.warning[0]
    assert alert_title(warning) == title
    assert warning.icon.startswith(":material/")
    points_to_quick_picks = "**Try an example** still work" in warning.value
    assert points_to_quick_picks == isinstance(error, pipeline.ExtractionAPIError)


def test_all_models_overloaded_says_overloaded_not_quota(monkeypatch):
    overloaded = errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
    counting_fake(monkeypatch, *[overloaded] * len(pipeline.MODEL_CHAIN))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    warning = at.warning[0]
    assert alert_title(warning) == "Gemini is overloaded right now"
    assert "temporarily overloaded on Google's side" in warning.value
    assert "quota" not in warning.value.lower()
    assert "**Try an example** still work" in warning.value
    assert "0 of 5" in all_text(at)


def test_all_models_exhausted_points_to_quick_picks(monkeypatch):
    quota = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    counting_fake(monkeypatch, *[quota] * len(pipeline.MODEL_CHAIN))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert not at.exception
    assert alert_title(at.warning[0]) == "All Gemini models are out of quota or busy"
    assert "**Try an example** still work" in at.warning[0].value
    assert "0 of 5" in all_text(at)


# --- Live path, cache and session cap ------------------------------------------

def test_paste_path_renders_with_fake_model(monkeypatch):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert not at.exception and not at.warning
    assert banner_tier(at) == "High-Risk"
    assert any("Pasted text" in c.value and "live analysis" in c.value for c in at.caption)
    assert not any("fallback model answered" in c.value for c in at.caption)
    assert "1 of 5" in all_text(at)


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
    assert ":blue-badge[:material/bolt: Cached result]" in all_text(at)
    assert "1 of 5" in all_text(at)  # cache hits don't count toward the cap


def test_session_cap_blocks_live_analysis_and_points_to_quick_picks(monkeypatch):
    fake = counting_fake(monkeypatch)  # any API call would fail: no responses scripted
    at = run_app()
    at.session_state["live_count"] = 5
    at = paste(at, "Some new documentation text.")
    assert alert_title(at.warning[0]) == "Live analysis limit reached for this session"
    assert "**Try an example** work without limits" in at.warning[0].value
    assert fake.models.calls == []
    at.button(key="qp_HTTP utility library").click().run()  # quick-picks still work
    assert banner_tier(at) == "Limited-Risk"


def test_cap_counts_each_new_live_analysis(monkeypatch):
    responses = [json.dumps({**VALID, "system_purpose": f"System {i}"}) for i in range(5)]
    counting_fake(monkeypatch, *responses)
    at = run_app()
    for i in range(5):
        at = paste(at, f"Distinct system number {i}.")
        assert not at.warning
    at = paste(at, "A sixth distinct system.")
    assert alert_title(at.warning[0]) == "Live analysis limit reached for this session"


# --- Bring-your-own key ----------------------------------------------------------

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
    assert banner_tier(at) == "High-Risk"
    assert "Using your own key" in all_text(at)
    assert at.session_state["live_count"] == 5  # own-key analyses don't count


def test_byo_key_is_never_rendered(monkeypatch):
    monkeypatch.setattr(pipeline, "make_client", lambda api_key: FakeClient(json.dumps(VALID)))
    at = run_app()
    at.sidebar.text_input(key="byo_key").input(FAKE_KEY).run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert FAKE_KEY not in all_text(at)
    assert FAKE_KEY not in banner(at)
    assert all(FAKE_KEY not in str(d.value) for d in at.dataframe)
    assert all(FAKE_KEY not in c.value for c in at.code)


def test_blank_byo_key_falls_back_to_shared_key(monkeypatch, client_keys):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = run_app()
    at.sidebar.text_input(key="byo_key").input("   ").run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert banner_tier(at) == "High-Risk"
    assert client_keys == [FAKE_SERVER_KEY]
    assert "1 of 5" in all_text(at)


# --- Shared key: st.secrets first, environment fallback ---------------------------

def test_shared_key_comes_from_environment_when_no_secrets(monkeypatch, client_keys):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert not at.warning
    assert client_keys == [FAKE_SERVER_KEY]


def test_st_secrets_take_precedence_over_environment(monkeypatch, client_keys):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["GEMINI_API_KEY"] = "fake-key-from-st-secrets"
    at.run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert not at.warning
    assert client_keys == ["fake-key-from-st-secrets"]


def test_byo_key_overrides_the_shared_key(monkeypatch, client_keys):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = run_app()
    at.sidebar.text_input(key="byo_key").input(FAKE_KEY).run()
    paste(at, "HireBot ranks job applicants automatically.")
    assert client_keys == [FAKE_KEY]


def test_no_key_anywhere_gives_a_friendly_state(monkeypatch, client_keys):
    # Empty, not deleted: a deleted variable would let load_dotenv() pull in a real .env.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    fake = counting_fake(monkeypatch)  # any API call would fail: no responses scripted
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert not at.exception
    assert alert_title(at.warning[0]) == "Live analysis isn't set up on this deployment"
    assert "**Try an example**" in at.warning[0].value
    assert fake.models.calls == [] and client_keys == []
    at.button(key="qp_HTTP utility library").click().run()  # quick-picks need no key
    assert banner_tier(at) == "Limited-Risk"


def test_server_key_is_never_rendered(monkeypatch):
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert FAKE_SERVER_KEY not in all_text(at) and FAKE_SERVER_KEY not in banner(at)


def test_rejected_own_key_points_to_the_sidebar(monkeypatch):
    def fail(*args, **kwargs):
        raise pipeline.InvalidAPIKeyError("Gemini rejected the API key (HTTP 400).", code=400)
    _patch(monkeypatch, analyze_text=fail)
    at = run_app()
    at.sidebar.text_input(key="byo_key").input(FAKE_KEY).run()
    at = paste(at, "HireBot ranks job applicants automatically.")
    assert alert_title(at.warning[0]) == "The Gemini API key was rejected"
    assert "entered in the sidebar" in at.warning[0].value
    assert "Try again shortly" not in at.warning[0].value


def test_rejected_shared_key_does_not_blame_the_visitor(monkeypatch):
    def fail(*args, **kwargs):
        raise pipeline.InvalidAPIKeyError("Gemini rejected the API key (HTTP 400).", code=400)
    _patch(monkeypatch, analyze_text=fail)
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert alert_title(at.warning[0]) == "The Gemini API key was rejected"
    assert "sidebar" not in at.warning[0].value


# --- Trust signals -------------------------------------------------------------------

def test_fallback_model_caption(monkeypatch):
    quota = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    counting_fake(monkeypatch, quota, json.dumps(VALID))  # primary 429s, next model answers
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert any(c.value == "Extracted by **gemini-3.7-flash**" for c in at.caption)
    assert any(c.value.startswith(":orange[:material/warning: A fallback model answered]") for c in at.caption)


def test_primary_model_has_no_fallback_caption(monkeypatch):
    # A live (fake) call the primary model answers; independent of which model
    # happened to answer when each fixture was recorded.
    counting_fake(monkeypatch, json.dumps(VALID))
    at = paste(run_app(), "HireBot ranks job applicants automatically.")
    assert any(c.value == "Extracted by **gemini-3.8-flash**" for c in at.caption)
    assert not any("fallback model answered" in c.value for c in at.caption)
