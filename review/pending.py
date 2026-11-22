from dataclasses import dataclass

from record.measurements import MeasurementOccurrence
from review.references import ReferenceState


@dataclass(frozen=True)
class PendingState:
    channel_id: str
    missing_occurrence_id: str


def mark_pending(reference: ReferenceState, occurrence: MeasurementOccurrence):
    if reference.origin.channel_id != occurrence.channel_id or occurrence.supplement is not None:
        raise ValueError('pending must start at a missing supplement on the current channel')
    return PendingState(occurrence.channel_id, occurrence.occurrence_id)


def pending_applies_to_channel(state: PendingState, channel_id):
    return state.channel_id == channel_id


def propagate_pending(state: PendingState, occurrence: MeasurementOccurrence):
    if not pending_applies_to_channel(state, occurrence.channel_id):
        raise ValueError('pending state cannot propagate to a different channel')
    return state
