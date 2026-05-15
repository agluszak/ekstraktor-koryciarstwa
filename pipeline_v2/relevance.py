from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.document import ArticleDocument, RelevanceDecision


@dataclass(frozen=True, slots=True)
class RelevanceProfile:
    public_money_terms: tuple[str, ...]
    public_org_terms: tuple[str, ...]
    appointment_terms: tuple[str, ...]
    anti_corruption_terms: tuple[str, ...]
    negative_legal_terms: tuple[str, ...]


DEFAULT_RELEVANCE_PROFILE = RelevanceProfile(
    public_money_terms=("dotacja", "umowa", "kontrakt", "publiczne pieniądze", "zł"),
    public_org_terms=("urząd", "ministerstwo", "spółka", "fundacja", "rada", "zarząd"),
    appointment_terms=("powołał", "powołana", "zatrudnił", "zatrudniona", "stanowisko"),
    anti_corruption_terms=("cba", "kontrola", "nepotyzm", "konflikt interesów"),
    negative_legal_terms=("trybunał konstytucyjny", "sąd pracy", "analiza prawna"),
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
        reasons: list[str] = []
        if money_hits:
            score += min(0.3, 0.12 * len(money_hits))
            reasons.append("public-money context")
        if org_hits:
            score += min(0.25, 0.08 * len(org_hits))
            reasons.append("public or organizational context")
        if appointment_hits:
            score += min(0.25, 0.12 * len(appointment_hits))
            reasons.append("appointment or employment context")
        if anti_corruption_hits:
            score += min(0.25, 0.15 * len(anti_corruption_hits))
            reasons.append("anti-corruption context")
        if (
            sum(
                bool(hits)
                for hits in (money_hits, org_hits, appointment_hits, anti_corruption_hits)
            )
            >= 3
        ):
            score += 0.18
            reasons.append("combined relevance context")
        if legal_hits and not (money_hits or appointment_hits or anti_corruption_hits):
            score = min(score, 0.2)
            reasons.append("legal-analysis negative context")

        normalized_score = round(min(score, 1.0), 3)
        return RelevanceDecision(
            is_relevant=normalized_score >= 0.45,
            score=normalized_score,
            reasons=tuple(reasons) or ("no relevance indicators found",),
        )


def matching_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if term.casefold() in text)
