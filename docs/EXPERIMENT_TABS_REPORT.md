# ActAudit experiment tabs: hand-off report

Branch: `feature/experiment-tabs`, created from `main` at `4490dc6e11f74449cb9c7628a9ae98ebb30191f6` (recorded before any work). `main` was never checked out for writing, committed to, rebased or pushed; its hash is unchanged (see the end of this report). Spec: blueprint Section 15. Phases are numbered 9–16, continuing the blueprint roadmap.

## Progress log

Resume from this log and the blueprint alone. Each phase ended with one commit and a push of `feature/experiment-tabs` (never `main`).

| Phase | Status | Commit | Notes |
|---|---|---|---|
| 9 — Branch setup + blueprint | done | 227c1c7 | §5 schema v2 rows, §6.2 Rule 0 note, §11 tree, §12 Phases 9–16, §14 decision log, §15 spec; this report. History scanned for keys: clean. Baseline suite: 174 passed, 1 skipped. |
| 10 — Schema v2, Rule 0, trace, fixture compat; recording (1) | done | 625be6a | Art. 2(3), 3(60), 9, 10, 14, 15, 27, 50, 113 verified against the Official Journal text. Recording (1): 4 of 7 quick-picks re-recorded on v2, tiers unchanged. |
| 11 — UI restructure + Tab 1 | done | 59cad67 | Eight lazy tabs with verbatim captions; Tab 1 migrated + ethical analysis; tab_grouping re-recorded (5 of 7). |
| 12 — Tabs 2, 4, 5 + datasets | done | 4091339 | Demo datasets reproducible; fairlearn; chart-height fix after browser check. |
| 13 — Tabs 3, 6, 7A; recording (2) | done, recording pending | a5b26fc | Recording (2) blocked by the daily quota. |
| 14 — Tab 8; recording (3) | done, recording pending | f02e141 | 7 sourced cases. Recording (3) blocked by the daily quota. |
| 15 — Robustness study + Tab 7B; recording (4) | done, recording pending | 86817a6 | Study script tested with a model-aware fake client. Recording (4) blocked by the daily quota. |
| 16 — Final verification + hand-off | done | (final commit) | 357 passed, 1 skipped; clean-copy install and boot; 34 screenshots reviewed; this report. |

**Pending recording:** 14 fixtures and the 38-run robustness study, all blocked by the Gemini free-tier daily quota (every model returned HTTP 429 from about 21:45 CEST on 29 September 2026; it resets at 00:00 PDT = 09:00 CEST). **One command completes everything:** `python scripts/record_all.py` (details under [Recording status](#recording-status)).

## What was built

ActAudit is now eight tabs, one per course experiment. Every tab keeps the project's central rule: the LLM only extracts observable facts; every judgment comes from a fixed, published rule table or plain computation, with its thresholds shown next to the result.

| Tab | Experiment (verbatim caption) | What it does | Backend |
|---|---|---|---|
| 1 · System Audit | Experiment 1 — Ethical Analysis of AI Applications | Everything the app did before (inputs, quick-picks, verdict, why-this-tier, principles, facts, raw source, quota protection, own key, error states), plus an **Ethical analysis**: affected parties and five harm categories from a rule table (project heuristic, each with its rationale and triggering facts), and pointers to Tabs 2, 3 and 4 | `analysis/harms.py` |
| 2 · Dataset Bias | Experiment 2 — Detecting Dataset Bias in AI System | CSV upload (50 MB cap; sampled to 50,000 rows) or a bundled demo; representation and imbalance ratio, optional reference shares, intersectional counts with small-cell flags, missingness by group, label base rates, rule-generated findings; the Art. 10 note when the loaded system is High-Risk | `analysis/data_bias.py` |
| 3 · Synthetic Media | Experiment 3 — Deepfake Vulnerability Assessment and Ethical Analysis | Capabilities with evidence; Art. 50(2) and 50(4) determinations (exceptions listed, not modelled); misuse-vulnerability matrix with its scoring table; rule-generated ethics text; three example repos | `analysis/synthetic_media.py` |
| 4 · Proxy Audit | Experiment 4 — Auditing the "Cost-as-a-Proxy" Resource Bias | A: target-label proxy check (cost, arrests, engagement, past decisions → what the proxy hides + reference case). B: association ranking (Cramér's V / correlation ratio), reconstruction test (cross-validated AUC + permutation importance), and the featured synthetic cost-vs-need selection demo | `analysis/proxy.py` |
| 5 · Fairness & Explainability | Experiment 5 — Implementing AI Fairness and Explainability Dashboard | A: per-group selection rate, TPR, FPR, precision, confusion matrices; demographic parity, equal opportunity and equalized odds differences; disparate-impact ratio vs the four-fifths rule (fairlearn). B: full rule trace (`classify_with_trace`) and a what-if explorer with the "disclosed human oversight and transparency" preset | `analysis/fairness.py`, `analysis/whatif.py`, `rules.classify_with_trace` |
| 6 · Impact Assessment | Experiment 6 — Operationalizing UNESCO & IEEE Frameworks via Algorithmic Impact Assessments | UNESCO/IEEE flags; the six Art. 27(1) elements filled only from facts (else "Not determinable from documentation"); a project-defined impact level I–IV with its scoring table; rule-driven actions with citations; Markdown and PDF downloads | `analysis/impact_assessment.py` |
| 7 · Robustness & Autonomy | Experiment 7 — Autonomous Target Selection and System Degradation Auditing | A: Rule 0 scope, meaningful-human-control note, decision autonomy, Art. 14/15 documentation checks. B: precomputed degradation study of ActAudit (stability matrix, per-field flip rates, injection resistance, findings); unrecorded runs shown as such | `analysis/autonomy.py`, `analysis/robustness.py`, `scripts/robustness_study.py` |
| 8 · Case Library | Experiment 8 — Case Study on AI Ethics and Regulations | Seven documented incidents (COMPAS, Amazon recruiting, Obermeyer care algorithm, Clearview AI, Dutch childcare benefits, Arup deepfake call, HireVue), each with sources, unverified notes, ActAudit's tier on a neutral description, and a rule-generated "Would the AI Act have caught this?"; load any case into the other tabs | `analysis/case_library.py`, `data/cases/` |

Cross-cutting changes:
- **Schema v2** (`SCHEMA_VERSION = 2`): ten new fact fields (target variable and type, synthetic media, impersonation, output marking, consent safeguards, military/defence use, robustness testing, fail-safe). Older fixtures still load, with the new fields at their defaults and an "older schema" badge.
- **Rule 0 / Out of scope**: exclusively military, defence or national-security use → Art. 2(3); new neutral-grey verdict banner (WCAG: light 7.56:1, dark 9.37:1).
- **Shared state**: one loaded system (`current_analysis`) and one loaded dataset shared by every tab; "Currently loaded" line on every tab.
- **Structure**: `app.py` is a thin entry point; `ui/` (one module per tab + shared components), `analysis/` (pure modules; every threshold in `analysis/config.py`), all reached from the UI only through `pipeline.py`.

## How to run

```bash
pip install -r requirements-dev.txt     # Python 3.12
cp .env.example .env                    # add GEMINI_API_KEY for live audits
streamlit run app.py
pytest                                  # offline; the ACTAUDIT_LIVE=1 test is skipped
python scripts/record_all.py            # finish the pending recordings (uses the .env key only)
python scripts/make_demo_datasets.py    # rebuild data/*.csv byte-for-byte
python scripts/screenshot_tabs.py       # dev only: needs `pip install playwright && playwright install chromium`
```

The quick-picks, Case Library, demo datasets and every data tab work with no key and no network.

## Test results

**357 passed, 1 skipped** (the opt-in live test), offline, in about 12 s. The same result in a fresh Python 3.12 venv in a copy of the repository with no `.venv`, no `.env` and no `GEMINI_API_KEY`.

| Test file | Tests | Covers |
|---|---|---|
| test_app.py | 60 | the original app scenarios, all still passing (locators updated for the tabs), plus the Out-of-scope banner and older-schema badge |
| test_tabs.py | 15 | verbatim tab labels and captions (code, blueprint and rendered), lazy tabs, "Currently loaded", Tab 1 ethical analysis |
| test_rules.py | 29 | + Rule 0 precedence and justification, clause/condition agreement on all 5,760 combinations of the tested values, the trace |
| test_schema.py | 23 | + schema v2, no judgment fields, v1 upgrade |
| test_extractor.py | 33 | + v2 response schema, prompt definitions, scoped confidence rule, `model=` override |
| test_pipeline.py | 10 | + fixture compatibility, example status |
| test_record_fixtures.py | 6 | pacing, skip-existing, quota stop, re-record, tier-change candidate |
| test_harms.py | 11 | harm categories, affected parties, tab pointers |
| test_data_bias.py | 11 | hand-computed representation, reference, intersection, missingness, base rates; load caps and friendly errors |
| test_proxy.py | 15 | hand-computed Cramér's V (1/3) and correlation ratio (√(13.5/17.5)); reconstruction near chance on noise and ≈1 on a leak; cost demo; proxy table |
| test_fairness.py | 5 | a 10-row example computed by hand and cross-checked with fairlearn; undefined rates |
| test_whatif.py | 5 | disclosure preset, military edit, evidence handling |
| test_synthetic_media.py | 10 | Art. 50 per capability combination, scoring table, ethics text |
| test_impact_assessment.py | 13 | Art. 27 elements, impact levels by hand, actions, citation flags, Markdown escaping, PDF |
| test_autonomy.py | 3 | scope, Art. 14/15 checks by tier |
| test_case_library.py | 17 | real data against the schema, malformed variants, verdict line by tier, timing, capability notes |
| test_robustness.py | 14 | perturbations; the study script with a model-aware fake client (resume, n/a, quota retirement, malformed); analysis; contrast; Tab 7B |
| test_data_tabs.py, test_analysis_tabs.py, test_datasets.py | 21 | AppTests for Tabs 2–8, shared column choices across tabs, hostile names rendering as text, demo datasets |
| test_ui_invariants.py | 4 | UI imports only through `pipeline.py`; raw HTML only in `ui/components.py`; `md_escape`; no hard-coded fractional thresholds in `analysis/` |
| test_github_fetch.py, test_principles.py | 53 | unchanged from `main` (principles now load fixtures through the compatibility loader) |

## Screenshot index

All in `docs/screenshots/experiment-tabs/`, 1440 px wide, full page, captured by `scripts/screenshot_tabs.py` from the running app with no API key. "Loaded" = the face_recognition quick-pick plus the UCI Adult demo (Tab 2) or the cost-as-a-proxy demo (Tabs 4–6, reconstruction test run in Tab 4, the what-if preset applied in Tab 5). I reviewed every image; fixes made from the review are in the decision log (chart heights, x-axis ranges, heatmap labels, the Tab 6 level metric and wrapping actions table, the duplicate autonomy line in Tab 7, the "hand-built" badge).

| Tab | Nothing loaded | Loaded |
|---|---|---|
| 1 · System Audit | [light](screenshots/experiment-tabs/tab1_empty_light.png) · [dark](screenshots/experiment-tabs/tab1_empty_dark.png) | [light](screenshots/experiment-tabs/tab1_loaded_light.png) · [dark](screenshots/experiment-tabs/tab1_loaded_dark.png) |
| 2 · Dataset Bias | [light](screenshots/experiment-tabs/tab2_empty_light.png) · [dark](screenshots/experiment-tabs/tab2_empty_dark.png) | [light](screenshots/experiment-tabs/tab2_loaded_light.png) · [dark](screenshots/experiment-tabs/tab2_loaded_dark.png) |
| 3 · Synthetic Media | [light](screenshots/experiment-tabs/tab3_empty_light.png) · [dark](screenshots/experiment-tabs/tab3_empty_dark.png) | [light](screenshots/experiment-tabs/tab3_loaded_light.png) · [dark](screenshots/experiment-tabs/tab3_loaded_dark.png) |
| 4 · Proxy Audit | [light](screenshots/experiment-tabs/tab4_empty_light.png) · [dark](screenshots/experiment-tabs/tab4_empty_dark.png) | [light](screenshots/experiment-tabs/tab4_loaded_light.png) · [dark](screenshots/experiment-tabs/tab4_loaded_dark.png) |
| 5 · Fairness & Explainability | [light](screenshots/experiment-tabs/tab5_empty_light.png) · [dark](screenshots/experiment-tabs/tab5_empty_dark.png) | [light](screenshots/experiment-tabs/tab5_loaded_light.png) · [dark](screenshots/experiment-tabs/tab5_loaded_dark.png) |
| 6 · Impact Assessment | [light](screenshots/experiment-tabs/tab6_empty_light.png) · [dark](screenshots/experiment-tabs/tab6_empty_dark.png) | [light](screenshots/experiment-tabs/tab6_loaded_light.png) · [dark](screenshots/experiment-tabs/tab6_loaded_dark.png) |
| 7 · Robustness & Autonomy | [light](screenshots/experiment-tabs/tab7_empty_light.png) · [dark](screenshots/experiment-tabs/tab7_empty_dark.png) | [light](screenshots/experiment-tabs/tab7_loaded_light.png) · [dark](screenshots/experiment-tabs/tab7_loaded_dark.png) |
| 8 · Case Library | [light](screenshots/experiment-tabs/tab8_empty_light.png) · [dark](screenshots/experiment-tabs/tab8_empty_dark.png) | [light](screenshots/experiment-tabs/tab8_loaded_light.png) · [dark](screenshots/experiment-tabs/tab8_loaded_dark.png) |
| Out-of-scope verdict | — | [light](screenshots/experiment-tabs/out_of_scope_verdict_light.png) · [dark](screenshots/experiment-tabs/out_of_scope_verdict_dark.png) |

The Out-of-scope screenshots use `scripts/screenshot_harness.py`, which preloads **hand-built facts** for the fictional military sample because that quick-pick isn't recorded yet. The page says so (source label "HAND-BUILT facts, screenshot only" and a "Hand-built facts (not an extraction)" badge). Once the sample is recorded, the harness uses the real fixture instead. Tab 8's "loaded" screenshots equal the empty ones apart from the loaded line, because no case analysis is recorded yet.

## Decision log

Recorded in blueprint §14 ("Experiment tabs: autonomous decisions"), copied here:

- New backend modules live in an `analysis/` package (not the repo root); all thresholds in `analysis/config.py`.
- `military_defence_use` means *exclusively* military, defence or national-security use, mirroring Art. 2(3); dual-use systems extract as `false`.
- The "several defaults → low confidence" prompt instruction is scoped to the v1 core fields, so the new capability fields (usually `false`) don't push every README to low confidence.
- A 7th quick-pick, a fictional military sample text, demonstrates the Out-of-scope tier.
- A re-recorded quick-pick whose tier or rule changes keeps its v1 fixture; the new output is saved under `tests/fixtures/_candidates/` and reported. The six non-quick-pick fixtures stay on v1 unless quota remains at the end.
- Misuse matrix (Tab 3): the "Consent / identity checks" and "Usage policy" columns both read the single extracted fact `consent_safeguards_mentioned`, stated in the UI.
- PDF report uses fpdf2 core fonts with latin-1 transliteration (no bundled font file).
- Case Library data is validated in Python (`analysis/case_library.py`); a JSON Schema file is kept alongside as documentation, so no `jsonschema` dependency.
- Robustness study: non-model perturbations run on one fixed reference model; perturbations that leave the text unchanged are recorded as "n/a" with no API call.
- The Rule 0 row enters the §6.2 table in Phase 10 (not Phase 9) because `tests/test_rules.py` mirrors that table.
- Re-recording an existing GitHub fixture reuses its stored README text rather than re-fetching, so any change in the extraction reflects the schema/prompt change, not an edited README.
- Each rule's condition is also stored as clauses (field + allowed values) for `classify_with_trace()`; a test checks clauses and condition agree on every combination of the tested values, so `classify()` itself stays untouched.
- Two `tests/test_app.py` assertions that depended on incidental fixture properties were made fixture-independent after re-recording (tiers unchanged): the "primary model shows no fallback caption" test now uses a fake live call, and the quick-pick test allows the low-confidence warning (a §9 finding; `psf/requests` now extracts with low confidence) while still forbidding every other warning.
- `ABSENT_DEFAULTS` moved from `extractor.py` to `schema.py` (re-exported by the extractor) so the fixture loader and the extractor share one definition.
- The recording scripts retry overload (503/504) with backoff but stop immediately on quota (429 from every model), printing the resume command.
- The sidebar starts collapsed (`initial_sidebar_state="collapsed"`) so all eight tab labels fit at 1440 px; it still holds the own-key field and usage counter, one click away.
- Lazy tabs are tested by seeding `session_state["main_tabs"]` in AppTest (verified to select the tab), so no separate per-tab test harness was needed.
- Evidence snippets and user-derived labels shown as Markdown are passed through `md_escape` (rendered literally); the model name and fixed rule text are not.
- Tab 1's Ethical analysis section sits below the result tabs (not as a fifth result tab), so Principles stays the default result tab and the verdict layout is unchanged; categories with no finding are listed on one line.
- fairlearn installed cleanly with pandas 3, so group metrics use `fairlearn.metrics.MetricFrame`; undefined rates (e.g. TPR for a group with no actual positives, which sklearn reports as 0) are set to NaN and ignored in the differences. Tests check hand-computed values and cross-check against fairlearn's own difference functions.
- Reconstruction test "top features" use permutation importance (AUC drop when one original column is shuffled, 5 repeats, fixed seed), not summed one-hot coefficients, which favoured many-category columns (e.g. `native_country`). It uses every non-protected column, including label and prediction columns; other protected attributes are excluded.
- Association uses the correlation ratio for numeric columns with more than 10 distinct values and Cramér's V otherwise; categorical columns with more than 50 values (IDs) are skipped (`MAX_CATEGORIES`). Cohen's effect-size conventions for V (0.1 / 0.3) are applied to the correlation ratio as a stated simplification.
- The positive label defaults to the label's least frequent value (e.g. `>50K`, `Yes`); the user can change it. Reference population shares are normalised to 100% over the groups entered.
- The Adult prediction model excludes `sex` and `race`, so its disparities arise through proxies (Tab 4 finds `relationship`), which is the point of the demo. `fnlwgt` (a census sampling weight) is dropped.
- Charts use `alt.Step` band heights: in Streamlit 1.64, `st.altair_chart` sizes to the chart's content and ignores a fixed `properties(height=...)` (verified in a browser probe). Status metrics hide the delta arrow, since the delta text is a status, not a change.
- In AppTests, the tabs widget's state isn't resent after a click (a browser does resend it), so tests re-select the tab before each interaction.
- The non-generative Tab 3 example is lukemelas/EfficientNet-PyTorch instead of huggingface/pytorch-image-models: the latter's README opens with a long changelog and its introduction starts at character 11,815, beyond the 8,000-character window the model sees.
- Art. 50 determinations use three statuses. Art. 50(2) "Applies" whenever synthetic content generation is extracted. Art. 50(4) first subparagraph "Applies" for image/audio/video generation by an impersonation-capable system (its output can be a deep fake per Art. 3(60)), "May apply" for image/audio/video generation without it. Art. 50(4) second subparagraph "May apply" for text generation. The exceptions are listed, not modelled.
- Misuse matrix scoring (project heuristic): capability rows × number of distinct safeguard facts documented (0 / 1 / 2) → High/Medium/Low per the table shown in the UI; overall = highest row.
- Art. 27(1)(b) (period and frequency of use) has no extraction field, so it is always "Not determinable from documentation", except that real-time use in public spaces is reported when extracted.
- Impact level (project-defined, inspired by Canada's AIA): additive points for domain, data, affected population, autonomy and capabilities, minus 1 per documented mitigation (oversight, transparency, robustness testing, fail-safe); bands I 0–2, II 3–5, III 6–8, IV 9+; a Prohibited tier is forced to IV.
- Recommended actions come from a fixed rule table; each cites a verified provision (EU AI Act or GDPR Art. 35, verified via CELLAR) or is labelled a project heuristic.
- The PDF report uses fpdf2 core fonts: common symbols are transliterated (→, —, quotes), other non-latin-1 characters become "?". Text is written with plain cells (no markup mode), and the Markdown report escapes every value.
- Tab 7A's note on meaningful human control is labelled a context note, not a legal citation.
- Case Library: all seven candidate incidents could be sourced, so all seven are included. Each case's "system_description" is a neutral reconstruction of the system (not the outcome) from the cited sources; details that go beyond them are listed as unverified. Sources that block automated access (Reuters, science.org, wicourts.gov, EPIC) were replaced or supplemented by reachable reputable ones (the Guardian's copy of the Reuters story, PBS, Harvard Law Review, Fortune/SHRM), and the blocked originals are noted as not fetched.
- "Would the AI Act have caught this?" is generated from ActAudit's tier (Prohibited → yes; High-Risk → partly, via Art. 9/10/14/15; Limited/Minimal → probably not; Out of scope → no), plus fact-based notes (Art. 50 for synthetic media; ActAudit's rules don't model Art. 5(1)(e) untargeted facial scraping for biometric systems) and a non-retroactivity line (entry into force 1 August 2024, the 20th day after OJ publication on 12 July 2024; most obligations from 2 August 2026; cases dated before August 2024 "predate it").
- Case text is rendered through `md_escape`, because amounts like "HK$200 million … US$25.6 million" would otherwise be rendered as LaTeX.
- Robustness subjects: classroom_emotion_tracker (Prohibited), face_recognition, pyresparser (High-Risk), requests (Limited-Risk), tab_grouping_extension (Minimal-Risk); the text is each fixture's stored README / sample text, so the study doesn't depend on GitHub.
- "Remove the intended-use section": the first Markdown section (below a top-level title) whose heading matches usage / use case / intended / purpose / features / about / overview / introduction / what is / description, else the first section; texts without Markdown sections are "n/a". Injections are inserted as their own paragraph after the first paragraph, so they stay inside the 8,000-character window.
- Baseline = the reference model (default `gemini-3.8-flash`) on the unmodified text; the other model columns run the same text on each model with no fallback (the new `model=` override); text perturbations use the reference model. Compared fields exclude free text (system_purpose, target_variable) and evidence snippets.
- Injection "resisted" means the same tier and no compared fact changed; "facts changed, tier held" and "tier changed" are reported separately, as is the number of true booleans turned false.
- A model that returns 429 is retired for the rest of the run and its runs stay pending (rerun later); brief overloads (503/504) are retried; malformed output after the extractor's own retry is recorded as a result ("malformed output"), since that is a legitimate robustness outcome.

## Citations and verification

All EU AI Act citations were checked against the Official Journal text of Regulation (EU) 2024/1689, retrieved from the EU Publications Office's CELLAR repository (`publications.europa.eu/resource/celex/32024R1689`; the same document EUR-Lex serves, whose site blocks automated access). GDPR citations were checked the same way (`celex/32016R0679`).

| Citation | Used for | Status |
|---|---|---|
| AI Act Art. 2(3), second subparagraph | Rule 0, Tab 7A | verified |
| Art. 3(60) (deep fake) | Tab 3 | verified |
| Art. 5(1)(e) (untargeted facial scraping) | Tab 8 note | verified |
| Art. 9(1) | Tab 6 action | verified |
| Art. 10(2)(f)–(g), 10(3) | Tab 1 pointer, Tab 2 note, Tab 6 actions | verified |
| Art. 14(1), 14(4)(d)–(e) | Tab 6 action, Tab 7A | verified |
| Art. 15(1), (3), (4), (5) | Tab 6 action, Tab 7A | verified |
| Art. 27(1)(a)–(f) | Tab 6 structure and applicability | verified |
| Art. 50(1), 50(2), 50(4) | Tab 3, Tab 6 actions | verified |
| Art. 113; OJ publication 12 July 2024 → entry into force 1 August 2024 | Tab 3 note, Tab 8 timing line | verified |
| GDPR Art. 35(1), 35(3)(b)–(c) | Tab 6 actions | verified |
| 29 CFR 1607.4(D) (four-fifths rule) | Tab 5 threshold source | from general knowledge of the US Uniform Guidelines; not fetched |
| Cohen (1988) effect-size conventions | Tab 4 thresholds | from general knowledge; the thresholds are labelled project choices that follow the convention |
| Obermeyer et al. (2019), Science 366(6464):447–453 | Tab 4 reference, cost demo | DOI confirmed; the paper page blocks automated access; findings cross-checked via the NY DFS letter and PBS |
| Angwin et al. (2016) ProPublica; Lum & Isaac (2016) Significance 13(5):14–19 | Tab 4 reference | verified (ProPublica fetched; Lum & Isaac bibliographic details confirmed) |
| Milli et al. (2025) PNAS Nexus 4(3), doi 10.1093/pnasnexus/pgaf062 | Tab 4 reference | verified |
| Dastin (2018) Reuters | Tab 4 reference, Tab 8 | content confirmed via the Guardian's copy; the Reuters URL itself couldn't be fetched |
| UNESCO Recommendation (2021) paragraph numbers | principle flags (unchanged from `main`) | **still unverified**, as before this branch |

**No citation in the code carries `citation_verified=False`.** Every rule, obligation and action is either a verified provision or labelled a project heuristic.

**Case facts marked unverified** (each is shown in the app with an "unverified" badge; nothing below is presented as confirmed):
- COMPAS: the vendor's (Northpointe/Equivant) dispute of ProPublica's analysis.
- Amazon: the Reuters URL itself (content via the Guardian); whether recruiters relied on the rankings; that recruiters could see the recommendations (reconstruction).
- Obermeyer: the paper's own text (via the NY letter and PBS); the vendor attribution to Optum's Impact Pro comes from the NY letter.
- Clearview AI: the €20 million fines in Italy, Greece and France (secondary reporting only).
- Dutch childcare benefits: that parents weren't told how the system worked (summarises Amnesty's findings).
- Arup: the exact tools used; the system description is a reconstruction from the reported facts.
- HireVue: EPIC's FTC complaint was not read directly (EPIC blocks automated access); what candidates were told (reconstruction).

## Recording status

| Priority | Recorded | Pending |
|---|---|---|
| (1) quick-picks on schema v2 | face_recognition, pyresparser, requests, classroom_emotion_tracker, tab_grouping_extension — all with their approved tier and rule unchanged | arnoweng/CheXNet, the fictional military sample (`text__military_target_recognition`) |
| (2) Tab 3 examples | — | CorentinJ/Real-Time-Voice-Cloning, deepfakes/faceswap, lukemelas/EfficientNet-PyTorch |
| (3) Case Library | — | the 7 `text__case_*` descriptions |
| (4) robustness study | — | 38 runs over 5 subjects (7 more are n/a and need no call) |

**To finish:** `python scripts/record_all.py` — resumable, paced, stops cleanly on quota and prints the same command. Budget: 12 fixture calls plus 38 study calls, 23 of them on `gemini-3.8-flash` (about 20 requests a day on the free tier), so the study takes two quota days; rerun the command once a day until it exits with code 0. Until then the app shows each missing item as "not recorded yet" (disabled buttons, Tab 8 notices, Tab 7B message). Two re-recording outcomes to review: `psf/requests` now extracts with `extraction_confidence: low` (tier unchanged), and no re-recording changed a tier, so `tests/fixtures/_candidates/` is empty. The six non-quick-pick fixtures (creditR, rasa, TriageAI, Insurance-Premium, face_classification, the-algorithm) remain on schema v1 by design; `python scripts/record_fixtures.py --set legacy --rerecord-older-schema` would upgrade them.

## Deployment readiness

- **Would deploy cleanly on Streamlit Community Cloud as it stands.** Verified by installing `requirements.txt` in a fresh Python 3.12 venv (20 s), with `pip check` clean. All 11 pinned packages are available as binary wheels (`pip download --only-binary=:all:`), so no system packages are needed. The app booted (health check 200) with only `GEMINI_API_KEY` in the environment, and every tab rendered with no exception.
- **New pinned dependencies:** pandas 3.0.6, numpy 2.5.3, altair 6.3.0, scikit-learn 1.9.1, scipy 1.18.1, fairlearn 0.14.0, fpdf2 2.8.9 (pandas/numpy/altair were already installed with Streamlit; now pinned explicitly).
- **No new secrets or settings.** `GEMINI_API_KEY` in Secrets is still the only requirement. The upload cap is set per widget (`max_upload_size=50`), so no `config.toml` change is needed.
- **No local-only paths** in shipped code (checked by grep). Bundled data is 0.8 MB of CSV plus the case JSON.
- **Behaviour change to be aware of:** the sidebar (own key, usage counter) now starts collapsed so that all eight tab labels fit.
- Playwright stays a dev-only tool, used only by `scripts/screenshot_tabs.py` and not in either requirements file.

## Updates needed in course materials if merged

`docs/REPORT.md` and `docs/screenshots/*.png` were not edited on this branch. If the branch is merged, these places would no longer match the app:

| Where | What changes | Suggested wording |
|---|---|---|
| REPORT §2, 3rd bullet ("thirteen facts") | the schema now has 23 facts | "…a small structured object: twenty-three facts (thirteen from the original design plus ten added for the experiment tabs), each constrained to an enumerated set of values…" |
| REPORT §2, "The user interface (`app.py`) can only reach the backend through `pipeline.py`" | the UI moved into `ui/` | "The user interface (`app.py` and the `ui/` package) can only reach the backend through `pipeline.py`; a test fails if any UI module imports anything else." |
| REPORT §3.3 schema table | ten new fields | add: "`target_variable` (free text) and `target_type` (cost_or_spending, arrests_or_police_contact, engagement_or_clicks, past_human_decisions, direct_outcome, other, unknown); `generates_synthetic_media`, `impersonation_capable`, `output_marking_mentioned`, `consent_safeguards_mentioned`, `military_defence_use`, `robustness_testing_mentioned`, `failsafe_mentioned` (true/false); `synthetic_media_types` (list of image, audio, video, text)." |
| REPORT §3.4 rule table | Rule 0 | add the row "0 · `military_defence_use` (exclusively military, defence or national-security use) · Out of scope · Art. 2(3)" and the bullet "**Rule 0:** Art. 2(3) excludes systems used exclusively for military, defence or national-security purposes, so the Act doesn't apply; the principle flags are still shown." |
| REPORT §3.6 | test count and files | "**Test suite:** 358 tests. 357 run offline with no API key…" and add a row per new test file (see the table above). |
| REPORT §3.7 Dashboard | single page → eight tabs; six → seven example buttons | "The app has eight tabs, one per course experiment (see the README table). Tab 1 is the audit described here, plus an ethical analysis of affected parties and harms…" and "seven example buttons". |
| REPORT §4 results table | models changed on re-recording (tiers and domains didn't) | pyresparser: 3.6-flash (was 3.8); face_recognition: 3.5-flash (was 3.6); requests: 3.5-flash, confidence **low** (was 3.6, high); tab organiser: 3.6-flash (was 3.7). Add to Observations: "requests is now also a low-confidence result after re-recording on schema v2." |
| REPORT §5 documentation-opacity counts | unchanged | still 2 of 12 mention human oversight and 0 of 12 mention AI disclosure; no change needed |
| REPORT §6 Limitations | new heuristics | add: "The harm mapping, misuse matrix, impact level and statistical thresholds are project choices, labelled as such. Case Library tiers are ActAudit's reading of a neutral description, not legal findings; the Act is not retroactive. Deployer duties under Art. 50(4) depend on use, which a README rarely shows." Remove "doesn't … list the obligations that follow from a tier" (Tabs 6 and 7 now list them). |
| REPORT §7 Citation status | new provisions | extend the first row to "Art. 2(3); 3(60); 5(1)(c), (e), (f), (h); 6(1)–(3); 9(1); 10(2)–(3); 14; 15; 27(1); 50(1), (2), (4); 113; Annex III points 1 and 5", and add "GDPR Art. 35 — verified against the Official Journal text". |
| REPORT §8 Future work | two items are now done | remove "A 'sensitivity' view…" (now the Tab 5 what-if explorer); PDF export (Tab 6) was a stretch goal; keep batch comparison, Art. 6(3) and reading code. |
| REPORT Appendix A | new screenshots | add a selection from `docs/screenshots/experiment-tabs/` (e.g. tab4_loaded_light, tab5_loaded_dark, tab6_loaded_light, out_of_scope_verdict_light), noting the Out-of-scope image uses hand-built facts until recorded. |
| README "Screenshots" | still shows the Phase 8 images | optional: replace with one image per tab from `docs/screenshots/experiment-tabs/`. The README was otherwise updated on this branch. |

## Known limitations

- Recordings are incomplete (see above); until then Tab 3's examples, the Case Library tiers, Tab 4A's case examples and Tab 7B are "not recorded yet".
- The ten new facts come from the same LLM extraction and can be wrong; older fallback models answered several fixtures. Every fact is shown with its evidence.
- Art. 50 exceptions, Art. 27's deployer scope and Art. 2(3)'s third subparagraph are stated but not modelled.
- The impact level, misuse matrix, harm mapping and most statistical thresholds are project-defined; the four-fifths rule is the only external statistical standard.
- Case descriptions are reconstructions written for ActAudit, not the systems' own documentation.
- The robustness study is small (5 subjects, 1 run per cell); it measures instability, it can't estimate rates precisely.
- The PDF uses core fonts, so characters outside latin-1 become "?".
- Uploaded CSVs are sampled to 50,000 rows; very wide files are slower in the reconstruction test (capped at 20,000 rows, behind a button).

## What I'd change with more time

- Finish the recordings, then commit the robustness findings and review the Case Library tiers against the "Would the Act have caught this?" lines.
- Repeat each robustness cell several times to separate model randomness from real sensitivity, and add paraphrase and translation perturbations.
- Model the Art. 50 exceptions and Art. 6(3) as explicit, testable rules with extracted facts behind them.
- Let the Case Library use each vendor's own public documentation where it exists, alongside the neutral description.
- Add intersectional fairness metrics (two attributes at once) to Tab 5, and bootstrap confidence intervals to every rate.
- Bundle a Unicode font for the PDF and add the charts to the downloadable report.

## Branch integrity

- `git rev-parse main` before work: `4490dc6e11f74449cb9c7628a9ae98ebb30191f6`; after the final push: see the final command output in the hand-off message (unchanged).
- Nothing was merged, rebased, force-pushed or committed to `main`. Every phase commit passed the full suite and a secret check (staged diff scanned for key patterns; `.env` untracked).
