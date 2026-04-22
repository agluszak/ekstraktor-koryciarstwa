from __future__ import annotations

from dataclasses import dataclass

from pipeline.domain_types import RoleKind, RoleModifier
from pipeline.models import ParsedWord
from pipeline.utils import normalize_entity_name


@dataclass(frozen=True, slots=True)
class RoleMatch:
    role_kind: RoleKind
    role_modifier: RoleModifier | None
    start: int
    end: int
    word_indices: frozenset[int]

    @property
    def canonical_name(self) -> str:
        base_name = normalize_entity_name(self.role_kind.value)
        if self.role_modifier is None:
            return base_name
        return f"{self.role_modifier.value} {base_name}"


@dataclass(frozen=True, slots=True)
class LemmaRolePattern:
    lemmas: tuple[str, ...]
    role_kind: RoleKind
    role_modifier: RoleModifier | None = None


ROLE_LEMMA_PATTERNS: tuple[LemmaRolePattern, ...] = (
    LemmaRolePattern(
        ("wiceprzewodniczący", "rada", "nadzorczy"),
        RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
        RoleModifier.DEPUTY,
    ),
    LemmaRolePattern(
        ("przewodniczący", "rada", "nadzorczy"),
        RoleKind.PRZEWODNICZACY_RADY_NADZORCZEJ,
    ),
    LemmaRolePattern(("zastępca", "prezes"), RoleKind.PREZES, RoleModifier.DEPUTY),
    LemmaRolePattern(("zastępczyni", "prezes"), RoleKind.PREZES, RoleModifier.DEPUTY),
    LemmaRolePattern(("członek", "zarząd"), RoleKind.CZLONEK_ZARZADU),
    LemmaRolePattern(("rada", "nadzorczy"), RoleKind.RADA_NADZORCZA),
    LemmaRolePattern(("prezydent", "miasto"), RoleKind.PREZYDENT_MIASTA),
    LemmaRolePattern(("sekretarz", "powiat"), RoleKind.SEKRETARZ_POWIATU),
    LemmaRolePattern(("marszałek", "województwo"), RoleKind.MARSZALEK_WOJEWODZTWA),
    LemmaRolePattern(("wiceprezes",), RoleKind.PREZES, RoleModifier.DEPUTY),
    LemmaRolePattern(("wiceprezeska",), RoleKind.PREZES, RoleModifier.DEPUTY),
    LemmaRolePattern(("prezes",), RoleKind.PREZES),
    LemmaRolePattern(("prezeska",), RoleKind.PREZES),
    LemmaRolePattern(("dyrektor",), RoleKind.DYREKTOR),
    LemmaRolePattern(("dyrektorka",), RoleKind.DYREKTOR),
    LemmaRolePattern(("wiceminister",), RoleKind.MINISTER, RoleModifier.DEPUTY),
    LemmaRolePattern(("minister",), RoleKind.MINISTER),
    LemmaRolePattern(("radny",), RoleKind.RADNY),
    LemmaRolePattern(("radna",), RoleKind.RADNY),
    LemmaRolePattern(("poseł",), RoleKind.POSEL),
    LemmaRolePattern(("posłanka",), RoleKind.POSEL),
    LemmaRolePattern(("senator",), RoleKind.SENATOR),
    LemmaRolePattern(("senatorka",), RoleKind.SENATOR),
    LemmaRolePattern(("wicewojewoda",), RoleKind.WOJEWODA, RoleModifier.DEPUTY),
    LemmaRolePattern(("wojewoda",), RoleKind.WOJEWODA),
    LemmaRolePattern(("wójt",), RoleKind.WOJT),
    LemmaRolePattern(("wojt",), RoleKind.WOJT),
    LemmaRolePattern(("starosta",), RoleKind.STAROSTA),
)


def match_role_mentions(parsed_words: list[ParsedWord]) -> list[RoleMatch]:
    raw_matches = _raw_role_matches(parsed_words)
    selected: list[RoleMatch] = []
    occupied_indices: set[int] = set()

    for match in sorted(
        raw_matches,
        key=lambda item: (item.end - item.start, -item.start),
        reverse=True,
    ):
        if occupied_indices.intersection(match.word_indices):
            continue
        selected.append(match)
        occupied_indices.update(match.word_indices)

    return sorted(selected, key=lambda item: item.start)


def has_copular_role_appointment(parsed_words: list[ParsedWord]) -> bool:
    role_word_indices = {
        word.index
        for match in match_role_mentions(parsed_words)
        for word_index in match.word_indices
        for word in parsed_words
        if word.index == word_index
    }
    if not role_word_indices:
        return False
    return any(
        word.lemma.casefold() == "zostać"
        and (
            word.deprel.casefold().startswith(("aux", "cop", "root", "xcomp"))
            or (
                word.head in role_word_indices and word.deprel.casefold().startswith(("aux", "cop"))
            )
        )
        for word in parsed_words
    )


def has_governance_verb_with_role(
    parsed_words: list[ParsedWord], trigger_lemmas: frozenset[str]
) -> bool:
    role_matches = match_role_mentions(parsed_words)
    role_word_indices = {
        word.index
        for match in role_matches
        for word_index in match.word_indices
        for word in parsed_words
        if word.index == word_index
    }
    if not role_word_indices:
        return False

    for word in parsed_words:
        if word.lemma.casefold() in trigger_lemmas:
            # 1. Direct children (obj, iobj, xcomp, obl)
            children = [c for c in parsed_words if c.head == word.index]
            if any(
                c.deprel.casefold() in {"obj", "iobj", "xcomp", "obl"}
                and c.index in role_word_indices
                for c in children
            ):
                return True

            # 2. Deep traversal (depth 2) for phrasings like "objął funkcję wiceprezesa"
            # Intermediate nouns: funkcja, stanowisko, fotel, posada, miejsce
            intermediate_nouns = {"funkcja", "stanowisko", "fotel", "posada", "miejsce"}
            for child in children:
                if (
                    child.deprel.casefold() in {"obj", "iobj", "xcomp", "obl"}
                    and child.lemma.casefold() in intermediate_nouns
                ):
                    grandchildren = [gc for gc in parsed_words if gc.head == child.index]
                    if any(
                        gc.deprel.casefold() in {"nmod", "appos", "flat"}
                        and gc.index in role_word_indices
                        for gc in grandchildren
                    ):
                        return True

            # 3. Linear proximity fallback: if governance verb and role are close together
            # in the same clause (roughly, not separated by other verbs)
            verb_pos = word.index
            for role_match in role_matches:
                # Get indices of words in this role match
                match_indices = sorted(list(role_match.word_indices))
                # Check distance from verb to closest token of role match
                dist = min(abs(verb_pos - i) for i in match_indices)
                if dist <= 4:
                    return True

    return False


def _raw_role_matches(parsed_words: list[ParsedWord]) -> list[RoleMatch]:
    lemmas = tuple(_normalized_lemma(word) for word in parsed_words)
    matches: list[RoleMatch] = []
    for start_index in range(len(parsed_words)):
        for pattern in ROLE_LEMMA_PATTERNS:
            end_index = start_index + len(pattern.lemmas)
            if lemmas[start_index:end_index] != pattern.lemmas:
                continue
            words = parsed_words[start_index:end_index]
            matches.append(
                RoleMatch(
                    role_kind=pattern.role_kind,
                    role_modifier=pattern.role_modifier,
                    start=words[0].start,
                    end=words[-1].end,
                    word_indices=frozenset(word.index for word in words),
                )
            )
    return matches


def _normalized_lemma(word: ParsedWord) -> str:
    return word.lemma.casefold() if word.lemma else word.text.casefold()
