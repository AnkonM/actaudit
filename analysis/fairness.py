"""Tab 5A · Fairness metrics (Experiment 5), computed with fairlearn.

Per group: selection rate, true-positive rate (TPR), false-positive rate (FPR),
precision and confusion counts. Summary: demographic parity difference, equal
opportunity difference, equalized odds difference and the disparate-impact ratio
against the four-fifths rule. A rate is undefined (NaN) for a group with no cases in
its denominator (e.g. TPR with no actual positives); differences ignore undefined rates.
"""
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from fairlearn.metrics import MetricFrame, count, false_positive_rate, selection_rate, true_positive_rate

from analysis import config


class FairnessError(ValueError):
    """The metrics can't be computed on this selection. `str(err)` is user-facing."""


def _counts(y_true: pd.Series, y_pred: pd.Series) -> dict[str, int]:
    return {
        "tp": int((y_true & y_pred).sum()), "fp": int((~y_true & y_pred).sum()),
        "tn": int((~y_true & ~y_pred).sum()), "fn": int((y_true & ~y_pred).sum()),
    }


def group_metrics(df: pd.DataFrame, attribute: str, label: str, prediction: str,
                  positive: Any) -> pd.DataFrame:
    """One row per group: n, selection_rate, tpr, fpr, precision and tp/fp/tn/fn."""
    data = df[[attribute, label, prediction]].dropna()
    if data.empty:
        raise FairnessError("No rows have a value for the attribute, label and prediction.")
    y_true = data[label] == positive
    y_pred = data[prediction] == positive
    groups = data[attribute].astype(str)
    if groups.nunique() < 2:
        raise FairnessError(f"'{attribute}' has fewer than two groups in these rows.")
    frame = MetricFrame(
        metrics={"n": count, "selection_rate": selection_rate,
                 "tpr": true_positive_rate, "fpr": false_positive_rate},
        y_true=y_true, y_pred=y_pred, sensitive_features=groups,
    )
    table = frame.by_group.reset_index().rename(columns={"sensitive_feature_0": "group"})
    table = table.rename(columns={table.columns[0]: "group"})
    counts = pd.DataFrame([{"group": g, **_counts(y_true[groups == g], y_pred[groups == g])}
                           for g in table["group"]])
    table = table.merge(counts, on="group")
    table["n"] = table["n"].astype(int)
    # Undefined rates: fairlearn/sklearn report 0 when the denominator is empty.
    table.loc[table["tp"] + table["fn"] == 0, "tpr"] = np.nan
    table.loc[table["fp"] + table["tn"] == 0, "fpr"] = np.nan
    predicted_pos = table["tp"] + table["fp"]
    table["precision"] = np.where(predicted_pos > 0, table["tp"] / predicted_pos.where(predicted_pos > 0, 1), np.nan)
    columns = ["group", "n", "selection_rate", "tpr", "fpr", "precision", "tp", "fp", "tn", "fn"]
    return table[columns].sort_values("n", ascending=False).reset_index(drop=True)


@dataclass(frozen=True)
class FairnessSummary:
    demographic_parity_difference: float  # max - min selection rate
    equal_opportunity_difference: float  # max - min TPR
    equalized_odds_difference: float  # max(TPR difference, FPR difference)
    disparate_impact_ratio: float  # min / max selection rate
    passes_four_fifths: bool
    lowest_group: str  # lowest selection rate
    highest_group: str
    flags: list[str]


def _spread(values: pd.Series) -> float:
    v = values.dropna()
    return float(v.max() - v.min()) if len(v) >= 2 else float("nan")


def summarise(table: pd.DataFrame) -> FairnessSummary:
    four_fifths = config.value("FOUR_FIFTHS")
    diff_limit = config.value("FAIRNESS_DIFF")
    rates = table.set_index("group")["selection_rate"]
    dpd = _spread(rates)
    eod = _spread(table["tpr"])
    fpr_diff = _spread(table["fpr"])
    eq_odds = float(np.nanmax([eod, fpr_diff])) if not (np.isnan(eod) and np.isnan(fpr_diff)) else float("nan")
    di = float(rates.min() / rates.max()) if rates.max() > 0 else float("nan")
    flags = []
    if not np.isnan(di) and di < four_fifths:
        flags.append(f"Disparate impact: group '{rates.idxmin()}' is selected at {di:.2f}× the rate "
                     f"of group '{rates.idxmax()}', below the four-fifths ({four_fifths:g}) threshold.")
    if dpd > diff_limit:
        flags.append(f"Demographic parity difference {dpd:.1%} exceeds {diff_limit:.0%}: groups are "
                     "selected at noticeably different rates.")
    if not np.isnan(eod) and eod > diff_limit:
        flags.append(f"Equal opportunity difference {eod:.1%} exceeds {diff_limit:.0%}: qualified "
                     "people in some groups are missed more often.")
    if not np.isnan(eq_odds) and eq_odds > diff_limit and eq_odds != eod:
        flags.append(f"Equalized odds difference {eq_odds:.1%} exceeds {diff_limit:.0%}: false "
                     "positives are spread unevenly across groups.")
    if not flags:
        flags.append(f"No metric crosses its threshold (four-fifths {four_fifths:g}; differences "
                     f"{diff_limit:.0%}).")
    return FairnessSummary(dpd, eod, eq_odds, di, bool(np.isnan(di) or di >= four_fifths),
                           str(rates.idxmin()), str(rates.idxmax()), flags)
