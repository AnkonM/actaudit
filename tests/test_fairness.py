"""analysis/fairness.py on a 10-row example computed by hand, cross-checked with fairlearn."""
import numpy as np
import pandas as pd
import pytest
from fairlearn.metrics import demographic_parity_difference, equalized_odds_difference

from analysis import fairness


def frame():
    # group a: y=[1,1,0,0,0], p=[1,0,1,0,0] -> TP1 FN1 FP1 TN2: sel .4, TPR .5, FPR 1/3, prec .5
    # group b: y=[1,1,1,0,0], p=[1,1,1,1,0] -> TP3 FN0 FP1 TN1: sel .8, TPR 1, FPR .5, prec .75
    return pd.DataFrame({
        "g": list("aaaaabbbbb"),
        "y": [1, 1, 0, 0, 0, 1, 1, 1, 0, 0],
        "p": [1, 0, 1, 0, 0, 1, 1, 1, 1, 0],
    })


def test_group_metrics_by_hand():
    t = fairness.group_metrics(frame(), "g", "y", "p", 1).set_index("group")
    assert t.loc["a", ["selection_rate", "tpr", "fpr", "precision"]].tolist() == pytest.approx([0.4, 0.5, 1 / 3, 0.5])
    assert t.loc["b", ["selection_rate", "tpr", "fpr", "precision"]].tolist() == pytest.approx([0.8, 1.0, 0.5, 0.75])
    assert t.loc["a", ["tp", "fp", "tn", "fn"]].tolist() == [1, 1, 2, 1]


def test_summary_by_hand_and_against_fairlearn():
    df = frame()
    s = fairness.summarise(fairness.group_metrics(df, "g", "y", "p", 1))
    assert s.demographic_parity_difference == pytest.approx(0.4)
    assert s.equal_opportunity_difference == pytest.approx(0.5)
    assert s.equalized_odds_difference == pytest.approx(0.5)  # max(0.5, 1/6)
    assert s.disparate_impact_ratio == pytest.approx(0.5) and not s.passes_four_fifths
    assert s.demographic_parity_difference == pytest.approx(
        demographic_parity_difference(df["y"], df["p"], sensitive_features=df["g"]))
    assert s.equalized_odds_difference == pytest.approx(
        equalized_odds_difference(df["y"], df["p"], sensitive_features=df["g"]))
    assert any("four-fifths" in f for f in s.flags)


def test_undefined_rates_are_nan_and_ignored():
    df = pd.DataFrame({"g": list("aaabbb"), "y": [0, 0, 0, 1, 0, 1], "p": [1, 0, 0, 1, 0, 0]})
    t = fairness.group_metrics(df, "g", "y", "p", 1).set_index("group")
    assert np.isnan(t.loc["a", "tpr"])  # group a has no actual positives
    s = fairness.summarise(t.reset_index())
    assert np.isnan(s.equal_opportunity_difference)  # only one defined TPR


def test_string_labels_and_equal_rates_pass():
    df = pd.DataFrame({"g": list("aabb"), "y": ["yes", "no", "yes", "no"], "p": ["yes", "no", "yes", "no"]})
    s = fairness.summarise(fairness.group_metrics(df, "g", "y", "p", "yes"))
    assert s.passes_four_fifths and s.flags[0].startswith("No metric crosses")


def test_single_group_is_a_friendly_error():
    with pytest.raises(fairness.FairnessError, match="fewer than two groups"):
        fairness.group_metrics(frame().assign(g="a"), "g", "y", "p", 1)
