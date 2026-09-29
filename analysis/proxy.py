"""Tab 4 · Proxy Audit (Experiment 4).

A. Target-label proxy check: a fixed table maps the extracted target_type to known
   proxy patterns (what the proxy stands in for, what it can hide, a reference case).
B. Data proxy detection: how strongly each non-protected column is associated with a
   protected attribute (Cramér's V / correlation ratio), a reconstruction test (can a
   simple fixed-seed model predict the protected attribute from the other columns?),
   and the cost-as-a-proxy selection demo.

All deterministic: no LLM, fixed seeds, thresholds from analysis/config.py.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis import config
from schema import ExtractedFacts, TargetType


# --- A. Target-label proxy check ---------------------------------------------------------

@dataclass(frozen=True)
class ProxyPattern:
    target_type: TargetType
    proxy: str  # what is measured
    stands_in_for: str  # what it is used as a stand-in for
    can_hide: str  # what the substitution can hide
    reference: str
    reference_url: str


PROXY_PATTERNS: dict[TargetType, ProxyPattern] = {
    TargetType.COST_OR_SPENDING: ProxyPattern(
        TargetType.COST_OR_SPENDING, "cost or spending", "need",
        "Groups who face barriers to access spend less at the same level of need, so a "
        "cost target ranks them as less needy and under-serves them.",
        "Obermeyer, Powers, Vogeli & Mullainathan (2019), 'Dissecting racial bias in an "
        "algorithm used to manage the health of populations', Science 366(6464):447–453",
        "https://doi.org/10.1126/science.aax2342",
    ),
    TargetType.ARRESTS_OR_POLICE_CONTACT: ProxyPattern(
        TargetType.ARRESTS_OR_POLICE_CONTACT, "arrests or police contact", "crime or reoffending",
        "Arrests reflect where and whom police patrol as well as offending, so heavily "
        "policed groups look riskier than they are.",
        "Angwin, Larson, Mattu & Kirchner (2016), 'Machine Bias', ProPublica (COMPAS); "
        "Lum & Isaac (2016), 'To predict and serve?', Significance 13(5):14–19",
        "https://www.propublica.org/article/machine-bias-risk-assessments-in-criminal-sentencing",
    ),
    TargetType.ENGAGEMENT_OR_CLICKS: ProxyPattern(
        TargetType.ENGAGEMENT_OR_CLICKS, "engagement or clicks", "quality or genuine interest",
        "Engagement rewards what grabs attention — outrage, sensationalism, stereotypes — "
        "rather than what is accurate, useful or wanted on reflection.",
        "Milli, Carroll, Wang, Pandey, Zhao & Dragan (2025), 'Engagement, user satisfaction, "
        "and the amplification of divisive content on social media', PNAS Nexus 4(3)",
        "https://doi.org/10.1093/pnasnexus/pgaf062",
    ),
    TargetType.PAST_HUMAN_DECISIONS: ProxyPattern(
        TargetType.PAST_HUMAN_DECISIONS, "past human decisions", "merit or suitability",
        "Historical decisions carry the biases of the people who made them; a model trained "
        "to copy them reproduces those biases at scale.",
        "Dastin (2018), 'Amazon scraps secret AI recruiting tool that showed bias against "
        "women', Reuters",
        "https://www.reuters.com/article/us-amazon-com-jobs-automation-insight-idUSKCN1MK08G",
    ),
}


@dataclass(frozen=True)
class TargetProxyResult:
    target_variable: str
    target_type: TargetType
    status: str  # "flag" | "no_flag" | "unknown"
    pattern: ProxyPattern | None
    message: str


def target_proxy_check(facts: ExtractedFacts) -> TargetProxyResult:
    t = facts.target_type
    if t in PROXY_PATTERNS:
        p = PROXY_PATTERNS[t]
        message = (f"The system predicts {p.proxy}, a known stand-in for {p.stands_in_for}. "
                   f"{p.can_hide}")
        return TargetProxyResult(facts.target_variable, t, "flag", p, message)
    if t == TargetType.UNKNOWN:
        return TargetProxyResult(
            facts.target_variable, t, "unknown", None,
            "The documentation doesn't state what the system predicts or optimises, so its "
            "target can't be checked for proxy problems — itself a documentation gap.")
    if t == TargetType.DIRECT_OUTCOME:
        message = ("The system predicts the outcome of interest directly, so no known proxy "
                   "pattern applies. Measurement bias in how that outcome was recorded is "
                   "still possible.")
    else:
        message = ("The stated target matches none of the known proxy patterns in the table; "
                   "no flag is raised.")
    return TargetProxyResult(facts.target_variable, t, "no_flag", None, message)


# --- B. Association measures --------------------------------------------------------------

def cramers_v(x: pd.Series, y: pd.Series) -> float:
    """Cramér's V from the chi-squared statistic of the contingency table (no bias
    correction). 0 = independent, 1 = one determines the other. Rows with a missing
    value in either series are dropped."""
    data = pd.DataFrame({"x": x, "y": y}).dropna()
    table = pd.crosstab(data["x"].astype(str), data["y"].astype(str)).to_numpy(dtype=float)
    n = table.sum()
    r, k = table.shape
    if n == 0 or min(r, k) < 2:
        return 0.0
    expected = table.sum(axis=1, keepdims=True) @ table.sum(axis=0, keepdims=True) / n
    chi2 = float(((table - expected) ** 2 / expected).sum())
    return float(np.sqrt(chi2 / (n * (min(r, k) - 1))))


def correlation_ratio(categories: pd.Series, values: pd.Series) -> float:
    """Correlation ratio η: the share of a numeric column's spread explained by group
    membership, square-rooted (0 = same mean in every group, 1 = fully determined)."""
    data = pd.DataFrame({"g": categories, "v": pd.to_numeric(values, errors="coerce")}).dropna()
    if data.empty:
        return 0.0
    total = float(((data["v"] - data["v"].mean()) ** 2).sum())
    if total == 0:
        return 0.0
    stats = data.groupby(data["g"].astype(str))["v"].agg(["count", "mean"])
    between = float((stats["count"] * (stats["mean"] - data["v"].mean()) ** 2).sum())
    return float(np.sqrt(between / total))


def _level(value: float) -> str:
    if value >= config.value("ASSOC_STRONG"):
        return "strong"
    if value >= config.value("ASSOC_MODERATE"):
        return "moderate"
    return "weak"


def association_ranking(df: pd.DataFrame, protected: str, exclude: list[str] | tuple = ()) -> pd.DataFrame:
    """Every other column's association with `protected`, strongest first.

    Numeric columns use the correlation ratio; categorical ones Cramér's V. Columns in
    `exclude` (e.g. other protected attributes) and high-cardinality categorical columns
    (more than MAX_CATEGORIES values, e.g. IDs) are skipped.
    """
    max_cat = config.value("MAX_CATEGORIES")
    rows = []
    for column in df.columns:
        if column == protected or column in exclude:
            continue
        series = df[column]
        if pd.api.types.is_numeric_dtype(series) and series.nunique(dropna=True) > 10:
            value, kind, measure = correlation_ratio(df[protected], series), "numeric", "correlation ratio"
        elif series.nunique(dropna=True) <= max_cat:
            value, kind, measure = cramers_v(df[protected], series), "categorical", "Cramér's V"
        else:
            continue
        rows.append({"column": column, "kind": kind, "measure": measure,
                     "value": round(value, 4), "level": _level(value)})
    table = pd.DataFrame(rows, columns=["column", "kind", "measure", "value", "level"])
    return table.sort_values("value", ascending=False).reset_index(drop=True)


# --- B. Reconstruction test ---------------------------------------------------------------

@dataclass(frozen=True)
class ReconstructionResult:
    protected: str
    auc_mean: float
    auc_std: float
    rows_used: int
    classes: int
    features_used: list[str]
    top_features: list[tuple[str, float]]  # (column, AUC drop when shuffled)
    level: str  # "strong" | "proxy risk" | "low"
    interpretation: str


class ReconstructionError(ValueError):
    """The test can't run on this data. `str(err)` is user-facing."""


def reconstruction_test(df: pd.DataFrame, protected: str, exclude: list[str] | tuple = (),
                        seed: int | None = None, folds: int | None = None,
                        row_cap: int | None = None) -> ReconstructionResult:
    """Can a simple model predict the protected attribute from the other columns?

    Logistic regression (standardised numeric + one-hot categorical features, fixed
    seed), stratified k-fold cross-validated AUC (macro one-vs-rest with more than two
    groups). Top features: permutation importance (mean AUC drop over 5 shuffles of
    each original column) on a model refitted on all rows used.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    seed = int(config.value("MODEL_SEED") if seed is None else seed)
    folds = int(config.value("CV_FOLDS") if folds is None else folds)
    row_cap = int(config.value("RECON_ROW_CAP") if row_cap is None else row_cap)
    max_cat = config.value("MAX_CATEGORIES")

    data = df[df[protected].notna()]
    if len(data) > row_cap:
        data = data.sample(n=row_cap, random_state=seed)
    y = data[protected].astype(str)
    counts = y.value_counts()
    if len(counts) < 2:
        raise ReconstructionError(f"'{protected}' has fewer than two groups in the data.")
    if counts.min() < folds:
        raise ReconstructionError(
            f"The smallest group of '{protected}' has {counts.min()} rows; at least {folds} "
            "are needed for cross-validation.")
    numeric, categorical = [], []
    for column in data.columns:
        if column == protected or column in exclude:
            continue
        if pd.api.types.is_numeric_dtype(data[column]):
            numeric.append(column)
        elif data[column].nunique(dropna=True) <= max_cat:
            categorical.append(column)
    if not numeric and not categorical:
        raise ReconstructionError("There are no usable non-protected columns.")
    X = data[numeric + categorical].copy()
    for column in categorical:
        X[column] = X[column].astype("object").where(X[column].notna(), "(missing)").astype(str)
    preprocess = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])
    model = make_pipeline(preprocess, LogisticRegression(max_iter=2000, random_state=seed))
    scoring = "roc_auc" if len(counts) == 2 else "roc_auc_ovr"
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    scores = cross_val_score(model, X, y, cv=cv, scoring=scoring)

    # Top features: permutation importance on the refitted model — how much the AUC drops
    # when one original column is shuffled. Measured per column (not per one-hot level),
    # so columns with many categories aren't favoured.
    model.fit(X, y)
    perm = permutation_importance(model, X, y, scoring=scoring, n_repeats=5, random_state=seed)
    drops = {c: max(float(d), 0.0) for c, d in zip(X.columns, perm.importances_mean)}
    top = sorted(drops.items(), key=lambda t: -t[1])[:5]

    auc = float(scores.mean())
    if auc >= config.value("AUC_STRONG"):
        level = "strong"
        interpretation = (f"The other columns predict '{protected}' very well (AUC {auc:.2f}): "
                          "the protected attribute is strongly encoded in them, so removing it "
                          "from a model would not stop the model from using it.")
    elif auc >= config.value("AUC_PROXY"):
        level = "proxy risk"
        interpretation = (f"The other columns predict '{protected}' fairly well (AUC {auc:.2f}): "
                          "together they act as a proxy for it.")
    else:
        level = "low"
        interpretation = (f"The other columns predict '{protected}' only weakly (AUC {auc:.2f}; "
                          "0.5 is chance): little proxy risk from this simple model.")
    return ReconstructionResult(protected, auc, float(scores.std()), len(data), len(counts),
                                numeric + categorical, top, level, interpretation)


# --- B. Cost-as-a-proxy demo -------------------------------------------------------------

@dataclass(frozen=True)
class CostProxyResult:
    by_band: pd.DataFrame  # need_band, group, patients, selected_by_cost, selected_by_need
    overall: pd.DataFrame  # group, patients, mean_need, selected_by_cost, selected_by_need
    share: float


def cost_proxy_selection(df: pd.DataFrame, group: str, need: str, cost: str,
                         share: float | None = None, bands: int = 5) -> CostProxyResult:
    """Select the top `share` of patients by predicted cost and, separately, by true
    need; report each group's selection rate within each band of true need.

    If cost were a fair proxy, groups at the same need level would be selected at the
    same rate. A gap within a band shows the proxy treating equally needy people
    differently.
    """
    share = config.value("COST_DEMO_SELECT_SHARE") if share is None else share
    data = df[[group, need, cost]].dropna().copy()
    data["by_cost"] = data[cost] >= data[cost].quantile(1 - share)
    data["by_need"] = data[need] >= data[need].quantile(1 - share)
    labels = [f"Q{i + 1}" for i in range(bands)]
    labels[0] += " (lowest need)"
    labels[-1] += " (highest need)"
    data["need_band"] = pd.qcut(data[need].rank(method="first"), bands, labels=labels)
    grouped = data.groupby(["need_band", group], observed=True)
    by_band = grouped.agg(patients=("by_cost", "size"), selected_by_cost=("by_cost", "mean"),
                          selected_by_need=("by_need", "mean")).reset_index()
    by_band["need_band"] = by_band["need_band"].astype(str)
    overall = data.groupby(group).agg(patients=("by_cost", "size"), mean_need=(need, "mean"),
                                      selected_by_cost=("by_cost", "mean"),
                                      selected_by_need=("by_need", "mean")).reset_index()
    return CostProxyResult(by_band, overall, share)


def cost_proxy_findings(result: CostProxyResult, group: str) -> list[str]:
    """Rule-generated summary of the cost demo."""
    o = result.overall.set_index(group)
    if len(o) < 2:
        return []
    lo_cost = o["selected_by_cost"].idxmin()
    hi_cost = o["selected_by_cost"].idxmax()
    out = [
        f"Selecting the top {result.share:.0%} by predicted cost picks {o.loc[hi_cost, 'selected_by_cost']:.1%} "
        f"of group {hi_cost} but only {o.loc[lo_cost, 'selected_by_cost']:.1%} of group {lo_cost}, "
        f"although their average true need is {o.loc[hi_cost, 'mean_need']:.1f} vs "
        f"{o.loc[lo_cost, 'mean_need']:.1f}.",
        "Selecting by true need instead picks "
        + " and ".join(f"{o.loc[g, 'selected_by_need']:.1%} of group {g}" for g in o.index) + ".",
    ]
    top = result.by_band[result.by_band["need_band"].str.endswith("(highest need)")]
    if len(top) >= 2:
        t = top.set_index(group)["selected_by_cost"]
        out.append(f"Even among the highest-need patients, cost-based selection picks "
                   f"{t.max():.1%} of group {t.idxmax()} vs {t.min():.1%} of group {t.idxmin()}: "
                   "equally needy people are treated differently because the proxy "
                   "under-measures one group's need.")
    return out
