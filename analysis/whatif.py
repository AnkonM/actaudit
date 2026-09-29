"""Tab 5B · What-if explorer: re-run the rule engine and principle mapping on edited
facts (no LLM call) and report what changed from the original extraction.
"""
from dataclasses import dataclass, replace
from typing import Any

from principles import evaluate_principles
from rules import RiskTier, classify
from schema import ExtractedFacts

# One-click presets. The disclosure preset is blueprint §9's documentation-opacity
# point: what if the README had simply said these two things?
PRESETS: dict[str, dict[str, Any]] = {
    "What if the README had disclosed human oversight and transparency?": {
        "human_oversight_mentioned": True,
        "transparency_mentioned": True,
    },
}


@dataclass(frozen=True)
class WhatIfDiff:
    original_tier: RiskTier
    edited_tier: RiskTier
    original_rule: int
    edited_rule: int
    changed_fields: list[tuple[str, Any, Any]]  # (field, original, edited)
    added_flags: list[str]  # UNESCO principle names newly flagged
    removed_flags: list[str]  # no longer flagged

    @property
    def tier_changed(self) -> bool:
        return self.original_tier != self.edited_tier

    @property
    def rule_changed(self) -> bool:
        return self.original_rule != self.edited_rule


def edit_facts(facts: ExtractedFacts, changes: dict[str, Any]) -> ExtractedFacts:
    """A copy with `changes` applied. Evidence for edited fields is dropped: an edited
    value is hypothetical, not something the documentation said."""
    actual = {k: v for k, v in changes.items() if getattr(facts, k) != v}
    evidence = {k: v for k, v in facts.evidence_snippets.items() if k not in actual}
    return replace(facts, **actual, evidence_snippets=evidence)


def compare(original: ExtractedFacts, edited: ExtractedFacts) -> WhatIfDiff:
    before, after = classify(original), classify(edited)
    flags_before = {f.unesco for f in evaluate_principles(original)}
    flags_after = {f.unesco for f in evaluate_principles(edited)}
    changed = [
        (name, getattr(original, name), getattr(edited, name))
        for name in original.__dataclass_fields__
        if name != "evidence_snippets" and getattr(original, name) != getattr(edited, name)
    ]
    return WhatIfDiff(before.tier, after.tier, before.rule_number, after.rule_number, changed,
                      sorted(flags_after - flags_before), sorted(flags_before - flags_after))


def describe(diff: WhatIfDiff) -> list[str]:
    """Rule-generated sentences for the UI."""
    if not diff.changed_fields:
        return ["No fact has been changed yet: edit a value to see its effect."]
    out = []
    if diff.tier_changed:
        out.append(f"The tier changes from {diff.original_tier.value} (rule {diff.original_rule}) "
                   f"to {diff.edited_tier.value} (rule {diff.edited_rule}).")
    elif diff.rule_changed:
        out.append(f"The tier stays {diff.edited_tier.value}, but a different rule decides it "
                   f"(rule {diff.original_rule} → rule {diff.edited_rule}).")
    else:
        out.append(f"The tier stays {diff.edited_tier.value} (rule {diff.edited_rule}).")
    if diff.removed_flags:
        out.append("No longer flagged: " + ", ".join(diff.removed_flags) + ".")
    if diff.added_flags:
        out.append("Newly flagged: " + ", ".join(diff.added_flags) + ".")
    if not diff.added_flags and not diff.removed_flags:
        out.append("The UNESCO/IEEE principle flags are unchanged.")
    return out
