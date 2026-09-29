"""Tab 1 ethical analysis: affected parties and harm categories (blueprint §15.4, Exp 1).

Deterministic mapping from extracted facts: no LLM, no scoring. Like principles.py,
every harm rule whose condition holds is reported (not first-match), with the facts
that triggered it and their evidence. The mapping is a project heuristic, labelled as
such in the UI; each rule carries a one-line rationale.

Harm categories follow the allocative / quality-of-service / representational
taxonomy common in AI-fairness work, plus privacy and autonomy/dignity.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from rules import RiskTier
from schema import (
    AffectedPopulation,
    DataSensitivity,
    DecisionAutonomy,
    DeploymentDomain as D,
    ExtractedFacts,
    TargetType,
)

PROJECT_HEURISTIC = "project heuristic, not derived from a specific Act provision"

ALLOCATIVE = "Allocative"
QUALITY_OF_SERVICE = "Quality-of-service"
REPRESENTATIONAL = "Representational"
PRIVACY = "Privacy"
AUTONOMY_DIGNITY = "Autonomy and dignity"

HARM_CATEGORIES: tuple[str, ...] = (
    ALLOCATIVE, QUALITY_OF_SERVICE, REPRESENTATIONAL, PRIVACY, AUTONOMY_DIGNITY,
)
CATEGORY_MEANING: dict[str, str] = {
    ALLOCATIVE: "withholding opportunities or resources (jobs, credit, benefits, liberty)",
    QUALITY_OF_SERVICE: "working worse for some people than for others",
    REPRESENTATIONAL: "portraying people or groups in stereotyped, demeaning or false ways",
    PRIVACY: "exposing or misusing information about people",
    AUTONOMY_DIGNITY: "taking decisions out of people's hands or treating them as objects",
}

# Target types where the predicted quantity is a known proxy for what matters (Tab 4).
PROXY_PRONE_TARGETS = frozenset({
    TargetType.COST_OR_SPENDING,
    TargetType.ARRESTS_OR_POLICE_CONTACT,
    TargetType.ENGAGEMENT_OR_CLICKS,
    TargetType.PAST_HUMAN_DECISIONS,
})

ALLOCATING_DOMAINS = frozenset({
    D.HIRING, D.ESSENTIAL_SERVICES, D.EDUCATION, D.LAW_ENFORCEMENT, D.MIGRATION_ASYLUM_BORDER,
})


def _value_str(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, tuple):
        return "[" + ", ".join(_value_str(v) for v in value) + "]"
    return str(value)


@dataclass(frozen=True)
class HarmRule:
    category: str
    condition: Callable[[ExtractedFacts], bool]
    trigger_fields: tuple[str, ...]
    harm: str  # what could go wrong, in plain language
    rationale: str  # one line: why these facts map to this harm


@dataclass(frozen=True)
class HarmFinding:
    category: str
    harm: str
    rationale: str
    fired_fields: tuple[tuple[str, str], ...]
    evidence: dict[str, str]


HARM_RULES: list[HarmRule] = [
    # --- Allocative -----------------------------------------------------------------
    HarmRule(
        ALLOCATIVE,
        lambda f: f.deployment_domain in ALLOCATING_DOMAINS,
        ("deployment_domain",),
        "Errors or bias can decide who gets a job, credit, a benefit, a school place, "
        "a legal status or their liberty.",
        "these domains allocate opportunities or resources, so mistakes translate directly "
        "into who receives them",
    ),
    HarmRule(
        ALLOCATIVE,
        lambda f: f.social_scoring,
        ("social_scoring",),
        "A score that follows people across unrelated contexts can shut them out of "
        "services or opportunities.",
        "general-purpose trustworthiness scores are used to ration access",
    ),
    HarmRule(
        ALLOCATIVE,
        lambda f: f.target_type in PROXY_PRONE_TARGETS,
        ("target_type",),
        "The system predicts a proxy; people for whom the proxy under-measures need or "
        "merit can be under-served (see Tab 4).",
        "proxy targets such as cost, arrests or past decisions encode existing inequalities",
    ),
    # --- Quality-of-service ---------------------------------------------------------
    HarmRule(
        QUALITY_OF_SERVICE,
        lambda f: f.biometric_use,
        ("biometric_use",),
        "Biometric matching can be less accurate for some demographic groups, giving them "
        "more false matches or rejections.",
        "face and other biometric analysis has documented accuracy differences across groups",
    ),
    HarmRule(
        QUALITY_OF_SERVICE,
        lambda f: f.emotion_inference,
        ("emotion_inference",),
        "Emotion inference can systematically misread people whose expressions differ from "
        "the training data.",
        "how emotions are expressed varies across cultures and individuals",
    ),
    HarmRule(
        QUALITY_OF_SERVICE,
        lambda f: f.affected_population == AffectedPopulation.VULNERABLE_GROUPS,
        ("affected_population",),
        "Vulnerable users can be poorly served by a system not designed or tested with them.",
        "children, patients and people with disabilities are often under-represented in "
        "design and testing",
    ),
    # --- Representational -----------------------------------------------------------
    HarmRule(
        REPRESENTATIONAL,
        lambda f: f.deployment_domain == D.CONTENT_MODERATION,
        ("deployment_domain",),
        "Moderation or ranking can suppress, demote or stereotype particular groups' content.",
        "deciding what is visible shapes how groups are represented",
    ),
    HarmRule(
        REPRESENTATIONAL,
        lambda f: f.emotion_inference or f.biometric_use,
        ("emotion_inference", "biometric_use"),
        "Categorising people from their face or behaviour can attach stereotyped or "
        "demeaning labels.",
        "inferred labels are applied to people without their say",
    ),
    HarmRule(
        REPRESENTATIONAL,
        lambda f: f.generates_synthetic_media,
        ("generates_synthetic_media",),
        "Generated content can depict people or groups falsely or in stereotyped ways "
        "(see Tab 3).",
        "generative models reproduce patterns, including stereotypes, from their training data",
    ),
    HarmRule(
        REPRESENTATIONAL,
        lambda f: f.target_type == TargetType.ENGAGEMENT_OR_CLICKS,
        ("target_type",),
        "Optimising for engagement can amplify sensational or stereotyped content.",
        "engagement rewards what attracts attention, not what is accurate or fair",
    ),
    # --- Privacy --------------------------------------------------------------------
    HarmRule(
        PRIVACY,
        lambda f: f.data_sensitivity in (DataSensitivity.PERSONAL, DataSensitivity.SENSITIVE),
        ("data_sensitivity",),
        "Information about identifiable people can be exposed, repurposed or retained "
        "longer than needed.",
        "any processing of personal data creates exposure; sensitive data raises the stakes",
    ),
    HarmRule(
        PRIVACY,
        lambda f: f.biometric_use,
        ("biometric_use",),
        "Biometric data identifies people permanently: unlike a password, a face can't "
        "be changed after a leak.",
        "biometric identifiers are unique and immutable",
    ),
    HarmRule(
        PRIVACY,
        lambda f: f.real_time_biometric_public,
        ("real_time_biometric_public",),
        "Identifying people in public spaces in real time removes anonymity in public.",
        "live identification makes everyone passing a camera identifiable",
    ),
    # --- Autonomy and dignity -------------------------------------------------------
    HarmRule(
        AUTONOMY_DIGNITY,
        lambda f: f.decision_autonomy == DecisionAutonomy.FULLY_AUTONOMOUS,
        ("decision_autonomy",),
        "Decisions are taken with no human review, so people can't be heard before a "
        "decision about them.",
        "fully automated decisions remove the chance to explain or contest",
    ),
    HarmRule(
        AUTONOMY_DIGNITY,
        lambda f: f.social_scoring,
        ("social_scoring",),
        "Reducing a person to a general trustworthiness score treats them as a number.",
        "social scoring judges people by aggregated behaviour, not as individuals",
    ),
    HarmRule(
        AUTONOMY_DIGNITY,
        lambda f: f.emotion_inference,
        ("emotion_inference",),
        "Inferring inner emotional states intrudes on people's mental privacy.",
        "emotions are inferred without the person choosing to disclose them",
    ),
    HarmRule(
        AUTONOMY_DIGNITY,
        lambda f: f.impersonation_capable,
        ("impersonation_capable",),
        "Reproducing a real person's face or voice takes control of their likeness away "
        "from them (see Tab 3).",
        "impersonation uses someone's identity without their consent",
    ),
    HarmRule(
        AUTONOMY_DIGNITY,
        lambda f: f.real_time_biometric_public,
        ("real_time_biometric_public",),
        "Being identified wherever you go can deter people from assembling or moving freely.",
        "pervasive identification has a chilling effect on public life",
    ),
    HarmRule(
        AUTONOMY_DIGNITY,
        lambda f: f.military_defence_use,
        ("military_defence_use",),
        "Outputs can feed decisions affecting life and liberty, where meaningful human "
        "control matters most (see Tab 7).",
        "military and security uses carry the gravest consequences of error",
    ),
]


def harm_findings(facts: ExtractedFacts) -> list[HarmFinding]:
    """Every harm rule whose condition holds, in HARM_RULES order (grouped by category).

    A rule with several trigger fields reports only those that are set, e.g. the
    representational categorisation rule reports emotion_inference and/or biometric_use.
    """
    findings = []
    for rule in HARM_RULES:
        if not rule.condition(facts):
            continue
        fired = tuple(
            (name, _value_str(getattr(facts, name)))
            for name in rule.trigger_fields
            if len(rule.trigger_fields) == 1 or getattr(facts, name) is True
        )
        findings.append(
            HarmFinding(
                category=rule.category,
                harm=rule.harm,
                rationale=rule.rationale,
                fired_fields=fired,
                evidence={n: facts.evidence_snippets[n] for n, _ in fired
                          if n in facts.evidence_snippets},
            )
        )
    return findings


def findings_by_category(facts: ExtractedFacts) -> dict[str, list[HarmFinding]]:
    """All five categories, in order, each with its findings (possibly empty)."""
    grouped: dict[str, list[HarmFinding]] = {c: [] for c in HARM_CATEGORIES}
    for finding in harm_findings(facts):
        grouped[finding.category].append(finding)
    return grouped


# --- Affected parties -------------------------------------------------------------------

@dataclass(frozen=True)
class AffectedParty:
    party: str
    reason: str  # the fact that identifies them, e.g. "deployment_domain=hiring"


DOMAIN_PARTIES: dict[D, str] = {
    D.HIRING: "Job applicants and employees",
    D.ESSENTIAL_SERVICES: "People applying for credit, insurance, public benefits or emergency services",
    D.LAW_ENFORCEMENT: "Suspects, defendants and members of the public in contact with police",
    D.BIOMETRIC_ID: "People whose face or other biometric data is captured, including bystanders",
    D.EDUCATION: "Students and learners (often minors) and their families",
    D.CONTENT_MODERATION: "Users and creators whose content is ranked, removed or recommended",
    D.CRITICAL_INFRASTRUCTURE: "People who depend on the infrastructure service",
    D.MIGRATION_ASYLUM_BORDER: "Migrants, asylum seekers and travellers",
    D.GENERAL_CONSUMER: "End users of the product",
}
NOT_DETERMINABLE = "Not determinable from documentation"


def affected_parties(facts: ExtractedFacts) -> list[AffectedParty]:
    """Who the system affects, from the domain, the stated population and capabilities."""
    parties = []
    if facts.deployment_domain in DOMAIN_PARTIES:
        parties.append(AffectedParty(DOMAIN_PARTIES[facts.deployment_domain],
                                     f"deployment_domain={facts.deployment_domain.value}"))
    if facts.affected_population == AffectedPopulation.VULNERABLE_GROUPS:
        parties.append(AffectedParty(
            "Vulnerable groups named in the documentation (children, patients, job seekers, "
            "asylum seekers, elderly people or persons with disabilities)",
            "affected_population=vulnerable_groups"))
    if facts.impersonation_capable:
        parties.append(AffectedParty(
            "People whose face or voice can be reproduced, and anyone deceived by the result",
            "impersonation_capable=true"))
    elif facts.generates_synthetic_media:
        parties.append(AffectedParty(
            "People who encounter the generated content and may take it for real",
            "generates_synthetic_media=true"))
    if facts.real_time_biometric_public:
        parties.append(AffectedParty("Everyone passing through the monitored public spaces",
                                     "real_time_biometric_public=true"))
    if facts.military_defence_use:
        parties.append(AffectedParty("People in the area of operations, including civilians",
                                     "military_defence_use=true"))
    if not parties:
        parties.append(AffectedParty(
            f"{NOT_DETERMINABLE}: no application domain or affected group is stated",
            "deployment_domain=other"))
    return parties


# --- Pointers to other tabs -------------------------------------------------------------

@dataclass(frozen=True)
class TabPointer:
    tab: int
    text: str


def related_tabs(facts: ExtractedFacts, tier: RiskTier) -> list[TabPointer]:
    """Plain-text pointers to other tabs (st.tabs can't be switched programmatically)."""
    pointers = []
    if tier == RiskTier.HIGH_RISK:
        pointers.append(TabPointer(
            2, "High-risk systems must use training, validation and testing data examined "
               "for possible biases and sufficiently representative (EU AI Act Art. 10(2)(f)–(g) "
               "and 10(3)). Check a dataset in Tab 2 · Dataset Bias."))
    if facts.generates_synthetic_media:
        pointers.append(TabPointer(
            3, "The system generates synthetic media: see Tab 3 · Synthetic Media for "
               "transparency duties (Art. 50) and misuse risks."))
    if facts.target_type in PROXY_PRONE_TARGETS:
        pointers.append(TabPointer(
            4, f"The system predicts a proxy target ({facts.target_type.value}): see "
               "Tab 4 · Proxy Audit for what the proxy can hide."))
    return pointers
