"""analysis/proxy.py: hand-computed association measures, reconstruction, cost demo."""
import numpy as np
import pandas as pd
import pytest

from analysis import proxy
from schema import TargetType
from tests.test_rules import make_facts


def _table(counts):
    """Expand a 2×2 contingency table into two columns."""
    rows = []
    for (x, y), n in counts.items():
        rows += [(x, y)] * n
    return pd.DataFrame(rows, columns=["x", "y"])


def test_cramers_v_by_hand():
    # [[20, 10], [10, 20]]: n=60, every expected count 15, chi2 = 4 × 25/15 = 6.667,
    # V = sqrt(6.667 / (60 × 1)) = 1/3.
    df = _table({("a", "p"): 20, ("a", "q"): 10, ("b", "p"): 10, ("b", "q"): 20})
    assert proxy.cramers_v(df["x"], df["y"]) == pytest.approx(1 / 3)
    perfect = _table({("a", "p"): 10, ("b", "q"): 10})
    assert proxy.cramers_v(perfect["x"], perfect["y"]) == pytest.approx(1.0)
    independent = _table({("a", "p"): 5, ("a", "q"): 5, ("b", "p"): 5, ("b", "q"): 5})
    assert proxy.cramers_v(independent["x"], independent["y"]) == pytest.approx(0.0)


def test_correlation_ratio_by_hand():
    # groups a:[1,2,3], b:[4,5,6]; grand mean 3.5; between = 3×1.5² + 3×1.5² = 13.5;
    # total = 17.5; eta = sqrt(13.5/17.5).
    g = pd.Series(list("aaabbb"))
    v = pd.Series([1, 2, 3, 4, 5, 6])
    assert proxy.correlation_ratio(g, v) == pytest.approx(np.sqrt(13.5 / 17.5))
    assert proxy.correlation_ratio(g, pd.Series([1, 2, 3, 1, 2, 3])) == pytest.approx(0.0)


def _synthetic(n=600, seed=1):
    rng = np.random.default_rng(seed)
    group = rng.choice(["a", "b"], n)
    return pd.DataFrame({
        "group": group,
        "noise1": rng.normal(size=n),
        "noise2": rng.choice(["x", "y", "z"], n),
        "leak": np.where(group == "a", "alpha", "beta"),
    })


def test_association_ranking_finds_the_leak_first():
    table = proxy.association_ranking(_synthetic(), "group")
    assert table.iloc[0]["column"] == "leak" and table.iloc[0]["level"] == "strong"
    assert table.set_index("column").loc["noise1", "level"] == "weak"


def test_reconstruction_near_chance_on_noise_and_perfect_on_a_leak():
    noise = proxy.reconstruction_test(_synthetic().drop(columns=["leak"]), "group")
    assert 0.35 < noise.auc_mean < 0.65 and noise.level == "low"
    leaked = proxy.reconstruction_test(_synthetic(), "group")
    assert leaked.auc_mean > 0.99 and leaked.level == "strong"
    assert leaked.top_features[0][0] == "leak"


def test_reconstruction_is_deterministic_and_respects_exclusions():
    a = proxy.reconstruction_test(_synthetic(), "group", exclude=["leak"])
    b = proxy.reconstruction_test(_synthetic(), "group", exclude=["leak"])
    assert a.auc_mean == b.auc_mean and "leak" not in a.features_used


def test_reconstruction_refuses_tiny_groups():
    df = _synthetic().assign(group=["a"] * 597 + ["b"] * 3)
    with pytest.raises(proxy.ReconstructionError, match="smallest group"):
        proxy.reconstruction_test(df, "group")


def test_cost_demo_selects_group_b_less_at_equal_need():
    df = pd.read_csv("data/cost_proxy_demo.csv")
    result = proxy.cost_proxy_selection(df, "group", "true_need_score", "predicted_cost")
    overall = result.overall.set_index("group")
    assert abs(overall.loc["A", "selected_by_need"] - overall.loc["B", "selected_by_need"]) < 0.02
    assert overall.loc["B", "selected_by_cost"] < overall.loc["A", "selected_by_cost"] - 0.10
    top = result.by_band[result.by_band["need_band"].str.endswith("(highest need)")].set_index("group")
    assert top.loc["B", "selected_by_cost"] < top.loc["A", "selected_by_cost"]
    assert "Even among the highest-need patients" in " ".join(proxy.cost_proxy_findings(result, "group"))


@pytest.mark.parametrize("target,status", [
    (TargetType.COST_OR_SPENDING, "flag"),
    (TargetType.ARRESTS_OR_POLICE_CONTACT, "flag"),
    (TargetType.ENGAGEMENT_OR_CLICKS, "flag"),
    (TargetType.PAST_HUMAN_DECISIONS, "flag"),
    (TargetType.DIRECT_OUTCOME, "no_flag"),
    (TargetType.OTHER, "no_flag"),
    (TargetType.UNKNOWN, "unknown"),
])
def test_target_proxy_check(target, status):
    result = proxy.target_proxy_check(make_facts(target_type=target, target_variable="x"))
    assert result.status == status
    if status == "unknown":
        assert "doesn't state what the system predicts" in result.message
    if target == TargetType.COST_OR_SPENDING:
        assert "Obermeyer" in result.pattern.reference and "need" in result.message


def test_every_pattern_has_a_reference_link():
    for pattern in proxy.PROXY_PATTERNS.values():
        assert pattern.reference_url.startswith("https://") and pattern.can_hide.endswith(".")
