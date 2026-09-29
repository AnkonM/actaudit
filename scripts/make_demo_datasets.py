"""Build the bundled demo datasets under data/ (blueprint §15.4, Tabs 2, 4 and 5).

Usage: python scripts/make_demo_datasets.py

Writes, reproducibly (fixed seeds, documented in data/README.md):
- data/adult_demo.csv — a 6,000-row sample of UCI Adult (CC BY 4.0) with an
  out-of-fold `predicted_income` column from a logistic regression that does not see
  sex or race. If the UCI download fails, a seeded synthetic stand-in with the same
  columns is written instead and the manifest says so.
- data/cost_proxy_demo.csv — a synthetic dataset built like the Obermeyer et al.
  (Science, 2019) case: two groups with the same distribution of true health need,
  where recorded cost is systematically lower for group B at equal need.
- data/datasets.json — the manifest the app reads (names, sources, default columns).
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ADULT_URL = "https://archive.ics.uci.edu/static/public/2/adult.zip"
ADULT_SEED = 42
ADULT_ROWS = 6000
MODEL_SEED = 0
COST_SEED = 2019
COST_ROWS = 4000
SELECT_SHARE = 0.20  # matches analysis/config.py COST_DEMO_SELECT_SHARE

ADULT_COLUMNS = [
    "age", "workclass", "fnlwgt", "education", "education_num", "marital_status",
    "occupation", "relationship", "race", "sex", "capital_gain", "capital_loss",
    "hours_per_week", "native_country", "income",
]


def fetch_adult() -> pd.DataFrame:
    response = requests.get(ADULT_URL, timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        raw = archive.read("adult.data").decode("utf-8")
    df = pd.read_csv(io.StringIO(raw), header=None, names=ADULT_COLUMNS,
                     skipinitialspace=True, na_values="?")
    df = df.dropna(how="all")
    # fnlwgt is a census sampling weight, not a person attribute; it only confuses demos.
    return df.drop(columns=["fnlwgt"])


def synthetic_adult(rows: int, seed: int) -> pd.DataFrame:
    """Fallback only: a seeded stand-in with Adult's columns (clearly labelled synthetic)."""
    rng = np.random.default_rng(seed)
    sex = rng.choice(["Male", "Female"], rows, p=[0.67, 0.33])
    race = rng.choice(["White", "Black", "Asian-Pac-Islander", "Amer-Indian-Eskimo", "Other"],
                      rows, p=[0.85, 0.10, 0.03, 0.01, 0.01])
    education_num = rng.integers(5, 17, rows)
    hours = np.clip(rng.normal(40, 12, rows), 1, 99).round()
    age = np.clip(rng.normal(38, 13, rows), 17, 90).round()
    logit = -8 + 0.35 * education_num + 0.04 * hours + 0.03 * age + 0.8 * (sex == "Male")
    income = np.where(rng.random(rows) < 1 / (1 + np.exp(-logit)), ">50K", "<=50K")
    return pd.DataFrame({
        "age": age.astype(int),
        "workclass": rng.choice(["Private", "Self-emp-not-inc", "Local-gov", "State-gov"], rows),
        "education": pd.cut(education_num, [0, 9, 10, 13, 20],
                            labels=["HS-or-less", "Some-college", "Bachelors", "Advanced"]).astype(str),
        "education_num": education_num,
        "marital_status": rng.choice(["Married-civ-spouse", "Never-married", "Divorced"], rows),
        "occupation": rng.choice(["Prof-specialty", "Craft-repair", "Sales", "Adm-clerical"], rows),
        "relationship": np.where(sex == "Male", "Husband", "Wife"),
        "race": race, "sex": sex,
        "capital_gain": np.where(rng.random(rows) < 0.08, rng.integers(1000, 20000, rows), 0),
        "capital_loss": 0,
        "hours_per_week": hours.astype(int),
        "native_country": "United-States",
        "income": income,
    })


def add_out_of_fold_predictions(df: pd.DataFrame) -> pd.DataFrame:
    """A plain logistic regression that never sees sex or race, predicted out-of-fold."""
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    features = df.drop(columns=["income", "sex", "race"])
    numeric = features.select_dtypes("number").columns.tolist()
    categorical = [c for c in features.columns if c not in numeric]
    model = make_pipeline(
        ColumnTransformer([
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), numeric),
            ("cat", make_pipeline(SimpleImputer(strategy="most_frequent"),
                                  OneHotEncoder(handle_unknown="ignore", min_frequency=20)), categorical),
        ]),
        LogisticRegression(max_iter=2000, random_state=MODEL_SEED),
    )
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=MODEL_SEED)
    out = df.copy()
    out["predicted_income"] = cross_val_predict(model, features, df["income"], cv=folds)
    return out


def build_adult() -> tuple[pd.DataFrame, dict]:
    try:
        full = fetch_adult()
        sample = full.sample(n=ADULT_ROWS, random_state=ADULT_SEED).reset_index(drop=True)
        synthetic = False
        note = (f"Random sample of {ADULT_ROWS:,} of the {len(full):,} rows of UCI Adult "
                f"(adult.data), seed {ADULT_SEED}; '?' read as missing; fnlwgt dropped.")
    except Exception as exc:  # noqa: BLE001 - any download failure falls back
        print(f"UCI download failed ({exc}); writing the synthetic fallback", file=sys.stderr)
        sample = synthetic_adult(ADULT_ROWS, ADULT_SEED)
        synthetic = True
        note = (f"SYNTHETIC stand-in with UCI Adult's columns ({ADULT_ROWS:,} rows, seed "
                f"{ADULT_SEED}); the UCI download failed when the data was built.")
    sample = add_out_of_fold_predictions(sample)
    meta = {
        "id": "adult",
        "name": "UCI Adult income (synthetic stand-in)" if synthetic else "UCI Adult income (6,000-row sample)",
        "file": "adult_demo.csv",
        "synthetic": synthetic,
        "source": "Synthetic, scripts/make_demo_datasets.py" if synthetic else
                  "Becker & Kohavi (1996), Adult, UCI Machine Learning Repository, "
                  "https://doi.org/10.24432/C5XW20",
        "licence": "CC BY 4.0",
        "note": note + " predicted_income: out-of-fold (5-fold) logistic regression that does "
                       f"not see sex or race, seed {MODEL_SEED}.",
        "protected": ["sex", "race"],
        "label": "income",
        "positive_label": ">50K",
        "prediction": "predicted_income",
    }
    return sample, meta


def build_cost_proxy() -> tuple[pd.DataFrame, dict]:
    """Two groups, identical need; group B's recorded cost is lower at equal need."""
    rng = np.random.default_rng(COST_SEED)
    n = COST_ROWS
    group = rng.permutation(np.repeat(["A", "B"], n // 2))
    age = np.clip(rng.normal(55, 12, n), 18, 90).round().astype(int)
    chronic = rng.poisson(2.2, n)  # same distribution in both groups
    severity = rng.normal(0, 1, n)
    need = np.clip(chronic * 10 + 5 * severity + rng.normal(0, 3, n), 0, None).round(1)
    # Unequal access: at the same need, group B incurs 30% lower cost (the proxy's blind spot).
    access = np.where(group == "B", 0.7, 1.0)
    base = 800 + 180 * need
    annual_cost = (base * access * rng.lognormal(0, 0.25, n)).round(-1)
    prior_year_cost = (base * access * rng.lognormal(0, 0.30, n)).round(-1)
    # Insurance type differs by group, so it can act as a proxy for group membership.
    insurance = np.where(rng.random(n) < np.where(group == "A", 0.65, 0.35), "private", "public")
    df = pd.DataFrame({
        "group": group, "age": age, "insurance_type": insurance,
        "chronic_conditions": chronic, "prior_year_cost": prior_year_cost,
        "annual_cost": annual_cost, "true_need_score": need,
    })
    # The "algorithm": predict next cost from claims-style features (no group, no need score).
    from sklearn.linear_model import LinearRegression

    X = pd.get_dummies(df[["age", "prior_year_cost", "insurance_type"]], drop_first=True, dtype=float)
    df["predicted_cost"] = LinearRegression().fit(X, df["annual_cost"]).predict(X).round(-1)
    cut_cost = df["predicted_cost"].quantile(1 - SELECT_SHARE)
    cut_need = df["true_need_score"].quantile(1 - SELECT_SHARE)
    df["selected_by_cost"] = np.where(df["predicted_cost"] >= cut_cost, "Yes", "No")
    df["high_need"] = np.where(df["true_need_score"] >= cut_need, "Yes", "No")
    meta = {
        "id": "cost_proxy",
        "name": "Cost-as-a-proxy demo (synthetic)",
        "file": "cost_proxy_demo.csv",
        "synthetic": True,
        "source": "Synthetic, scripts/make_demo_datasets.py, modelled on Obermeyer et al., "
                  "Science 366(6464):447-453 (2019), https://doi.org/10.1126/science.aax2342",
        "licence": "CC0 (generated for this project)",
        "note": (f"SYNTHETIC: {n:,} patients, seed {COST_SEED}. Groups A and B have the same "
                 "distribution of true need; at equal need group B's recorded cost is 30% lower "
                 "(unequal access). predicted_cost comes from a linear regression on age, "
                 f"prior-year cost and insurance type; the top {SELECT_SHARE:.0%} by predicted "
                 f"cost are selected_by_cost, the top {SELECT_SHARE:.0%} by true need are "
                 "high_need."),
        "protected": ["group"],
        "label": "high_need",
        "positive_label": "Yes",
        "prediction": "selected_by_cost",
        "need_column": "true_need_score",
        "cost_column": "predicted_cost",
    }
    return df, meta


def main() -> int:
    DATA.mkdir(exist_ok=True)
    manifest = []
    for build in (build_cost_proxy, build_adult):
        df, meta = build()
        df.to_csv(DATA / meta["file"], index=False)
        meta["rows"] = len(df)
        manifest.append(meta)
        print(f"wrote data/{meta['file']} ({len(df):,} rows, synthetic={meta['synthetic']})")
    (DATA / "datasets.json").write_text(json.dumps({"datasets": manifest}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
