"""The bundled demo datasets and their manifest (data/datasets.json)."""
import pandas as pd

from analysis import data_bias


def test_manifest_lists_both_demos_with_existing_columns():
    demos = {d["id"]: d for d in data_bias.demo_datasets()}
    assert set(demos) == {"adult", "cost_proxy"}
    for meta in demos.values():
        loaded, _ = data_bias.load_demo(meta["id"])
        for column in [*meta["protected"], meta["label"], meta["prediction"]]:
            assert column in loaded.df.columns
        assert meta["positive_label"] in set(loaded.df[meta["label"]])
        assert meta["licence"] and meta["source"] and len(loaded.df) == meta["rows"]
    assert demos["cost_proxy"]["synthetic"] is True


def test_cost_demo_has_equal_need_but_unequal_cost():
    df = pd.read_csv("data/cost_proxy_demo.csv")
    by_group = df.groupby("group")
    assert by_group.size().tolist() == [2000, 2000]
    need = by_group["true_need_score"].mean()
    assert abs(need["A"] - need["B"]) < 1.0  # same need
    assert by_group["annual_cost"].mean()["B"] < 0.8 * by_group["annual_cost"].mean()["A"]
    high = df.groupby("group")["high_need"].apply(lambda s: (s == "Yes").mean())
    assert abs(high["A"] - high["B"]) < 0.02


def test_data_readme_documents_every_file():
    readme = open("data/README.md").read()
    for name in ("adult_demo.csv", "cost_proxy_demo.csv", "datasets.json", "CC BY 4.0",
                 "make_demo_datasets.py", "2019", "42"):
        assert name in readme
