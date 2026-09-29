"""Tab 3 · Synthetic Media (Experiment 3): capabilities, AI Act transparency duties,
a misuse-vulnerability matrix and a rule-generated ethical analysis.

Everything is a deterministic mapping from extracted facts. Article text verified
against the Official Journal text of Regulation (EU) 2024/1689:
- Art. 50(2): providers of AI systems generating synthetic audio, image, video or text
  content shall ensure outputs are marked in a machine-readable format and detectable
  as artificially generated or manipulated (exceptions: assistive function for
  standard editing, not substantially altering the input, law-enforcement use).
- Art. 50(4), first subparagraph: deployers of a system generating or manipulating
  image, audio or video content constituting a deep fake shall disclose that it is
  artificial (exceptions: law-enforcement use; evidently artistic, creative, satirical
  or fictional works only need an appropriate disclosure of its existence).
- Art. 50(4), second subparagraph: deployers of a system generating or manipulating
  text published to inform the public on matters of public interest shall disclose it
  (exceptions: law-enforcement use; human review or editorial control with editorial
  responsibility).
- Art. 3(60): 'deep fake' = AI-generated or manipulated image, audio or video content
  that resembles existing persons, objects, places, entities or events and would
  falsely appear to a person to be authentic or truthful.
- Art. 113: Art. 50 applies from 2 August 2026.
"""
from dataclasses import dataclass

from schema import ExtractedFacts, SyntheticMediaType as M

PROJECT_HEURISTIC = "project heuristic, not derived from a specific Act provision"
AV_TYPES = frozenset({M.IMAGE, M.AUDIO, M.VIDEO})


# --- Capabilities -------------------------------------------------------------------------

@dataclass(frozen=True)
class Capability:
    name: str
    field: str
    present: bool
    value: str
    evidence: str | None


def capabilities(facts: ExtractedFacts) -> list[Capability]:
    ev = facts.evidence_snippets
    types = ", ".join(t.value for t in facts.synthetic_media_types) or "none stated"
    return [
        Capability("Generates synthetic media", "generates_synthetic_media",
                   facts.generates_synthetic_media, str(facts.generates_synthetic_media).lower(),
                   ev.get("generates_synthetic_media")),
        Capability("Media types", "synthetic_media_types", bool(facts.synthetic_media_types), types,
                   ev.get("synthetic_media_types")),
        Capability("Can impersonate a real person's face or voice", "impersonation_capable",
                   facts.impersonation_capable, str(facts.impersonation_capable).lower(),
                   ev.get("impersonation_capable")),
    ]


# --- Transparency obligations (Art. 50) ------------------------------------------------------

APPLIES = "Applies"
MAY_APPLY = "May apply"
NOT_APPLICABLE = "Does not apply"


@dataclass(frozen=True)
class Obligation:
    provision: str
    duty_holder: str  # "Provider" | "Deployer"
    duty: str
    status: str  # APPLIES | MAY_APPLY | NOT_APPLICABLE
    reason: str
    documentation: str  # what the documentation shows
    exceptions: str  # stated, not modelled
    citation_verified: bool = True


def transparency_obligations(facts: ExtractedFacts) -> list[Obligation]:
    types = set(facts.synthetic_media_types)
    generates = facts.generates_synthetic_media or bool(types)
    marked = facts.output_marking_mentioned
    marking_doc = ("The documentation mentions watermarking, labelling or provenance of outputs."
                   if marked else
                   "The documentation doesn't mention marking outputs as AI-generated.")
    av = sorted(t.value for t in types & AV_TYPES)

    art50_2 = Obligation(
        "EU AI Act Art. 50(2)", "Provider",
        "Mark outputs in a machine-readable format so they are detectable as artificially "
        "generated or manipulated.",
        APPLIES if generates else NOT_APPLICABLE,
        ("The system generates synthetic content"
         + (f" ({', '.join(t.value for t in facts.synthetic_media_types)})" if types else "") + "."
         if generates else "No synthetic-content generation was extracted."),
        marking_doc if generates else "—",
        "Not modelled: assistive functions for standard editing, output that doesn't "
        "substantially alter the input, and uses authorised by law to fight crime.",
    )

    if av and facts.impersonation_capable:
        status, reason = APPLIES, (
            f"It generates or manipulates {', '.join(av)} and can reproduce real people, so "
            "its output can be a deep fake (Art. 3(60)); deployers who publish such content "
            "must disclose it.")
    elif av:
        status, reason = MAY_APPLY, (
            f"It generates or manipulates {', '.join(av)}; content that resembles real persons, "
            "places or events and would falsely appear authentic is a deep fake (Art. 3(60)).")
    else:
        status, reason = NOT_APPLICABLE, "No image, audio or video generation was extracted."
    art50_4a = Obligation(
        "EU AI Act Art. 50(4), first subparagraph", "Deployer",
        "Disclose that deep-fake image, audio or video content has been artificially "
        "generated or manipulated.",
        status, reason,
        ("Deployer disclosure is outside the provider's README; "
         + ("consent or usage-policy safeguards are mentioned." if facts.consent_safeguards_mentioned
            else "no consent or usage-policy safeguards are mentioned."))
        if status != NOT_APPLICABLE else "—",
        "Not modelled: uses authorised by law to fight crime; for evidently artistic, "
        "creative, satirical or fictional work the duty is limited to an appropriate "
        "disclosure that doesn't hamper the work.",
    )

    art50_4b = Obligation(
        "EU AI Act Art. 50(4), second subparagraph", "Deployer",
        "Disclose that text published to inform the public on matters of public interest "
        "has been artificially generated or manipulated.",
        MAY_APPLY if M.TEXT in types else NOT_APPLICABLE,
        ("It generates text; the duty applies when deployers publish it to inform the "
         "public on matters of public interest." if M.TEXT in types
         else "No text generation was extracted."),
        "Depends on how deployers publish the text." if M.TEXT in types else "—",
        "Not modelled: uses authorised by law to fight crime; text that has undergone human "
        "review or editorial control with a person holding editorial responsibility.",
    )
    return [art50_2, art50_4a, art50_4b]


OBLIGATIONS_NOTE = (
    "Simplified: the Art. 50 exceptions are listed but not modelled, deployer duties depend "
    "on how the system is used (which a README rarely shows), and Art. 50 applies from "
    "2 August 2026 (Art. 113)."
)


# --- Misuse vulnerability matrix (project heuristic) --------------------------------------------

LOW, MEDIUM, HIGH = "Low", "Medium", "High"

# Capability row -> score with 0, 1 or 2 distinct safeguard facts documented
# (output marking; consent / identity checks / usage policy).
MISUSE_SCORING: dict[str, tuple[str, str, str]] = {
    "Impersonation of a real person": (HIGH, HIGH, MEDIUM),
    "Synthetic video": (HIGH, MEDIUM, LOW),
    "Synthetic audio": (HIGH, MEDIUM, LOW),
    "Synthetic images": (MEDIUM, MEDIUM, LOW),
    "Synthetic text": (MEDIUM, LOW, LOW),
    "Synthetic content (type not stated)": (MEDIUM, MEDIUM, LOW),
}
SAFEGUARD_COLUMNS = ("Output marking", "Consent / identity checks", "Usage policy")
SAFEGUARD_NOTE = (
    "“Consent / identity checks” and “Usage policy” both come from one extracted fact, "
    "consent_safeguards_mentioned, so they always agree; together they count as one "
    "documented safeguard."
)
_RANK = {LOW: 0, MEDIUM: 1, HIGH: 2}


@dataclass(frozen=True)
class MisuseRow:
    capability: str
    safeguards: tuple[bool, bool, bool]  # per SAFEGUARD_COLUMNS
    documented: int  # distinct safeguard facts: 0, 1 or 2
    score: str


@dataclass(frozen=True)
class MisuseMatrix:
    rows: list[MisuseRow]
    overall: str | None  # highest row score; None when there is no capability


def misuse_matrix(facts: ExtractedFacts) -> MisuseMatrix:
    types = set(facts.synthetic_media_types)
    caps = []
    if facts.impersonation_capable:
        caps.append("Impersonation of a real person")
    caps += [label for t, label in ((M.VIDEO, "Synthetic video"), (M.AUDIO, "Synthetic audio"),
                                    (M.IMAGE, "Synthetic images"), (M.TEXT, "Synthetic text"))
             if t in types]
    if facts.generates_synthetic_media and not types:
        caps.append("Synthetic content (type not stated)")
    marking, consent = facts.output_marking_mentioned, facts.consent_safeguards_mentioned
    documented = int(marking) + int(consent)
    rows = [MisuseRow(c, (marking, consent, consent), documented, MISUSE_SCORING[c][documented])
            for c in caps]
    overall = max((r.score for r in rows), key=_RANK.get) if rows else None
    return MisuseMatrix(rows, overall)


# --- Ethical analysis (rule-generated text) -----------------------------------------------------

def ethical_analysis(facts: ExtractedFacts) -> list[tuple[str, str]]:
    """(theme, sentence) pairs, each produced by a fixed rule from the capabilities."""
    types = set(facts.synthetic_media_types)
    generates = facts.generates_synthetic_media or bool(types)
    if not generates and not facts.impersonation_capable:
        return [("Scope", "No synthetic-media capability was extracted, so deepfake-specific "
                          "risks don't arise from the documented functions.")]
    out = []
    if facts.impersonation_capable:
        out.append(("Consent", "Reproducing a real person's face or voice uses their identity; "
                    "doing so ethically needs that person's informed consent. The documentation "
                    + ("mentions consent, identity-verification or usage-policy safeguards."
                       if facts.consent_safeguards_mentioned else
                       "doesn't mention any consent, identity-verification or usage-policy safeguard.")))
    if facts.impersonation_capable and M.AUDIO in types:
        out.append(("Impersonation and fraud", "Cloned voices have been used to impersonate "
                    "relatives and executives in phone scams; anyone with a short recording of a "
                    "person's voice becomes a potential target."))
    if facts.impersonation_capable and (M.VIDEO in types or M.IMAGE in types):
        out.append(("Impersonation and fraud", "Face-swapped images or video can put real people "
                    "into scenes they were never in, from fake video calls used for fraud "
                    "(see the Case Library, Tab 8) to non-consensual intimate imagery."))
    if types & AV_TYPES:
        out.append(("Misinformation", "Realistic synthetic images, audio or video can be passed "
                    "off as evidence of events that never happened, and make genuine evidence "
                    "easier to dismiss as fake."))
    if M.TEXT in types:
        out.append(("Misinformation", "Generated text can produce convincing misleading "
                    "content at scale, for example fake reviews or news-like articles."))
    out.append(("Transparency", "The documentation mentions marking generated output, which "
                "helps viewers and platforms recognise it." if facts.output_marking_mentioned else
                "Without marking, people who later see the output can't tell it was generated."))
    return out
