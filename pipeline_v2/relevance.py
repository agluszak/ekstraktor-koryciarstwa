from __future__ import annotations

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
    public_money_terms: tuple[str, ...]
    public_org_terms: tuple[str, ...]
    appointment_terms: tuple[str, ...]
    anti_corruption_terms: tuple[str, ...]
    negative_legal_terms: tuple[str, ...]


DEFAULT_RELEVANCE_PROFILE = RelevanceProfile(
    public_money_terms=(
        "dotacj",
        "umow",
        "kontrakt",
        "publiczne pieniądz",
        "zł",
        "zarobk",
        "pensj",
        "wynagrodzeni",
        "finansowani",
        "grant",
        "subwencj",
        "pieniądz",
        "środki publiczn",
        "kosztuje",
        "płacą",
        "wyłożyć",
        "milion",
        "tysiąc",
    ),
    public_org_terms=(
        "urząd",
        "ministerstw",
        "spółk",
        "fundacj",
        "rada",
        "zarząd",
        "prezes",
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
        "nepotyzm",
        "konflikt interesów",
        "korupcj",
        "łapówk",
        "kolesiostw",
        "układ",
        "synekur",
        "tłuste koty",
        "partyjn",
        "polityczn",
        "działacz",
        "powiązani",
        "koalicj",
        "znajom",
        "rodzin",
        "partnerk",
    ),
    negative_legal_terms=(
        "trybunał konstytucyjny",
        "sąd pracy",
        "analiza prawna",
        "pozew",
        "sędzi",
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
        money_hits = matching_terms(text, self.profile.public_money_terms)
        org_hits = matching_terms(text, self.profile.public_org_terms)
        appointment_hits = matching_terms(text, self.profile.appointment_terms)
        anti_corruption_hits = matching_terms(text, self.profile.anti_corruption_terms)
        legal_hits = matching_terms(text, self.profile.negative_legal_terms)

        score = 0.0
        reasons: list[RelevanceSignal] = []
        if money_hits:
            score += min(0.35, 0.15 * len(money_hits))
            reasons.append(PublicMoneyRelevanceSignal())
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
            for hits in (money_hits, org_hits, appointment_hits, anti_corruption_hits)
        )
        if hits_by_category >= 3:
            score += 0.25
            reasons.append(StrongCombinedRelevanceSignal())
        elif hits_by_category >= 2:
            score += 0.1
            reasons.append(CombinedRelevanceSignal())

        if legal_hits and not (anti_corruption_hits or appointment_hits):
            score = min(score, 0.2)
            reasons.append(LegalNegativeRelevanceSignal())

        normalized_score = round(min(score, 1.0), 3)
        return RelevanceDecision(
            is_relevant=normalized_score >= 0.4,
            score=normalized_score,
            reasons=tuple(reasons) or (NoRelevanceIndicatorsSignal(),),
        )


def matching_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if term.casefold() in text)
