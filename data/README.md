# Bundled data

Everything in this folder is generated or fetched by a script in `scripts/`, with fixed
seeds, so it can be rebuilt byte-for-byte. The app reads `datasets.json` (the manifest)
to list the demo datasets.

| File | What it is | Source and licence | Built by | Seeds |
|---|---|---|---|---|
| `adult_demo.csv` | 6,000-row random sample of UCI Adult (`adult.data`, 32,561 rows) with an extra `predicted_income` column. `?` is read as missing; `fnlwgt` (a census sampling weight) is dropped. | Becker, B. & Kohavi, R. (1996). *Adult* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5XW20 — **CC BY 4.0**. Downloaded from https://archive.ics.uci.edu/static/public/2/adult.zip | `scripts/make_demo_datasets.py` | sample: 42; model/folds: 0 |
| `cost_proxy_demo.csv` | **Synthetic.** 4,000 patients in groups A and B with the same distribution of true need; at equal need group B's recorded cost is 30% lower (unequal access). Built like the case in Obermeyer et al. (2019), *Science* 366(6464):447–453, https://doi.org/10.1126/science.aax2342 | Generated for this project (CC0) | `scripts/make_demo_datasets.py` | 2019 |
| `datasets.json` | Manifest: name, provenance note, licence and default column choices for each demo | — | `scripts/make_demo_datasets.py` | — |
| `cases/` | Case Library (Tab 8) | see `cases/cases.json` | hand-written, sources per case | — |
| `robustness/` | Robustness-study runs (Tab 7B) | ActAudit's own outputs | `scripts/robustness_study.py` | — |

## `adult_demo.csv`: the prediction column

`predicted_income` is an out-of-fold prediction (5-fold stratified cross-validation,
shuffle seed 0) from a logistic regression (standardised numeric features, one-hot
categorical features, `random_state=0`) that **does not see `sex` or `race`**. Every row's
prediction comes from a model that never saw that row. It exists so Tab 5 can show
fairness metrics on a realistic model. Its disparities by sex come through proxies such
as `relationship` (Husband/Wife), which Tab 4's reconstruction test surfaces.

If the UCI download fails when the script runs, it writes a seeded synthetic stand-in
with the same columns instead; the manifest then marks the dataset `synthetic: true`
and the app labels it as synthetic.

## `cost_proxy_demo.csv`: how it is generated

- `group`: A or B, exactly 50/50.
- `age` ~ Normal(55, 12), clipped to 18–90; `chronic_conditions` ~ Poisson(2.2) — the same distributions in both groups.
- `true_need_score` = 10 × chronic_conditions + 5 × severity + noise, severity ~ Normal(0, 1), noise ~ Normal(0, 3).
- `annual_cost` and `prior_year_cost` = (800 + 180 × need) × access × log-normal noise, with **access = 1.0 for A and 0.7 for B**.
- `insurance_type`: private with probability 0.65 in A and 0.35 in B (a proxy for group).
- `predicted_cost`: linear regression of `annual_cost` on age, prior-year cost and insurance type (no group, no need score) — "the algorithm".
- `selected_by_cost` = top 20% by predicted cost; `high_need` = top 20% by true need.

Result: both groups have 20% high-need patients, but selection by predicted cost picks about 28% of A and 12% of B.

Rebuild everything with:

```bash
python scripts/make_demo_datasets.py
```
