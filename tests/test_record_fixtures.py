"""scripts/record_fixtures.py with a fake Gemini client: no network, no quota."""
import json

import pytest
from google.genai import errors

from schema import SCHEMA_VERSION, V2_FIELDS
from scripts import record_fixtures as rf
from tests.test_extractor import VALID, FakeClient


def _quota():
    return errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})


@pytest.fixture
def fixture_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(rf, "CANDIDATE_DIR", tmp_path / "_candidates")
    monkeypatch.setattr(rf, "set_stems", lambda name: ["text__a", "text__b"])
    monkeypatch.setattr(rf, "all_sources", lambda: {
        s: rf.Source(s, "text", f"{s} ranks job applicants.", "test", "hiring")
        for s in ("text__a", "text__b")
    })
    return tmp_path


def test_records_pending_fixtures_with_schema_version_and_paces(fixture_dir):
    sleeps = []
    out = rf.run("x", client=FakeClient(json.dumps(VALID), json.dumps(VALID)), pace=6, sleep=sleeps.append)
    assert out["recorded"] == ["text__a", "text__b"]
    record = json.loads((fixture_dir / "text__a.json").read_text())
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["extracted_facts"]["synthetic_media_types"] == []
    assert sleeps == [6]  # paced between calls, not before the first


def test_existing_fixtures_are_skipped(fixture_dir):
    (fixture_dir / "text__a.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION}))
    client = FakeClient(json.dumps(VALID))
    out = rf.run("x", client=client, pace=0)
    assert out["skipped"] == ["text__a"] and out["recorded"] == ["text__b"]
    assert len(client.models.calls) == 1


def test_quota_exhaustion_stops_cleanly_and_lists_pending(fixture_dir):
    client = FakeClient(*[_quota()] * 4)  # every model in the chain
    out = rf.run("x", client=client, pace=0, sleep=lambda s: None)
    assert out["pending"] == ["text__a", "text__b"]
    assert not list(fixture_dir.glob("*.json"))


def _v1_record(facts):
    v1 = {k: v for k, v in facts.items() if k not in V2_FIELDS}
    return {"source_kind": "text", "source_text": "old", "model": "m",
            "raw_model_response": "{}", "extracted_facts": v1}


def test_rerecord_older_schema_replaces_when_tier_is_unchanged(fixture_dir):
    (fixture_dir / "text__a.json").write_text(json.dumps(_v1_record(VALID)))
    (fixture_dir / "text__b.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION}))
    out = rf.run("x", rerecord_older=True, client=FakeClient(json.dumps(VALID)), pace=0)
    assert out["recorded"] == ["text__a"] and out["skipped"] == ["text__b"]
    assert json.loads((fixture_dir / "text__a.json").read_text())["schema_version"] == SCHEMA_VERSION


def test_rerecord_that_changes_the_tier_is_parked_as_a_candidate(fixture_dir):
    (fixture_dir / "text__a.json").write_text(json.dumps(_v1_record(VALID)))  # High-Risk, rule 4
    (fixture_dir / "text__b.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION}))
    changed = {**VALID, "deployment_domain": "other"}  # would become Limited-Risk, rule 8
    out = rf.run("x", rerecord_older=True, client=FakeClient(json.dumps(changed)), pace=0)
    assert out["candidate"] == ["text__a"]
    kept = json.loads((fixture_dir / "text__a.json").read_text())
    assert "schema_version" not in kept  # the approved v1 fixture is untouched
    parked = json.loads((fixture_dir / "_candidates" / "text__a.json").read_text())
    assert parked["replaces"] == {"tier_rule_before": ["High-Risk", 4],
                                  "tier_rule_after": ["Limited-Risk", 8]}


def test_real_sets_cover_quick_picks_and_examples():
    assert "text__military_target_recognition" in rf.set_stems("quick_picks")
    assert "deepfakes__faceswap" in rf.set_stems("synthetic")
    legacy = rf.set_stems("legacy")
    assert "ayhandis__creditR" in legacy and "psf__requests" not in legacy
    assert set(rf.set_stems("all")) <= set(rf.all_sources())
