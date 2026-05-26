from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument, RelevanceDecision
from pipeline_v2.types import (
    AntiCorruptionRelevanceSignal,
    AppointmentRelevanceSignal,
    CombinedRelevanceSignal,
    LegalNegativeRelevanceSignal,
    NoRelevanceIndicatorsSignal,
    PublicMoneyRelevanceSignal,
    PublicOrgRelevanceSignal,
    RelevanceSignal,
    StrongCombinedRelevanceSignal,
)


@dataclass(frozen=True, slots=True)
class RelevanceProfile:
    funding_terms: tuple[str, ...]
    compensation_terms: tuple[str, ...]
    public_org_terms: tuple[str, ...]
    appointment_terms: tuple[str, ...]
    anti_corruption_terms: tuple[str, ...]
    negative_legal_terms: tuple[str, ...]


DEFAULT_RELEVANCE_PROFILE = RelevanceProfile(
    funding_terms=(
        "dotacj",
        "umow",
        "kontrakt",
        "dofinansowani",
        "finansowani",
        "grant",
        "subwencj",
        "środki publiczn",
        "rezerwy budżetowej",
        "wyłożyć",
        "przekaza",
        "milion",
        "tysiąc",
    ),
    compensation_terms=(
        "zarobk",
        "pensj",
        "wynagrodzeni",
        "odpraw",
        "premi",
        "kosztuje",
        "płacą",
        "zł",
    ),
    public_org_terms=(
        "urząd",
        "zakład",
        "ministerstw",
        "spółk",
        "fundacj",
        "rada",
        "radzie nadzorczej",
        "zarząd",
        "dyrektor",
        "ratusz",
        "starostw",
        "gmin",
        "powiat",
        "województw",
        "instytucj",
        "wodociąg",
        "elektrociepłowni",
        "energetyk",
        "państwow",
        "miejsk",
    ),
    appointment_terms=(
        "powoła",
        "nadzorcz",
        "zatrudni",
        "stanowisk",
        "nominacj",
        "posad",
        "funkcj",
        "rekrutacj",
        "konkurs",
        "kadrow",
        "obsad",
        "odwołan",
        "dymisj",
        "awans",
        "zatrudnieni",
    ),
    anti_corruption_terms=(
        "cba",
        "kontrol",
        "prokuratur",
        "nik",
        "zawiadomieni",
        "śledztw",
        "audyt",
        "nepotyzm",
        "konflikt interesów",
        "korupcj",
        "łapówk",
        "kolesiostw",
        "synekur",
    ),
    negative_legal_terms=(
        "trybunał konstytucyjny",
        "sąd pracy",
        "droga sądowa",
        "analiza prawna",
        "pozew",
        "sędzi",
        "orzeczenie",
        "sądu najwyższego",
        "skargę kasacyjną",
        "wyrok",
    ),
)


class ProfileRelevanceFilter:
    def __init__(self, profile: RelevanceProfile = DEFAULT_RELEVANCE_PROFILE) -> None:
        self.profile = profile

    def name(self) -> str:
        return "profile_relevance_filter_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        document.relevance = self.decide(document)
        return document

    def decide(self, document: ArticleDocument) -> RelevanceDecision:
        text = " ".join((document.title, document.cleaned_text)).casefold()
        funding_hits = matching_terms(text, self.profile.funding_terms)
        compensation_hits = matching_terms(text, self.profile.compensation_terms)
        org_hits = matching_terms(text, self.profile.public_org_terms)
        appointment_hits = matching_terms(text, self.profile.appointment_terms)
        anti_corruption_hits = matching_terms(text, self.profile.anti_corruption_terms)
        legal_hits = matching_terms(text, self.profile.negative_legal_terms)

        score = 0.0
        reasons: list[RelevanceSignal] = []
        if funding_hits or compensation_hits:
            reasons.append(PublicMoneyRelevanceSignal())
        if funding_hits:
            score += min(0.4, 0.12 * len(funding_hits))
        if compensation_hits:
            score += min(0.32, 0.1 * len(compensation_hits))
        if org_hits:
            score += min(0.3, 0.1 * len(org_hits))
            reasons.append(PublicOrgRelevanceSignal())
        if appointment_hits:
            score += min(0.3, 0.15 * len(appointment_hits))
            reasons.append(AppointmentRelevanceSignal())
        if anti_corruption_hits:
            score += min(0.35, 0.2 * len(anti_corruption_hits))
            reasons.append(AntiCorruptionRelevanceSignal())

        hits_by_category = sum(
            bool(hits)
            for hits in (
                funding_hits or compensation_hits,
                org_hits,
                appointment_hits,
                anti_corruption_hits,
            )
        )
        if hits_by_category >= 3:
            score += 0.25
            reasons.append(StrongCombinedRelevanceSignal())
        elif hits_by_category >= 2:
            score += 0.1
            reasons.append(CombinedRelevanceSignal())

        if legal_hits:
            reasons.append(LegalNegativeRelevanceSignal())
            score -= min(0.35, 0.08 * len(legal_hits))
            if not funding_hits and not anti_corruption_hits:
                score = min(score, 0.2)

        normalized_score = round(max(0.0, min(score, 1.0)), 3)
        return RelevanceDecision(
            is_relevant=normalized_score >= 0.4,
            score=normalized_score,
            reasons=tuple(reasons) or (NoRelevanceIndicatorsSignal(),),
        )


def matching_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    matches: list[str] = []
    for term in terms:
        if " " in term:
            pattern = rf"(?<!\w){re.escape(term.casefold())}(?!\w)"
        else:
            pattern = rf"(?<!\w){re.escape(term.casefold())}[\w-]*"
        if re.search(pattern, text):
            matches.append(term)
    return tuple(matches)
