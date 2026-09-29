"""Every threshold used by the experiment tabs, in one place (blueprint §15.1).

Each threshold carries its value, what it means and where it comes from, so the UI
can show it next to the results that use it. Values without an external source are
labelled as project choices.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Threshold:
    key: str
    value: float
    label: str  # short name shown in the UI
    meaning: str  # one plain sentence
    source: str  # external source, or "project choice"


PROJECT_CHOICE = "project choice, not a legal or statistical standard"

_THRESHOLDS = [
    # --- Uploads (Tab 2) -------------------------------------------------------
    Threshold("MAX_UPLOAD_MB", 50, "Maximum upload size (MB)",
              "CSV files larger than this are rejected.", PROJECT_CHOICE),
    Threshold("ROW_CAP", 50_000, "Row cap for computation",
              "Larger datasets are randomly sampled down to this many rows (fixed seed).",
              PROJECT_CHOICE),
    Threshold("SAMPLE_SEED", 0, "Sampling seed",
              "Random seed used when sampling an uploaded dataset.", PROJECT_CHOICE),
    # --- Dataset bias (Tab 2) ----------------------------------------------------
    Threshold("MIN_GROUP_SHARE", 0.10, "Minimum group share",
              "A group making up less of the dataset than this is flagged as under-represented.",
              PROJECT_CHOICE),
    Threshold("IMBALANCE_RATIO", 3.0, "Imbalance ratio",
              "Largest group size ÷ smallest group size above this is flagged as imbalanced.",
              PROJECT_CHOICE),
    Threshold("REF_UNDER", 0.80, "Under-representation ratio",
              "Observed share ÷ expected share below this is flagged as under-represented "
              "(mirrors the four-fifths ratio).", PROJECT_CHOICE),
    Threshold("REF_OVER", 1.25, "Over-representation ratio",
              "Observed share ÷ expected share above this is flagged as over-represented "
              "(the reciprocal of 0.8).", PROJECT_CHOICE),
    Threshold("SMALL_CELL", 30, "Small-cell size",
              "Intersectional groups with fewer rows than this are too small for reliable "
              "statistics.", PROJECT_CHOICE),
    Threshold("MISSINGNESS_GAP", 0.05, "Missingness gap",
              "A column whose missing-value rate differs between groups by more than this "
              "(5 percentage points) is flagged.", PROJECT_CHOICE),
    Threshold("BASE_RATE_GAP", 0.10, "Base-rate gap",
              "A difference in positive-label rate between the highest and lowest group "
              "above this (10 percentage points) is flagged.", PROJECT_CHOICE),
    # --- Proxy detection (Tab 4) -------------------------------------------------
    Threshold("ASSOC_MODERATE", 0.10, "Moderate association",
              "Cramér's V or correlation ratio at or above this marks a column as a possible "
              "proxy (Cohen's 'small' effect for Cramér's V with two categories; used for the "
              "correlation ratio too, as a project simplification).",
              "Cohen (1988), Statistical Power Analysis, effect-size conventions"),
    Threshold("ASSOC_STRONG", 0.30, "Strong association",
              "Cramér's V or correlation ratio at or above this marks a column as a likely "
              "proxy (Cohen's 'medium' effect for Cramér's V with two categories; used for the "
              "correlation ratio too, as a project simplification).",
              "Cohen (1988), Statistical Power Analysis, effect-size conventions"),
    Threshold("AUC_PROXY", 0.70, "Reconstruction AUC (proxy risk)",
              "If the other columns predict the protected attribute with a cross-validated "
              "AUC at or above this, the attribute is recoverable from them.", PROJECT_CHOICE),
    Threshold("AUC_STRONG", 0.80, "Reconstruction AUC (strong)",
              "AUC at or above this means the protected attribute is strongly encoded in "
              "the other columns.", PROJECT_CHOICE),
    Threshold("CV_FOLDS", 5, "Cross-validation folds",
              "Number of stratified folds for the reconstruction test.", PROJECT_CHOICE),
    Threshold("MODEL_SEED", 0, "Model seed",
              "Random seed for every model the tabs fit.", PROJECT_CHOICE),
    Threshold("RECON_ROW_CAP", 20_000, "Reconstruction row cap",
              "The reconstruction test uses at most this many rows (fixed-seed sample).",
              PROJECT_CHOICE),
    Threshold("MAX_CATEGORIES", 50, "Maximum categories per column",
              "Categorical columns with more distinct values than this (e.g. IDs) are left "
              "out of association and reconstruction.", PROJECT_CHOICE),
    Threshold("COST_DEMO_SELECT_SHARE", 0.20, "Share selected in the cost demo",
              "The cost-as-a-proxy demo selects this share of patients for the programme.",
              PROJECT_CHOICE),
    # --- Fairness (Tab 5) --------------------------------------------------------
    Threshold("FOUR_FIFTHS", 0.80, "Four-fifths rule",
              "A group's selection rate below this fraction of the highest group's rate is "
              "evidence of adverse impact.",
              "US Uniform Guidelines on Employee Selection Procedures, 29 CFR 1607.4(D)"),
    Threshold("FAIRNESS_DIFF", 0.10, "Fairness difference",
              "Demographic parity, equal opportunity or equalized odds differences above "
              "this (10 percentage points) are flagged.", PROJECT_CHOICE),
]

THRESHOLDS: dict[str, Threshold] = {t.key: t for t in _THRESHOLDS}


def value(key: str) -> float:
    """The threshold's value (raises KeyError on unknown keys)."""
    return THRESHOLDS[key].value
