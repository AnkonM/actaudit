"""Shared test helpers: build AnalysisResults from hand-written facts (no API call)."""
import pipeline
from extractor import ExtractionResult
from tests.test_rules import make_facts


def make_result(label: str = "Test system", **overrides):
    facts = make_facts(**overrides)
    extraction = ExtractionResult(facts=facts, raw_response="{}", model=pipeline.MODEL_CHAIN[0])
    return pipeline._assemble("text", label, "Documentation text.", None, extraction)
