from dataclasses import dataclass
from typing import NewType

ListBlockId = NewType("ListBlockId", str)


@dataclass(frozen=True, slots=True)
class EvidenceScope:
    paragraph_index: int
    list_block_id: ListBlockId | None = None
    list_item_index: int | None = None


@dataclass(frozen=True, slots=True)
class ScopeCompatibilityPolicy:
    def _same_list_item_or_no_list_conflict(
        self,
        left: EvidenceScope,
        right: EvidenceScope,
    ) -> bool:
        if left.list_block_id is None and right.list_block_id is None:
            return True
        if left.list_block_id != right.list_block_id:
            return False
        if left.list_item_index is None or right.list_item_index is None:
            return True
        return left.list_item_index == right.list_item_index

    def _scope_allows(self, left: EvidenceScope, right: EvidenceScope) -> bool:
        if left.paragraph_index == right.paragraph_index:
            return self._same_list_item_or_no_list_conflict(left, right)

        if (
            left.list_block_id is not None
            or right.list_block_id is not None
            or left.list_item_index is not None
            or right.list_item_index is not None
        ):
            return False

        return True

    def scope_allows_window(self, anchor: EvidenceScope, evidence: EvidenceScope) -> bool:
        return self._scope_allows(anchor, evidence)

    def scope_allows_same_event(self, left: EvidenceScope, right: EvidenceScope) -> bool:
        return self._scope_allows(left, right)
