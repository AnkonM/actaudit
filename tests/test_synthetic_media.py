"""analysis/synthetic_media.py: Art. 50 determinations, misuse matrix, ethics text."""
import pytest

from analysis import synthetic_media as sm
from schema import SyntheticMediaType as M
from tests.test_rules import make_facts


def obligations(**kw):
    return {o.provision: o for o in sm.transparency_obligations(make_facts(**kw))}


def test_non_generative_system_has_no_art50_duties():
    obs = obligations()
    assert {o.status for o in obs.values()} == {sm.NOT_APPLICABLE}


def test_voice_cloner_triggers_marking_and_deepfake_disclosure():
    obs = obligations(generates_synthetic_media=True, synthetic_media_types=(M.AUDIO,),
                      impersonation_capable=True)
    assert obs["EU AI Act Art. 50(2)"].status == sm.APPLIES
    assert obs["EU AI Act Art. 50(2)"].duty_holder == "Provider"
    assert "doesn't mention marking" in obs["EU AI Act Art. 50(2)"].documentation
    deepfake = obs["EU AI Act Art. 50(4), first subparagraph"]
    assert deepfake.status == sm.APPLIES and deepfake.duty_holder == "Deployer"
    assert "Art. 3(60)" in deepfake.reason
    assert obs["EU AI Act Art. 50(4), second subparagraph"].status == sm.NOT_APPLICABLE


def test_generic_image_generator_may_trigger_deepfake_duty():
    obs = obligations(generates_synthetic_media=True, synthetic_media_types=(M.IMAGE,),
                      output_marking_mentioned=True)
    assert obs["EU AI Act Art. 50(4), first subparagraph"].status == sm.MAY_APPLY
    assert "mentions watermarking" in obs["EU AI Act Art. 50(2)"].documentation


def test_text_generator_may_trigger_public_interest_text_duty():
    obs = obligations(generates_synthetic_media=True, synthetic_media_types=(M.TEXT,))
    assert obs["EU AI Act Art. 50(4), second subparagraph"].status == sm.MAY_APPLY
    assert "editorial control" in obs["EU AI Act Art. 50(4), second subparagraph"].exceptions


@pytest.mark.parametrize("marking,consent,expected", [
    (False, False, sm.HIGH), (True, False, sm.HIGH), (True, True, sm.MEDIUM)])
def test_impersonation_row_follows_the_scoring_table(marking, consent, expected):
    m = sm.misuse_matrix(make_facts(impersonation_capable=True, output_marking_mentioned=marking,
                                    consent_safeguards_mentioned=consent))
    assert m.rows[0].capability == "Impersonation of a real person" and m.rows[0].score == expected


def test_matrix_rows_and_overall():
    m = sm.misuse_matrix(make_facts(generates_synthetic_media=True,
                                    synthetic_media_types=(M.TEXT, M.VIDEO),
                                    consent_safeguards_mentioned=True))
    assert [(r.capability, r.score) for r in m.rows] == [("Synthetic video", sm.MEDIUM), ("Synthetic text", sm.LOW)]
    assert m.rows[0].safeguards == (False, True, True)  # consent + policy share one fact
    assert m.overall == sm.MEDIUM
    assert sm.misuse_matrix(make_facts()).overall is None


def test_untyped_generation_gets_a_row():
    m = sm.misuse_matrix(make_facts(generates_synthetic_media=True))
    assert m.rows[0].capability == "Synthetic content (type not stated)"


def test_ethical_analysis_themes():
    themes = [t for t, _ in sm.ethical_analysis(make_facts(
        generates_synthetic_media=True, synthetic_media_types=(M.AUDIO,), impersonation_capable=True))]
    assert themes == ["Consent", "Impersonation and fraud", "Misinformation", "Transparency"]
    assert sm.ethical_analysis(make_facts())[0][0] == "Scope"
