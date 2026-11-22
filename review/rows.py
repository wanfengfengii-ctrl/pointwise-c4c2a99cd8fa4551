from dataclasses import dataclass
from fractions import Fraction

from record.measurements import MeasurementOccurrence, ReadingCandidate, candidate_data, source_data
from review.pending import PendingState
from review.references import ReferenceState


def _reference_data(reference):
    if reference is None:
        return None
    origin = reference.origin
    return {
        'value': str(reference.value),
        'origin': {
            'kind': origin.kind,
            'channel_id': origin.channel_id,
            'occurrence_id': origin.occurrence_id,
            'source': None if origin.source is None else source_data(origin.source),
        },
    }


@dataclass(frozen=True)
class ReviewRow:
    occurrence: MeasurementOccurrence
    selected_kind: str | None
    selected: ReadingCandidate | None
    reference_before: ReferenceState | None
    reference_after: ReferenceState | None
    delta: Fraction | None
    pending: PendingState | None = None

    def as_data(self):
        occurrence = self.occurrence
        pending = None
        if self.pending is not None:
            missing = self.pending.missing_occurrence_id
            reason = 'missing_supplement' if missing == occurrence.occurrence_id else 'upstream_pending'
            pending = {'reason': reason, 'blocked_by': missing}
        return {
            'position': occurrence.position,
            'occurrence_id': occurrence.occurrence_id,
            'channel_id': occurrence.channel_id,
            'template_id': occurrence.template_id,
            'status': 'pending' if pending is not None else 'value',
            'original': candidate_data(occurrence.original),
            'selected_kind': self.selected_kind,
            'selected': candidate_data(self.selected),
            'reference_before': _reference_data(self.reference_before),
            'reference_after': _reference_data(self.reference_after),
            'delta': None if self.delta is None else str(self.delta),
            'pending': pending,
        }


def build_value_row(occurrence, kind, selected, before, after):
    return ReviewRow(occurrence, kind, selected, before, after, selected.value - before.value)


def build_pending_row(occurrence, pending, before=None):
    return ReviewRow(occurrence, None, None, before, None, None, pending)
