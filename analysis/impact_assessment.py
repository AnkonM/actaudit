"""Tab 6 · Algorithmic impact assessment (Experiment 6).

Built only from extracted facts (and dataset findings, if any), with no LLM:
- the six elements Art. 27(1) lists for a fundamental-rights impact assessment
  (verified against the Official Journal text of Regulation (EU) 2024/1689), each
  filled from facts or marked "Not determinable from documentation";
- an impact level I–IV from a project-defined scoring table *inspired by* the Canadian
  Algorithmic Impact Assessment tool (Directive on Automated Decision-Making) — not the
  official Canadian questionnaire or scoring;
- recommended actions from a fixed rule table, each with a citation and verified flag;
- Markdown and PDF reports built from fixed template text and escaped values only.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from analysis import harms
from analysis.proxy import PROXY_PATTERNS
from rules import RiskTier
from schema import (
    AffectedPopulation,
    DataSensitivity,
    DecisionAutonomy,
    DeploymentDomain as D,
    ExtractedFacts,
    ExtractionConfidence,
)

NOT_DETERMINABLE = "Not determinable from documentation"
PROJECT_HEURISTIC = "project heuristic, not derived from a specific Act provision"
DISCLAIMER = (
    "Educational decision-support output from ActAudit, implementing a simplified subset of "
    "the EU AI Act. Not legal advice or a compliance certification. Facts were extracted "
    "from documentation by an LLM; every judgment below comes from fixed, published rules."
)
IMPACT_LEVEL_LABEL = (
    "Project-defined impact level, inspired by the Canadian Algorithmic Impact Assessment "
    "tool (Directive on Automated Decision-Making). Not the official Canadian scoring."
)


# --- Art. 27(1) elements ------------------------------------------------------------------------

# (point, the Article's element, condensed from the verified text)
ART27_ELEMENTS = [
    ("a", "Processes in which the system will be used, in line with its intended purpose"),
    ("b", "Period of time within which, and frequency with which, it is intended to be used"),
    ("c", "Categories of natural persons and groups likely to be affected"),
    ("d", "Specific risks of harm likely to affect those persons or groups"),
    ("e", "Implementation of human oversight measures"),
    ("f", "Measures if those risks materialise, including internal governance and complaint mechanisms"),
]


@dataclass(frozen=True)
class Element:
    point: str
    title: str
    lines: list[str]  # plain text; UI and reports escape them
    determinable: bool


def _ev(facts: ExtractedFacts, name: str) -> str:
    snippet = facts.evidence_snippets.get(name)
    return f' (documentation: "{snippet}")' if snippet else ""


def _elements(facts: ExtractedFacts, dataset_findings: list[str] | None) -> list[Element]:
    out = []
    # (a) intended purpose and domain
    lines = []
    if facts.system_purpose:
        lines.append(f"Intended purpose: {facts.system_purpose}")
    if facts.deployment_domain != D.OTHER:
        lines.append(f"Deployment domain: {facts.deployment_domain.value}{_ev(facts, 'deployment_domain')}")
    if lines:
        lines.append("The deployer's own processes aren't described in provider documentation.")
    out.append(Element("a", ART27_ELEMENTS[0][1], lines or [NOT_DETERMINABLE], bool(lines)))
    # (b) period and frequency — no field records it, except real-time public use
    if facts.real_time_biometric_public:
        lines = ["Real-time, continuous use in publicly accessible spaces is described"
                 f"{_ev(facts, 'real_time_biometric_public')}.",
                 "The period of use is not stated."]
        out.append(Element("b", ART27_ELEMENTS[1][1], lines, True))
    else:
        out.append(Element("b", ART27_ELEMENTS[1][1], [NOT_DETERMINABLE], False))
    # (c) affected persons
    parties = [p for p in harms.affected_parties(facts) if not p.party.startswith(NOT_DETERMINABLE)]
    out.append(Element("c", ART27_ELEMENTS[2][1],
                       [f"{p.party} (from {p.reason})" for p in parties] or [NOT_DETERMINABLE],
                       bool(parties)))
    # (d) risks of harm
    lines = [f"{f.category}: {f.harm}" for f in harms.harm_findings(facts)]
    lines += [f"Dataset: {line}" for line in dataset_findings or []]
    out.append(Element("d", ART27_ELEMENTS[3][1], lines or [NOT_DETERMINABLE], bool(lines)))
    # (e) human oversight
    lines = []
    if facts.human_oversight_mentioned:
        lines.append("The documentation mentions human review, override or appeal"
                     f"{_ev(facts, 'human_oversight_mentioned')}.")
    if facts.decision_autonomy != DecisionAutonomy.HUMAN_ON_LOOP or "decision_autonomy" in facts.evidence_snippets:
        lines.append(f"Decision autonomy: {facts.decision_autonomy.value}{_ev(facts, 'decision_autonomy')}.")
    out.append(Element("e", ART27_ELEMENTS[4][1],
                       lines or [f"{NOT_DETERMINABLE}: no human review, override or appeal "
                                 "mechanism is described."], bool(lines)))
    # (f) measures if risks materialise
    lines = []
    if facts.failsafe_mentioned:
        lines.append(f"Fallback or fail-safe behaviour is described{_ev(facts, 'failsafe_mentioned')}.")
    if facts.human_oversight_mentioned:
        lines.append("Human review or appeal is mentioned (see (e)); no complaint mechanism is "
                     "extracted separately.")
    out.append(Element("f", ART27_ELEMENTS[5][1],
                       lines or [f"{NOT_DETERMINABLE}: no fallback, governance or complaint "
                                 "mechanism is described."], bool(lines)))
    return out


def art27_applicability(tier: RiskTier, facts: ExtractedFacts) -> str:
    if tier == RiskTier.HIGH_RISK:
        text = ("Art. 27 requires this assessment before first use by deployers that are bodies "
                "governed by public law or private entities providing public services, and by "
                "deployers of credit-scoring and life/health-insurance pricing systems "
                "(Annex III points 5(b)–(c)); systems in critical infrastructure (Annex III "
                "point 2) are exempt. It is used here as the structure either way.")
        if facts.deployment_domain == D.CRITICAL_INFRASTRUCTURE:
            text += " This system's domain is critical infrastructure, which Art. 27(1) excludes."
        return text
    return (f"For a {tier.value} system Art. 27 doesn't require this assessment; its six "
            "elements are used here as a structured framework.")


# --- Impact level (project-defined, AIA-inspired) --------------------------------------------------

@dataclass(frozen=True)
class Factor:
    label: str
    condition_text: str
    points: int
    condition: Callable[[ExtractedFacts], bool]
    mitigation: bool = False


ANNEX_III_LIKE = {D.HIRING, D.ESSENTIAL_SERVICES, D.LAW_ENFORCEMENT, D.EDUCATION,
                  D.MIGRATION_ASYLUM_BORDER, D.CRITICAL_INFRASTRUCTURE, D.BIOMETRIC_ID}

IMPACT_SCORING: list[Factor] = [
    Factor("Domain", "Annex III area or biometric_id", 3, lambda f: f.deployment_domain in ANNEX_III_LIKE),
    Factor("Domain", "content_moderation", 2, lambda f: f.deployment_domain == D.CONTENT_MODERATION),
    Factor("Domain", "general_consumer", 1, lambda f: f.deployment_domain == D.GENERAL_CONSUMER),
    Factor("Data", "sensitive data", 2, lambda f: f.data_sensitivity == DataSensitivity.SENSITIVE),
    Factor("Data", "personal data", 1, lambda f: f.data_sensitivity == DataSensitivity.PERSONAL),
    Factor("People", "vulnerable groups affected", 2,
           lambda f: f.affected_population == AffectedPopulation.VULNERABLE_GROUPS),
    Factor("Autonomy", "fully autonomous", 3, lambda f: f.decision_autonomy == DecisionAutonomy.FULLY_AUTONOMOUS),
    Factor("Autonomy", "human on the loop", 1, lambda f: f.decision_autonomy == DecisionAutonomy.HUMAN_ON_LOOP),
    Factor("Capability", "social scoring", 3, lambda f: f.social_scoring),
    Factor("Capability", "real-time biometric ID in public", 3, lambda f: f.real_time_biometric_public),
    Factor("Capability", "military / defence use", 3, lambda f: f.military_defence_use),
    Factor("Capability", "emotion inference", 2, lambda f: f.emotion_inference),
    Factor("Capability", "impersonation of real people", 2, lambda f: f.impersonation_capable),
    Factor("Capability", "biometric data", 1, lambda f: f.biometric_use),
    Factor("Capability", "generates synthetic media", 1, lambda f: f.generates_synthetic_media),
    Factor("Capability", "proxy target", 1, lambda f: f.target_type in PROXY_PATTERNS),
    Factor("Mitigation", "human oversight documented", -1, lambda f: f.human_oversight_mentioned, True),
    Factor("Mitigation", "transparency documented", -1, lambda f: f.transparency_mentioned, True),
    Factor("Mitigation", "robustness testing documented", -1, lambda f: f.robustness_testing_mentioned, True),
    Factor("Mitigation", "fail-safe documented", -1, lambda f: f.failsafe_mentioned, True),
]
# (upper bound of the score, level, meaning); a score above the last bound is level IV.
LEVEL_BANDS = [(2, "I", "little to no impact"), (5, "II", "moderate impact"),
               (8, "III", "high impact"), (10**9, "IV", "very high impact")]


@dataclass(frozen=True)
class ImpactLevel:
    level: str
    meaning: str
    score: int  # impact points minus mitigation points, not below 0
    impact_points: int
    mitigation_points: int
    applied: list[tuple[str, str, int]]  # (factor, condition, points) that applied
    override: str | None  # why the level was forced, if it was


def impact_level(facts: ExtractedFacts, tier: RiskTier) -> ImpactLevel:
    applied = [(f.label, f.condition_text, f.points) for f in IMPACT_SCORING if f.condition(facts)]
    impact = sum(p for _, _, p in applied if p > 0)
    mitigation = -sum(p for _, _, p in applied if p < 0)
    score = max(impact - mitigation, 0)
    level, meaning = next((lvl, m) for bound, lvl, m in LEVEL_BANDS if score <= bound)
    override = None
    if tier == RiskTier.PROHIBITED and level != "IV":
        level, meaning = "IV", "very high impact"
        override = "A prohibited practice is always level IV."
    return ImpactLevel(level, meaning, score, impact, mitigation, applied, override)


# --- Recommended actions ------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    action: str
    because: str
    citation: str
    citation_verified: bool


@dataclass(frozen=True)
class ActionRule:
    condition: Callable[[ExtractedFacts, RiskTier, bool], bool]  # (facts, tier, dataset_flagged)
    action: str
    because: str
    citation: str
    citation_verified: bool = True


ACTION_RULES: list[ActionRule] = [
    ActionRule(lambda f, t, d: t == RiskTier.PROHIBITED,
               "Do not deploy: the practice is prohibited in the EU.",
               "the system was classified Prohibited", "EU AI Act Art. 5(1)"),
    ActionRule(lambda f, t, d: t == RiskTier.OUT_OF_SCOPE,
               "Apply the law of armed conflict and national-security oversight regimes, and keep "
               "meaningful human control over any use of force.",
               "military_defence_use=true (the AI Act does not apply)", PROJECT_HEURISTIC),
    ActionRule(lambda f, t, d: not f.human_oversight_mentioned
               or f.decision_autonomy == DecisionAutonomy.FULLY_AUTONOMOUS,
               "Define human review of decisions, with the power to override or reverse outputs, "
               "and an appeal route for the people affected.",
               "no human oversight is documented, or decisions are fully autonomous",
               "EU AI Act Art. 14(4)(d) (required for high-risk systems)"),
    ActionRule(lambda f, t, d: f.data_sensitivity == DataSensitivity.SENSITIVE,
               "Carry out a data protection impact assessment before processing.",
               "data_sensitivity=sensitive (special categories of personal data)",
               "GDPR (Regulation (EU) 2016/679) Art. 35(1), 35(3)(b)"),
    ActionRule(lambda f, t, d: f.real_time_biometric_public,
               "Carry out a data protection impact assessment for systematic monitoring of "
               "public spaces.", "real_time_biometric_public=true",
               "GDPR (Regulation (EU) 2016/679) Art. 35(3)(c)"),
    ActionRule(lambda f, t, d: f.data_sensitivity == DataSensitivity.PERSONAL,
               "Confirm the lawful basis for processing and whether a data protection impact "
               "assessment is required.", "data_sensitivity=personal",
               "GDPR (Regulation (EU) 2016/679) Art. 35(1)"),
    ActionRule(lambda f, t, d: not f.transparency_mentioned,
               "Tell people when they are interacting with an AI system.",
               "transparency_mentioned=false", "EU AI Act Art. 50(1)"),
    ActionRule(lambda f, t, d: t == RiskTier.HIGH_RISK,
               "Establish and maintain a risk-management system across the system's lifecycle.",
               "the system was classified High-Risk", "EU AI Act Art. 9(1)"),
    ActionRule(lambda f, t, d: t == RiskTier.HIGH_RISK,
               "Examine training, validation and testing data for possible biases and "
               "representativeness (see Tab 2 · Dataset Bias).",
               "the system was classified High-Risk", "EU AI Act Art. 10(2)(f)–(g), 10(3)"),
    ActionRule(lambda f, t, d: d,
               "Address the dataset issues flagged in the dataset findings before training or "
               "deployment.", "the loaded dataset has flagged findings", "EU AI Act Art. 10(3)"),
    ActionRule(lambda f, t, d: not f.robustness_testing_mentioned,
               "Measure and document accuracy and robustness, including adversarial testing, "
               "and declare the accuracy metrics.", "robustness_testing_mentioned=false",
               "EU AI Act Art. 15(1), 15(3), 15(5) (required for high-risk systems)"),
    ActionRule(lambda f, t, d: not f.failsafe_mentioned
               and (f.decision_autonomy == DecisionAutonomy.FULLY_AUTONOMOUS or t == RiskTier.HIGH_RISK),
               "Define fail-safe behaviour and a way to stop the system in a safe state.",
               "failsafe_mentioned=false for an autonomous or high-risk system",
               "EU AI Act Art. 15(4), 14(4)(e)"),
    ActionRule(lambda f, t, d: f.generates_synthetic_media and not f.output_marking_mentioned,
               "Mark generated outputs in a machine-readable format (e.g. watermarking or "
               "provenance metadata).", "synthetic media without documented output marking",
               "EU AI Act Art. 50(2)"),
    ActionRule(lambda f, t, d: f.impersonation_capable and not f.consent_safeguards_mentioned,
               "Require consent and identity verification before reproducing a real person, and "
               "publish a usage policy against impersonation.",
               "impersonation_capable=true without documented consent safeguards", PROJECT_HEURISTIC),
    ActionRule(lambda f, t, d: f.target_type in PROXY_PATTERNS,
               "Check that the prediction target measures what matters, and test for proxy bias "
               "(see Tab 4 · Proxy Audit).", "the target is a known proxy", PROJECT_HEURISTIC),
    ActionRule(lambda f, t, d: f.extraction_confidence == ExtractionConfidence.LOW,
               "Improve the documentation: state the intended use, who is affected, and the "
               "oversight in place.", "extraction_confidence=low", PROJECT_HEURISTIC),
]


def recommended_actions(facts: ExtractedFacts, tier: RiskTier, dataset_flagged: bool = False) -> list[Action]:
    return [Action(r.action, r.because, r.citation, r.citation_verified)
            for r in ACTION_RULES if r.condition(facts, tier, dataset_flagged)]


# --- The assessment ------------------------------------------------------------------------------

@dataclass(frozen=True)
class ImpactAssessment:
    system: str
    generated_on: str
    tier: str
    rule_number: int
    justification: str
    provision: str
    provision_verified: bool
    applicability: str
    principles: list[dict[str, Any]]
    elements: list[Element]
    impact: ImpactLevel
    actions: list[Action]
    dataset_name: str | None = None
    dataset_findings: list[str] = field(default_factory=list)


def build(result: Any, dataset_name: str | None = None, dataset_findings: list[str] | None = None,
          dataset_flagged: bool = False, today: date | None = None) -> ImpactAssessment:
    """Assemble the assessment from an AnalysisResult (and optional dataset findings)."""
    facts = result.extraction.facts
    c = result.classification
    return ImpactAssessment(
        system=result.source_label,
        generated_on=(today or date.today()).isoformat(),
        tier=c.tier.value, rule_number=c.rule_number, justification=c.justification,
        provision=c.provision, provision_verified=c.citation_verified,
        applicability=art27_applicability(c.tier, facts),
        principles=[{"unesco": p.unesco, "ieee": p.ieee, "ieee_ref": p.ieee_ref,
                     "explanation": p.explanation, "documentation_gap": p.documentation_gap}
                    for p in result.principles],
        elements=_elements(facts, dataset_findings),
        impact=impact_level(facts, c.tier),
        actions=recommended_actions(facts, c.tier, dataset_flagged),
        dataset_name=dataset_name,
        dataset_findings=list(dataset_findings or []),
    )


# --- Reports -------------------------------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def md_escape(text: Any) -> str:
    """Render untrusted text literally in Markdown (no links, emphasis or HTML)."""
    return _MD_SPECIAL.sub(r"\\\1", " ".join(str(text).split()))


def _verified(flag: bool) -> str:
    return "verified" if flag else "unverified"


def to_markdown(ia: ImpactAssessment) -> str:
    e = md_escape
    lines = [
        "# ActAudit algorithmic impact assessment", "",
        f"> {DISCLAIMER}", "",
        f"**System:** {e(ia.system)}  ", f"**Generated:** {ia.generated_on}", "",
        "## EU AI Act classification", "",
        f"**Tier:** {e(ia.tier)} (rule {ia.rule_number})", "",
        e(ia.justification), "",
        f"**Provision:** {e(ia.provision)} (citation {_verified(ia.provision_verified)})", "",
        "## UNESCO and IEEE principle flags", "",
    ]
    if not ia.principles:
        lines.append("No principle concerns were flagged.")
    for p in ia.principles:
        kind = "documentation gap" if p["documentation_gap"] else "from stated facts"
        lines.append(f"- **{e(p['ieee'])}** ({e(p['ieee_ref'])}) / **{e(p['unesco'])}** "
                     f"(UNESCO Recommendation on the Ethics of AI, 2021), {kind}: {e(p['explanation'])}")
    lines += ["", "## Impact assessment (structure of EU AI Act Art. 27(1))", "", e(ia.applicability), ""]
    for el in ia.elements:
        lines.append(f"### ({el.point}) {e(el.title)}")
        lines += [f"- {e(line)}" for line in el.lines] + [""]
    lvl = ia.impact
    lines += [
        "## Impact level", "", f"**Level {lvl.level}** — {lvl.meaning}. Score {lvl.score} = "
        f"{lvl.impact_points} impact points − {lvl.mitigation_points} mitigation points.", "",
        f"*{IMPACT_LEVEL_LABEL}*", "",
    ]
    if lvl.override:
        lines += [lvl.override, ""]
    lines += ["| Factor | Condition | Points |", "|---|---|---|"]
    lines += [f"| {e(f)} | {e(c)} | {p:+d} |" for f, c, p in lvl.applied] or ["| — | none applied | 0 |"]
    lines += ["", "## Recommended actions", ""]
    for a in ia.actions:
        lines.append(f"- {e(a.action)} *Because:* {e(a.because)}. *Citation:* {e(a.citation)} "
                     f"({_verified(a.citation_verified)})")
    if ia.dataset_name:
        lines += ["", "## Dataset results", "", f"Dataset: {e(ia.dataset_name)}", ""]
        lines += [f"- {e(x)}" for x in ia.dataset_findings] or ["- No findings."]
    return "\n".join(lines) + "\n"


_LATIN1 = str.maketrans({"—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
                         "→": "->", "×": "x", "÷": "/", "≥": ">=", "≤": "<=", "…": "...",
                         "−": "-", "•": "-", "·": "-"})


def _latin1(text: Any) -> str:
    """fpdf2's core fonts are latin-1 only: map common symbols, replace the rest."""
    return str(text).translate(_LATIN1).encode("latin-1", "replace").decode("latin-1")


def to_pdf(ia: ImpactAssessment) -> bytes:
    """A plain PDF of the same content. Text is written with plain cells (no markup
    mode), so no value can inject formatting."""
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title("ActAudit algorithmic impact assessment")
    pdf.add_page()

    def heading(text: str, size: int = 13) -> None:
        pdf.set_font("Helvetica", "B", size)
        pdf.multi_cell(0, 7, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def para(text: str, style: str = "", size: int = 10) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, 5, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    heading("ActAudit algorithmic impact assessment", 16)
    para(DISCLAIMER, "I", 9)
    para(f"System: {ia.system}    Generated: {ia.generated_on}")
    heading("EU AI Act classification")
    para(f"Tier: {ia.tier} (rule {ia.rule_number})", "B")
    para(ia.justification)
    para(f"Provision: {ia.provision} (citation {_verified(ia.provision_verified)})")
    heading("UNESCO and IEEE principle flags")
    if not ia.principles:
        para("No principle concerns were flagged.")
    for p in ia.principles:
        kind = "documentation gap" if p["documentation_gap"] else "from stated facts"
        para(f"- {p['ieee']} ({p['ieee_ref']}) / {p['unesco']} (UNESCO Recommendation on the "
             f"Ethics of AI, 2021), {kind}: {p['explanation']}")
    heading("Impact assessment (structure of EU AI Act Art. 27(1))")
    para(ia.applicability, "I", 9)
    for el in ia.elements:
        para(f"({el.point}) {el.title}", "B")
        for line in el.lines:
            para(f"- {line}")
    heading("Impact level")
    lvl = ia.impact
    para(f"Level {lvl.level} - {lvl.meaning}. Score {lvl.score} = {lvl.impact_points} impact "
         f"points - {lvl.mitigation_points} mitigation points.", "B")
    para(IMPACT_LEVEL_LABEL, "I", 9)
    if lvl.override:
        para(lvl.override)
    for f, c, pts in lvl.applied:
        para(f"{f}: {c} ({pts:+d})", size=9)
    heading("Recommended actions")
    for a in ia.actions:
        para(f"- {a.action} Because: {a.because}. Citation: {a.citation} ({_verified(a.citation_verified)})")
    if ia.dataset_name:
        heading("Dataset results")
        para(f"Dataset: {ia.dataset_name}")
        for x in ia.dataset_findings or ["No findings."]:
            para(f"- {x}")
    return bytes(pdf.output())
