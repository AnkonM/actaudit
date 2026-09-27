# ActAudit
### Automated Risk Classification of AI Systems Against EU AI Act, UNESCO & IEEE Ethical Frameworks

**Course:** Ethics in AI & DS — Mini Project
**Type:** LLM-assisted compliance auditing tool
**Status:** Pre-development / Blueprint v2
**Purpose of this document:** This is the single, persistent source of truth for the project. It is written to be handed to a coding agent (e.g. Claude Code) as the *only* context needed to build, extend, or resume work on ActAudit without the original chat history. Every design decision, schema, rule, and rationale that matters for correct implementation should live here. When this document and the agent's memory of a prior session conflict, this document wins — update it whenever a real decision changes.

---

## 1. Problem Statement

Assessing whether an AI system is "high-risk" under the EU AI Act, or whether it aligns with UNESCO's Recommendation on the Ethics of AI (2021) and IEEE's Ethically Aligned Design principles, currently requires a human expert to manually read documentation and map it against dense regulatory text. This is slow, inconsistent, not reproducible, and inaccessible to smaller teams/startups who most need early compliance guidance — the people least likely to have in-house legal/compliance staff.

**ActAudit** automates the *information extraction* step (using an LLM to read unstructured documentation) while keeping the actual *risk classification* fully deterministic and auditable (via a hand-built rule engine grounded in real EU AI Act provisions). This split — LLM for reading, rules for judging — is the ethical and technical core of the project.

### 1.1 Why this split matters (do not collapse it)
- An LLM asked "what risk tier is this?" gives an unreliable, unauditable, hallucination-prone answer that changes between runs.
- A rule engine given raw unstructured text can't parse it at all.
- Splitting the two — LLM extracts *facts*, rules classify *tiers* — gives you a system where the risky/subjective part (reading messy text) is bounded to producing a small structured object, and the part that actually matters for the person's compliance decision (the tier) is 100% deterministic, testable, and citable.
- **This split must be preserved in every implementation decision.** If a future feature is tempted to ask the LLM "is this high risk?" directly, that is a regression — reject it. The LLM's output schema (Section 5) should never contain a risk tier or judgment field, only observable facts.

## 2. Core Idea / One-Line Pitch

> Paste a GitHub repo URL or a model card / README text → ActAudit extracts structured risk-relevant facts using an LLM → a deterministic rule engine maps those facts to an EU AI Act risk tier + UNESCO/IEEE principle flags → a dashboard displays the classification with a full, inspectable reasoning trace.

No questionnaire. The input is always a real-world artifact (repo or pasted documentation text), never a form the user fills in about their own system — this is intentional (see Section 3.1).

## 3. Inputs

### 3.1 Why real artifacts, not a questionnaire
A questionnaire asks the user to self-report facts about their own system, which (a) is trivially gameable, (b) doesn't scale to auditing *other people's* systems, and (c) feels like a form-filler rather than an AI tool. Feeding it a real README/model card means the tool is actually reading and reasoning about existing documentation the way a human auditor would.

### 3.2 Accepted input types (v1 scope)
- **Option A — GitHub repo URL:** tool fetches the README from the repo's default branch via GitHub's raw content API. No auth/token required for public repos.
- **Option B — Pasted text:** any unstructured text — a Hugging Face model card, a product description, a privacy policy excerpt, an internal spec.

### 3.3 Explicitly out of scope for v1 (do not build unless asked)
- Private/authenticated GitHub repos (would require OAuth — adds complexity for no demo value)
- Multi-file repo scanning / static code analysis (this is Section 10 "GitHub Repo Scanner" territory from the original brainstorm — a good v2 idea, not v1)
- Non-English documentation handling
- File uploads (PDF spec sheets etc.) — text paste covers this well enough for a demo

## 4. End-to-End Pipeline / Workflow

```
1. Input (GitHub URL or pasted text)
        │
        ▼
2. Fetch & clean text
   - GitHub path: try README.md / README / readme.md on main, then master branch,
     via https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}
   - Paste path: use text as-is, strip excess whitespace
   - Guardrail: truncate to a safe max length before sending to the LLM (see 6.4 —
     truncation happens in extractor.py, not here)
   - Accepted v1 limitation: repos whose default branch isn't main or master surface
     ReadmeNotFoundError. This is not a bug — the error message already tells the user
     to paste the text instead. Do not add default-branch detection.
   - Accepted v1 simplification: HTML markup inside a fetched README (e.g. a README
     that opens with raw HTML tags) is NOT stripped or cleaned before being sent to the
     LLM. Deliberate: the extraction model handles HTML-embedded markdown adequately,
     and stripping tags risks losing structurally informative content (badges, headers).
        │
        ▼
3. LLM Extraction (structured JSON output, schema in Section 5)
   - Single call, JSON-mode / response-schema constrained
   - On malformed JSON: retry once with a stricter "return ONLY valid JSON" reminder
   - On repeated failure: surface a clear error to the user, do NOT silently guess
        │
        ▼
4. Rule Engine (deterministic, zero LLM involvement, Section 6)
   - Ordered rule list, first match wins
   - Produces: risk_tier, justification text, cited provision, which fields fired it
   - Also produces: UNESCO principle flags, IEEE EAD principle flags (Section 7)
        │
        ▼
5. Dashboard Output (Section 8)
   - Risk tier badge (color-coded)
   - Extracted facts table (full transparency into what the LLM saw/inferred)
   - "Why this tier" panel — the exact rule + provision that fired
   - Principle-by-principle breakdown (UNESCO / IEEE)
   - Optional PDF export (stretch goal)
```

## 5. Extraction Schema (LLM output contract)

This is a **contract**, not a suggestion — the rule engine in Section 6 depends on these exact field names and enum values. If the schema changes, the rule engine must be updated in the same commit.

| Field | Type | Allowed values | Description |
|---|---|---|---|
| `system_purpose` | string | free text, ≤200 chars | One-sentence summary of what the system does |
| `deployment_domain` | enum | `hiring`, `essential_services`, `law_enforcement`, `biometric_id`, `education`, `content_moderation`, `critical_infrastructure`, `migration_asylum_border`, `general_consumer`, `other` | Primary domain the system operates in. `essential_services` = access to essential private/public services and benefits per Annex III point 5: creditworthiness/credit scoring, public-benefit eligibility (incl. healthcare services), life/health insurance risk pricing, emergency call triage/dispatch. Clinical/diagnostic tools with no such access-gating role map to `other` (see 6.2 note on healthcare). Replaces the earlier `credit_lending` and `healthcare` values. |
| `data_sensitivity` | enum | `none`, `personal`, `sensitive` | `sensitive` = health, biometric, criminal, political/religious/union-affiliation data |
| `biometric_use` | boolean | — | Processes biometric data for identification or categorization |
| `decision_autonomy` | enum | `human_in_loop`, `human_on_loop`, `fully_autonomous` | `human_in_loop` = human approves each decision; `human_on_loop` = human can override/monitor but doesn't approve each one; `fully_autonomous` = no human review path mentioned |
| `affected_population` | enum | `general_public`, `vulnerable_groups` | `vulnerable_groups` = children, job seekers, patients, asylum seekers, elderly, persons with disabilities |
| `emotion_inference` | boolean | — | Infers emotion/intent from biometric or behavioral signals |
| `social_scoring` | boolean | — | Scores/ranks individuals for general trustworthiness or eligibility across unrelated contexts |
| `real_time_biometric_public` | boolean | — | Real-time biometric identification in publicly accessible spaces (a specifically named EU AI Act red line) |
| `human_oversight_mentioned` | boolean | — | Documentation explicitly mentions human review, override, or appeal mechanisms |
| `transparency_mentioned` | boolean | — | Documentation mentions disclosure to end users that they are interacting with an AI system |
| `extraction_confidence` | enum | `high`, `medium`, `low` | LLM's self-assessed confidence given how much relevant info the source text actually contained |
| `evidence_snippets` | object | `{field_name: "quoted or paraphrased snippet"}` | For each non-default field the LLM set, a short pointer to what in the text justified it — critical for the "why this tier" transparency panel and for user trust/debugging |

### 5.1 Extraction prompt design notes
- Instruct the model explicitly: *"You are extracting observable facts only. Do not assess risk, legality, or compliance. If information for a field is not present in the text, use the safest 'unknown' default for that field and lower extraction_confidence accordingly — do not guess."*
- Unknown/absent-signal defaults should bias toward the *lower-risk* enum value, not the higher-risk one, and this should be paired with `extraction_confidence: low` so the UI can visibly flag "this classification is based on incomplete documentation" — this is itself a finding worth surfacing (see Section 9's documentation-opacity point), not something to hide.
  - **Exact absent-signal defaults:** `deployment_domain: other`, `data_sensitivity: none`, `decision_autonomy: human_on_loop`, `affected_population: general_public`, every boolean `false`.
  - **Exception — `decision_autonomy` defaults to `human_on_loop`, not the lowest-risk `human_in_loop`.** `human_in_loop` is a positive claim (a human approves each decision) and is a condition of Rule 7 (Minimal-Risk). Defaulting to it let documentation *silence* earn a Minimal-Risk classification, contradicting Section 9's point that thin documentation is a finding, not a pass. Observed in Phase 3 live testing: all five READMEs came back `human_in_loop` with no supporting text. `human_in_loop` must now be justified by an evidence snippet.
  - **Evidence snippets for defaulted fields are dropped** by the extractor after parsing: a snippet is kept only when its field's value differs from the absent-signal default above (`system_purpose` and `extraction_confidence` have no default and keep theirs). Phase 3 live testing showed the model emitting placeholder snippets such as `"none"` for defaulted fields.
  - **Fixtures store the raw model response** alongside the parsed facts, so post-processing (e.g. snippet filtering) can be re-checked offline without new API calls.
- Require JSON-only output; use the SDK's structured output / response schema feature rather than trusting prompt instructions alone.
- **Healthcare routing instruction (include explicitly in the prompt):** clinical/diagnostic tools (disease detection, treatment recommendation, medical imaging analysis) → `deployment_domain: other`, since that is the Annex I/medical-device path this tool doesn't assess (see the healthcare note in Section 6.2). Healthcare-*access* tools (insurance pricing, benefits eligibility, triage/resource prioritization) → `essential_services`.
- **Biometric routing instruction (include explicitly in the prompt):** face recognition, face detection, or facial identification libraries/tools (e.g. face_recognition, dlib-based face matching, facial biometric matching) → `deployment_domain: biometric_id`, `biometric_use: true`, even if the README doesn't explicitly use the word "biometric". Added after Phase 3 live testing, where a fallback model (`gemini-3.5-flash`) routed ageitgey/face_recognition to `other`.
- **Definition of `other` (include explicitly in the prompt):** `other` = general-purpose libraries and developer tools with no specific application domain, research code, and anything else. A library or toolkit *built for a specific domain* (e.g. credit scoring, résumé screening, face recognition) takes that domain, not `other`. Added after Phase 3 live testing, where the earlier wording ("libraries, developer tools… → other") made ayhandis/creditR (a credit-scoring package) route to `other` on `gemini-3.6-flash`.
- **SDK call config:** the Gemini call (`google-genai`) must explicitly disable automatic function calling in its generation config — this call has no tools/functions to invoke, and leaving AFC on only produces a noisy SDK warning on every call.

## 6. Rule Engine (deterministic, auditable core)

### 6.1 Design principles
- Ordered list of rules, **first match wins** — this must be a simple, linear, human-readable list a grader can step through by hand. No weighted scoring, no ML, no fuzzy logic.
- Every rule carries: the condition, the resulting tier, a human-readable justification string, and a cited provision (even if approximate — see 6.3).
- A rule firing must be traceable back to specific extracted fields, so the "why this tier" panel can say e.g. *"Classified as High-Risk because deployment_domain=hiring → employment is a named Annex III high-risk area (see: Annex III + Art. 6(2))."*

### 6.2 v1 Rule Table (citations audited against Regulation (EU) 2024/1689, EUR-Lex)

| # | Condition | Tier | Cited provision | Verified? |
|---|---|---|---|---|
| 1 | `real_time_biometric_public == true and deployment_domain == law_enforcement` | **Prohibited** | Art. 5(1)(h) — real-time remote biometric identification in publicly accessible spaces "for the purposes of law enforcement" (narrow statutory exceptions exist, not modeled here) | Yes |
| 2 | `social_scoring == true` | **Prohibited** | Art. 5(1)(c) — social scoring. No "public authorities" restriction in the final text: any scoring based on social behaviour or personal characteristics that leads to detrimental treatment is covered | Yes |
| 3 | `emotion_inference == true and deployment_domain in [education, hiring]` | **Prohibited** | Art. 5(1)(f) — inferring emotions "in the areas of workplace and education institutions," except for medical/safety reasons. Does not require biometric data | Yes |
| 4 | `deployment_domain in [hiring, essential_services, law_enforcement, education, migration_asylum_border, critical_infrastructure]` | **High-Risk** | Annex III + Art. 6(2) — domain membership makes a system high-risk regardless of human oversight; `decision_autonomy` is deliberately not a condition here | Yes |
| 5 | `data_sensitivity == sensitive and affected_population == vulnerable_groups` | **High-Risk** | (project heuristic, not derived from a specific Act provision) | Yes — honestly labeled as non-Act-derived |
| 6 | `biometric_use == true and deployment_domain == biometric_id` | **High-Risk** | Annex III point 1(a)/(b); emotion recognition is separately covered under point 1(c) | Yes |
| 7 | `deployment_domain == general_consumer and data_sensitivity == none and decision_autonomy == human_in_loop` | **Minimal-Risk** | (project heuristic, not derived from a specific Act provision) | Yes — honestly labeled as non-Act-derived |
| 8 | *(default — no other rule fired)* | **Limited-Risk** | (project default tier — no specific Article; Art. 50(1) transparency duties may separately apply to systems that interact directly with people or generate synthetic content, but the Act has no blanket "Limited-Risk by default" provision). Justification string: "Classified as Limited-Risk because no higher- or lower-tier rule matched." | Yes — honestly labeled as non-Act-derived |

**Note on why `decision_autonomy` was removed from Rule 4's condition:** the original draft gated High-Risk on `decision_autonomy != human_in_loop`, letting a human-in-the-loop system in a named Annex III domain fall through to Limited-Risk. This was checked against the Act and found to be a factual error, not a defensible simplification: under Art. 6(2), Annex III domain membership makes a system high-risk regardless of human oversight, and the actual Art. 6(3) narrow exemption doesn't turn on autonomy. Since fixing this required no new extraction field, it was corrected rather than disclaimed. `decision_autonomy` is still extracted and still used — it now feeds the "human oversight" UNESCO/IEEE principle flag (Section 7) instead of the EU Act tier.

**Note on why "healthcare" is not a standalone domain:** clinical/diagnostic AI becomes high-risk primarily via the Annex I/medical-device route (Art. 6(1), MDR/IVDR), not Annex III, and a README can't reliably establish medical-device certification status — this tool doesn't claim to assess that path. Healthcare-access AI (triage prioritization, health insurance risk assessment, benefits/resource allocation) is a genuine Annex III Category 5 use case (points 5(a)/5(c)/5(d)) and is covered under `essential_services`. This distinction is stated in Section 9's limitations.

**Remaining acknowledged simplifications:** Rule 1's Art. 5(1)(h) statutory exceptions (victim search, imminent threat-to-life with judicial authorization) are not modeled. Rule 4 doesn't model the Art. 6(3) narrow-task exemption at all — every named-domain system is High-Risk here, over-inclusive relative to real Art. 6(3) carve-outs but not misleading. Rules 5, 7, and 8 are project-invented heuristics layered on the Act's actual tiers, explicitly labeled as such.

### 6.2.1 Citation verification status
Each rule in the implemented rule table carries a `citation_verified: bool` field, now set to True on all 8 rules following the citation audit against Regulation (EU) 2024/1689 (EUR-Lex).

### 6.3 Justification string format (for consistency)
```
"Classified as {TIER} because {field}={value} [and {field}={value} ...] "
"→ {plain-language reasoning} (see: {provision citation})"
```

### 6.4 Guardrails
- Max input text length to the LLM: cap at ~8,000 characters (README content beyond this rarely adds classification-relevant signal; truncate with a visible "(truncated)" notice rather than silently cutting).
  - **Where:** truncation happens in `extractor.py`, immediately before the LLM call — NOT in `github_fetch.py`.
  - `FetchedReadme.text` (and the stored pasted text) must always carry the full, untruncated content, because the raw-source toggle (Section 8) shows the original. Only the copy actually sent to the LLM is truncated, and the "(truncated)" notice is attached to that copy, never to the stored original.
- If GitHub fetch fails (private repo, no README, bad URL): surface a specific, actionable error — not a generic failure.
- If extraction returns a field value outside the allowed enum: reject and retry rather than passing an invalid value into the rule engine (the rule engine should never need defensive coding against malformed input from the extractor — validate at the boundary).

## 7. UNESCO & IEEE Principle Mapping

Separate from the EU AI Act tier, produce a secondary set of flags mapping extracted facts to relevant principles, so the tool visibly covers **two of the course's experiments** (Algorithmic Impact Assessments via UNESCO/IEEE frameworks, and the AI Act case study).

| Extracted signal | UNESCO principle implicated | IEEE EAD principle implicated |
|---|---|---|
| `human_oversight_mentioned == false` or `decision_autonomy == fully_autonomous` | Human oversight and determination | Accountability |
| `transparency_mentioned == false` | Transparency and explainability | Transparency |
| `affected_population == vulnerable_groups` | Fairness and non-discrimination | Human Rights |
| `data_sensitivity == sensitive` | Right to privacy and data protection | Data Agency |
| `social_scoring == true` or `real_time_biometric_public == true` | Human dignity and autonomy | Well-being |

Rationale for the human-oversight row's two triggers: documentation silence and an explicitly fully-autonomous pipeline are independent signals — either is sufficient to flag the concern.

**Documentation gaps vs. fact-based flags (decided after Phase 4):** the `human_oversight_mentioned == false` and `transparency_mentioned == false` triggers fire on documentation *silence*, so they flag nearly every repo (including plain utility libraries). They stay exactly as specified above — per Section 9, missing documentation is a finding — but each `PrincipleFlag` carries `documentation_gap: bool` (true only when every trigger that fired is silence-based), and the dashboard presents documentation-gap flags in a separate "Documentation gaps" group from fact-based flags. A flag with both kinds of trigger (e.g. silence plus `decision_autonomy == fully_autonomous`) counts as fact-based.

Each flagged principle should render in the dashboard with a one-line plain-language explanation of *why* it's flagged (which field triggered it), mirroring the EU AI Act "why this tier" transparency approach.

## 8. Dashboard / Output Specification

Single-page Streamlit app, one interaction flow:

1. **Input section** — tabs or radio for "GitHub URL" vs "Paste text"; text input/textarea; "Analyze" button
2. **Loading state** — spinner during fetch + extraction (can take a few seconds)
3. **Results section** (appears after analysis):
   - **Risk tier badge** — large, color-coded: red (Prohibited/High-Risk), amber (Limited-Risk), green (Minimal-Risk)
   - **Extracted facts table** — every field from Section 5, with its value and evidence snippet where available; `extraction_confidence` shown prominently if `low`
   - **"Why this tier" panel** — ALWAYS renders `justification` and `provision` as two separate lines, for every rule (including the Rule 8 default). Some justification strings already restate the provision in prose; that's fine — the panel does not deduplicate, it just consistently shows both fields
   - **Principle breakdown** — UNESCO/IEEE flags from Section 7, each with its one-line explanation; fact-based flags and documentation-gap flags (`documentation_gap == true`) rendered as two separate groups (see Section 7)
   - **Raw source toggle** — collapsible view of the actual README/text that was analyzed, for verification
4. **Example quick-picks** — 3–4 pre-loaded example repos spanning different tiers, as buttons, for a fast/reliable live demo that doesn't depend on live network conditions during presentation

### 8.1 Error states to handle gracefully in the UI
- Invalid/unreachable GitHub URL
- Repo with no README found
- Gemini API failure or rate limit
- Malformed extraction after retry
- Empty/too-short pasted text

## 9. Ethical Framing (for report/viva — do not omit from final writeup)

- **LLM does extraction only, not judgment.** The classification itself is deterministic and auditable, avoiding the irony of "an opaque AI deciding AI ethics compliance." State this explicitly as the project's central design decision.
- **Transparency by design.** Every classification shows its reasoning trace and the specific rule/provision that fired — the tool practices the explainability principle it audits others for.
- **Documentation opacity as a finding, not just a limitation.** If a system's tier depends heavily on how much its README discloses, that's not merely a tool limitation — it's evidence that *documentation completeness itself is an accountability mechanism*, and vague documentation is a way (intentional or not) that risk can be obscured. Surface `extraction_confidence: low` cases as an explicit finding in the report.
- **Known limitations to state honestly:** English-only, README-only (v1 doesn't inspect actual code/data), simplified rule provisions (acknowledged simplifications listed in 6.2), no legal validity — this is a decision-support/educational tool, not a compliance certification.
- **Healthcare limitation:** clinical/diagnostic AI is high-risk mainly via the Annex I/medical-device route (Art. 6(1), MDR/IVDR), which this tool does not assess — a README can't establish medical-device certification status. Only healthcare-access AI (Annex III points 5(a)/5(c)/5(d), extracted as `essential_services`) is classified as High-Risk by the rule engine.

## 10. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| LLM extraction | Gemini 3.8 Flash via `google-genai` SDK, free tier — confirmed working against the project's API key; `gemini-2.5-flash` is no longer available to new users, do not revert to it | JSON-mode / response-schema constrained output; automatic function calling explicitly disabled (see 5.1). **Model fallback chain:** `gemini-3.8-flash` → `gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash`. Free-tier quotas are per model (observed: 20 requests/day for 3.8 Flash), so on HTTP 429 or 503 the next model is tried; other errors are not retried. A malformed-output retry stays on the model that answered. `gemini-flash-latest` is excluded (shares 3.8's quota). Every result and fixture records which model produced it. |
| Backend | Python 3.10+ | |
| Rule engine | Plain Python, ordered list + dataclasses | No ML, no external deps beyond stdlib |
| GitHub fetch | `requests` against raw.githubusercontent.com | No auth for public repos |
| Frontend/dashboard | Streamlit | Fastest path to a polished demoable UI |
| Env/config | `python-dotenv`, `.env` for `GEMINI_API_KEY` | Never hardcode the key |
| Export (stretch) | `reportlab` or `weasyprint` for PDF | Only after core loop is solid |
| Deployment | Streamlit Community Cloud or Hugging Face Spaces | Free, gives a shareable link for portfolio/resume |

## 11. Project File Structure

```
actaudit/
├── app.py                  # Streamlit entrypoint — UI + orchestration only
├── extractor.py             # Gemini call, prompt, JSON parsing/retry logic
├── rules.py                  # Rule engine: rule table + evaluator
├── principles.py              # UNESCO/IEEE principle mapping (Section 7)
├── github_fetch.py            # README fetch logic + error handling
├── schema.py                   # Dataclass/TypedDict for extraction schema (Section 5)
├── examples/                    # Pre-loaded demo repos (name → URL or cached text)
│   └── quick_picks.py
├── tests/
│   ├── test_rules.py           # Unit tests: given a fact-set, assert correct tier
│   ├── test_extractor.py        # Mocked LLM response → schema validation
│   └── fixtures/                 # Sample READMEs for offline rule-engine testing
├── requirements.txt
├── .env.example
└── README.md                      # Setup + usage instructions (separate from course report)
```

## 12. Development Roadmap

### Phase 0 — Setup (30–45 min)
- [ ] Init repo, virtualenv, `requirements.txt`
- [ ] Get Gemini API key from Google AI Studio, set up `.env` / `.env.example`
- [x] Confirm `google-genai` SDK auth works with a trivial "hello world" call — done via `scripts/check_gemini.py` against `gemini-3.8-flash`

### Phase 1 — Schema & Rule Engine First (build and test this before any LLM/UI code)
*Rationale: the rule engine is the auditable core and the part your grade most depends on. Build and unit-test it against hand-written fact-sets before it ever depends on a live LLM call — this de-risks the whole project, since if the LLM pipeline breaks the night before the demo, the rule engine (the actually-gradeable logic) is still proven correct.*
- [ ] `schema.py`: define the extraction schema as a dataclass/TypedDict with enums
- [ ] `rules.py`: implement the ordered rule table from Section 6.2
- [ ] `tests/test_rules.py`: write ~10 hand-crafted fact-sets (one per rule + a couple of default-fallthrough cases) and assert the correct tier + justification fires
- [ ] Manually verify EU AI Act article/annex citations used in the rule table (action item from 6.2) — do this before writing the report, not after

### Phase 2 — GitHub Fetch (standalone, testable in isolation)
- [ ] `github_fetch.py`: given a repo URL, try README variants across main/master
- [ ] Handle: no README found, invalid URL, private repo, rate-limited request
- [ ] Quick manual test against 3–4 real public repos

### Phase 3 — LLM Extraction
- [x] `extractor.py`: prompt design per Section 5.1, JSON-schema-constrained Gemini call
- [x] Retry-once-on-malformed-JSON logic
- [x] Field-level enum validation at the boundary (reject/retry invalid extractor output rather than passing it downstream)
- [x] Test against 8–10 real READMEs spanning different domains/risk levels (aim for coverage: a face-recognition tool, a hiring tool, a credit-scoring tool, a general chatbot, a clinical/diagnostic tool such as medical imaging analysis (expected domain: `other`), a healthcare-access tool such as triage prioritization or health-insurance pricing (expected domain: `essential_services`), a plain utility library) — record actual outputs in `tests/fixtures/` so extraction behavior is reproducible even if the live API changes later
  - **Fixture history:** the 10-repo set in `tests/fixtures/` (recorded by `scripts/record_fixtures.py`) was re-recorded in full after two prompt fixes found in live testing: (1) the biometric routing instruction (Section 5.1), after a fallback model routed ageitgey/face_recognition to `other`; (2) the narrowed definition of `other`, after ayhandis/creditR routed to `other`. The committed set is the one recorded after both fixes (2026-09-27), and every repo classifies as expected. Each fixture records the model that answered; the set spans `gemini-3.6/3.7/3.8-flash` because of per-model free-tier quotas.
  - **Robustness added during recording:** transport failures (timeouts, dropped connections) are wrapped as `ExtractionAPIError`, and the default client uses a 60s request timeout.

### Phase 4 — Principle Mapping
- [x] `principles.py`: implement Section 7's UNESCO/IEEE flag logic (not first-match: every implicated principle is flagged; multi-trigger rows report each trigger that fired)
- [x] Unit test alongside the rule engine tests (`tests/test_principles.py`)

### Phase 5 — Integration
- [ ] Wire fetch → extract → rules → principles into a single callable pipeline function (keep this decoupled from Streamlit so it's independently testable)
- [ ] End-to-end test: real GitHub URL in, full result object out

### Phase 6 — Dashboard
- [ ] `app.py`: input tabs, analyze button, loading state
- [ ] Results rendering per Section 8 (badge, facts table, why-this-tier panel, principle breakdown)
- [ ] Raw source toggle
- [ ] Quick-pick example buttons (Section 8, point 4) — cache their extraction results so the demo doesn't depend on live API latency/availability during presentation
- [ ] Error states per Section 8.1, rendered as friendly warnings not stack traces

### Phase 7 — Polish & Deploy
- [ ] Visual pass on the Streamlit UI (spacing, color consistency, badge styling)
- [ ] Deploy to Streamlit Community Cloud / HF Spaces
- [ ] Smoke-test the deployed link end-to-end (env vars carry over correctly, no localhost-only assumptions)

### Phase 8 — Report & Submission Materials
- [ ] Write methodology section: the extraction/rules split (Section 1.1), citing this as the core ethical design decision
- [ ] Document known limitations honestly (Section 9)
- [ ] Screenshots / short demo recording
- [ ] Finalize rule-table citations against actual EU AI Act text (do not submit with placeholder/unverified article numbers)

### Stretch goals (only after Phase 7 is fully done — do not start these early)
- [ ] PDF export of a given result
- [ ] Batch mode: analyze multiple repos, comparative table
- [ ] "Sensitivity" view: show how tier would change if a given field were different (demonstrates how documentation completeness affects classification — ties back to Section 9)

## 13. Deliverables Checklist

- [ ] Working Streamlit app (deployed, public link)
- [ ] GitHub repo: clean structure per Section 11, README with setup instructions, rule-table documentation
- [ ] Test suite covering rule engine (minimum) and ideally extraction schema validation
- [ ] Short demo video / screenshots for course submission
- [ ] Course report: problem statement, methodology (Sections 1–7 adapted), ethical framing (Section 9), verified citations, limitations

## 14. Open Decisions / Things to Revisit

- ~~Exact EU AI Act article/annex numbers in the rule table are unverified placeholders~~ — resolved: citations audited against Regulation (EU) 2024/1689 (Section 6.2 / 6.2.1).
- Whether `human_on_loop` vs `human_in_loop` distinction is worth the added extraction complexity, or should be collapsed to a boolean `has_human_oversight` — current schema keeps the 3-way enum for richer justification text; revisit if extraction accuracy on this field proves unreliable in Phase 3 testing.
- PDF export and batch mode are explicitly stretch-only — do not let them creep into the Phase 1–7 critical path.
