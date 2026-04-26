from __future__ import annotations

from dataclasses import dataclass

from pipeline.semantic_signals import (
    COMPLAINT_PATRONAGE_MARKERS,
    COMPLAINT_POWER_MARKERS,
    COMPLAINT_SPEAKER_MARKERS,
    matching_markers,
)

WHISTLEBLOWER_MARKERS = frozenset({"radna", "radny", "działacz", "działaczka"})
RECIPIENT_MARKERS = frozenset({"do premiera", "premiera", "premier"})


@dataclass(frozen=True, slots=True)
class PatronageComplaintSignal:
    patronage_markers: tuple[str, ...]
    power_markers: tuple[str, ...]


def detect_patronage_complaint(text: str) -> PatronageComplaintSignal | None:
    patronage_hits = tuple(matching_markers(text, COMPLAINT_PATRONAGE_MARKERS))
    power_hits = tuple(matching_markers(text, COMPLAINT_POWER_MARKERS))
    if not patronage_hits or not power_hits:
        return None
    return PatronageComplaintSignal(
        patronage_markers=patronage_hits,
        power_markers=power_hits,
    )


def has_speaker_markers(text: str) -> bool:
    return bool(matching_markers(text, COMPLAINT_SPEAKER_MARKERS))


def has_power_holder_markers(text: str) -> bool:
    return bool(matching_markers(text, COMPLAINT_POWER_MARKERS))


def has_whistleblower_markers(text: str) -> bool:
    return bool(matching_markers(text, WHISTLEBLOWER_MARKERS))


def has_complaint_recipient_markers(text: str) -> bool:
    return bool(matching_markers(text, RECIPIENT_MARKERS))
