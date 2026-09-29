"""analysis/data_bias.py on small hand-checked frames."""
import numpy as np
import pandas as pd
import pytest

from analysis import data_bias as db


def frame():
    # 10 rows: sex M×6, F×3, X×1. Values chosen so every number below is easy by hand.
    return pd.DataFrame({
        "sex": ["M"] * 6 + ["F"] * 3 + ["X"],
        "age_band": ["young", "old", "young", "old", "young", "old", "young", "young", "old", "old"],
        "income": [np.nan, 1, 2, 3, 4, 5, np.nan, np.nan, 7, 8],  # M 1/6 missing, F 2/3, X 0
        "hired": ["yes", "yes", "yes", "no", "no", "no", "yes", "no", "no", "no"],
    })


def test_representation_by_hand():
    rep = db.representation(frame(), "sex")
    assert rep.table.set_index("group")["count"].to_dict() == {"M": 6, "F": 3, "X": 1}
    assert rep.table.set_index("group")["share"].to_dict() == pytest.approx({"M": 0.6, "F": 0.3, "X": 0.1})
    assert rep.imbalance_ratio == 6.0 and rep.imbalanced  # 6 / 1 > 3
    assert not rep.table["below_min_share"].any()  # X is exactly 10%, not below it
    assert db.representation(frame(), "sex", min_share=0.2).table.set_index("group")["below_min_share"]["X"]


def test_reference_comparison_normalises_and_flags():
    rep = db.representation(frame(), "sex")
    comp = db.reference_comparison(rep, {"M": 40, "F": 40}).set_index("group")  # -> 50% / 50%
    assert comp.loc["M", "expected_share"] == pytest.approx(0.5)
    assert comp.loc["M", "ratio"] == pytest.approx(1.2) and comp.loc["M", "status"] == "in line"
    assert comp.loc["F", "ratio"] == pytest.approx(0.6) and comp.loc["F", "status"] == "under-represented"


def test_intersectional_counts_and_small_cells():
    inter = db.intersectional_counts(frame(), "sex", "age_band", small_cell=3)
    counts = inter.table.set_index(["sex", "age_band"])["count"].to_dict()
    assert counts[("M", "young")] == 3 and counts[("F", "young")] == 2 and counts[("X", "young")] == 0
    assert inter.empty_cells == 1  # X × young never occurs
    assert inter.small_cells == 3  # F×young=2, F×old=1, X×old=1


def test_missingness_gap_by_hand():
    table = db.missingness_by_group(frame(), "sex").set_index("column")
    assert list(table.index) == ["income"]  # only columns with missing values
    assert table.loc["income", "missing in M"] == pytest.approx(1 / 6)
    assert table.loc["income", "missing in F"] == pytest.approx(2 / 3)
    assert table.loc["income", "gap"] == pytest.approx(2 / 3)  # F 2/3 − X 0
    assert table.loc["income", "flagged"]


def test_label_base_rates_by_hand():
    base = db.label_base_rates(frame(), "sex", "hired", "yes")
    rates = base.table.set_index("group")["base_rate"].to_dict()
    assert rates == pytest.approx({"M": 0.5, "F": 1 / 3, "X": 0.0})
    assert base.gap == pytest.approx(0.5) and base.flagged


def test_findings_are_generated_from_the_numbers():
    df = frame()
    rep = db.representation(df, "sex", min_share=0.2)
    lines = db.findings(rep, None, db.intersectional_counts(df, "sex", "age_band"),
                        db.missingness_by_group(df, "sex"), db.label_base_rates(df, "sex", "hired", "yes"))
    text = "\n".join(lines)
    assert "Under-represented in 'sex': X (10.0%)" in text
    assert "largest group is 6.0× the smallest" in text
    assert "largest gap is 'income' (66.7%" in text
    assert "'M' (50.0%) than for 'X' (0.0%)" in text


def test_load_csv_caps_and_samples():
    data = ("a,b\n" + "\n".join(f"{i},{i % 2}" for i in range(100))).encode()
    loaded = db.load_csv(data, row_cap=10, seed=0)
    assert loaded.rows_original == 100 and loaded.sampled and len(loaded.df) == 10
    assert db.load_csv(data, row_cap=10, seed=0).df.equals(loaded.df)  # fixed seed
    with pytest.raises(db.DatasetError, match="limit is"):
        db.load_csv(data, max_mb=0.0001)


@pytest.mark.parametrize("data,message", [
    (b"\xff\xfe\x00bad", "UTF-8"),
    (b"", "couldn't be read"),
    (b"only_one_column\n1\n2\n", "at least two columns"),
])
def test_load_csv_friendly_errors(data, message):
    with pytest.raises(db.DatasetError, match=message):
        db.load_csv(data)


def test_group_candidates_skip_ids_and_constants():
    df = pd.DataFrame({"id": range(200), "sex": ["M", "F"] * 100, "const": 1})
    assert db.group_column_candidates(df) == ["sex"]
