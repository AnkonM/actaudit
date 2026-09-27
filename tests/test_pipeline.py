"""Pipeline tests. Offline by default; the live end-to-end test runs only with
ACTAUDIT_LIVE=1 (it costs one Gemini request and needs network + GEMINI_API_KEY)."""
import json
import os

import pytest

from extractor import MAX_INPUT_CHARS, EmptyInputError
from github_fetch import RepoNotFoundError
from pipeline import analyze_github, analyze_text, clean_pasted_text
from rules import RiskTier
from tests.test_extractor import VALID, FakeClient
from tests.test_github_fetch import FakeResponse, FakeSession

RAW = "https://raw.githubusercontent.com/octo/hirebot/main/README.md"


def test_github_path_end_to_end_offline():
    readme = "# HireBot\n" + "Ranks job applicants automatically. " * 300  # > 8,000 chars
    session = FakeSession({RAW: FakeResponse(200, readme)})
    client = FakeClient(json.dumps(VALID))

    result = analyze_github("https://github.com/octo/hirebot", client=client, session=session)

    assert result.source_kind == "github"
    assert result.source_label == "octo/hirebot"
    assert result.source_text == readme  # full original kept for the raw-source toggle
    assert result.llm_input_truncated is True
    assert client.models.calls[0]["contents"].endswith("(truncated)")
    assert len(client.models.calls[0]["contents"]) < len(readme)
    assert result.extraction.model == "gemini-3.8-flash"
    assert result.classification.tier is RiskTier.HIGH_RISK
    assert result.classification.rule_number == 4
    assert {f.ieee for f in result.principles} >= {"Accountability", "Human Rights"}


def test_text_path_cleans_whitespace():
    client = FakeClient(json.dumps(VALID))
    result = analyze_text("\n\n  Hiring tool.   \n\n\n\nRanks CVs.  \n", client=client)
    assert result.source_kind == "text"
    assert result.readme is None
    assert result.source_text == "Hiring tool.\n\nRanks CVs."
    assert result.llm_input_truncated is False


def test_clean_pasted_text():
    assert clean_pasted_text("a  \n\n\n\nb\n") == "a\n\nb"


def test_fetch_errors_propagate_unchanged():
    with pytest.raises(RepoNotFoundError):
        analyze_github("https://github.com/octo/missing", client=FakeClient(), session=FakeSession())


def test_empty_paste_raises_before_any_api_call():
    client = FakeClient()
    with pytest.raises(EmptyInputError):
        analyze_text("   \n  ", client=client)
    assert client.models.calls == []


@pytest.mark.skipif(os.getenv("ACTAUDIT_LIVE") != "1", reason="live test; set ACTAUDIT_LIVE=1")
def test_live_github_url_end_to_end():
    from dotenv import load_dotenv

    load_dotenv()
    result = analyze_github("https://github.com/OmkarPathak/pyresparser")
    assert result.source_label == "OmkarPathak/pyresparser"
    assert len(result.source_text) > 0
    assert result.classification.tier is RiskTier.HIGH_RISK
    assert result.classification.rule_number == 4
    assert MAX_INPUT_CHARS > 0 and result.principles
