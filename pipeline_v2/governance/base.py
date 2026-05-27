from __future__ import annotations

from pipeline_v2.governance.constants import (
    APPOINTMENT_LEMMAS,
    CURRENT_DESCRIPTOR_LEMMAS,
    DASH_CHARS,
    DISMISSAL_LEMMAS,
    EXCEPTION_CLAUSE_LEMMAS,
    FORMER_DESCRIPTOR_LEMMAS,
    GENERIC_APPOINTMENT_LEMMAS,
    GOVERNANCE_ROLE_LEMMAS,
    HOLDING_LEMMAS,
    OBJAC_APPOINTMENT_LEMMAS,
    ORG_LIKE_PERSON_HINT_TOKENS,
    PERSON_DESCRIPTOR_LEMMAS,
    POLITICAL_ROLE_LEMMAS,
    ROLE_TITLE_ONLY_PERSON_LEMMAS,
    SINGULAR_PERSON_ROLE_LEMMAS,
    SUCCESSOR_NOUN_LEMMAS,
    TEMPORAL_PREPOSITIONS,
    VERB_LIKE_POS,
)
from pipeline_v2.ids import ProducerId


class GovernanceBase:
    producer_id = ProducerId("governance_candidate_stage_v2")
    _org_like_person_hint_tokens = ORG_LIKE_PERSON_HINT_TOKENS
    _person_descriptor_lemmas = PERSON_DESCRIPTOR_LEMMAS
    _appointment_lemmas = APPOINTMENT_LEMMAS
    _holding_lemmas = HOLDING_LEMMAS
    _former_descriptor_lemmas = FORMER_DESCRIPTOR_LEMMAS
    _generic_appointment_lemmas = GENERIC_APPOINTMENT_LEMMAS
    _objac_appointment_lemmas = OBJAC_APPOINTMENT_LEMMAS
    _temporal_prepositions = TEMPORAL_PREPOSITIONS
    _successor_noun_lemmas = SUCCESSOR_NOUN_LEMMAS
    _current_descriptor_lemmas = CURRENT_DESCRIPTOR_LEMMAS
    _dash_chars = DASH_CHARS
    _exception_clause_lemmas = EXCEPTION_CLAUSE_LEMMAS
    _dismissal_lemmas = DISMISSAL_LEMMAS
    _governance_role_lemmas = GOVERNANCE_ROLE_LEMMAS
    _political_role_lemmas = POLITICAL_ROLE_LEMMAS
    _verb_like_pos = VERB_LIKE_POS
    _role_title_only_person_lemmas = ROLE_TITLE_ONLY_PERSON_LEMMAS
    _singular_person_role_lemmas = SINGULAR_PERSON_ROLE_LEMMAS
