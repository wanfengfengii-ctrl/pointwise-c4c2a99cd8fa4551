from dataclasses import dataclass
from fractions import Fraction

from record.measurements import MeasurementOccurrence, SourceRef
from review.request import ReviewRequest


@dataclass(frozen=True)
class ReferenceOrigin:
    kind: str
    channel_id: str
    occurrence_id: str | None = None
    source: SourceRef | None = None


@dataclass(frozen=True)
class ReferenceState:
    value: Fraction
    origin: ReferenceOrigin


def initial_reference_state(request: ReviewRequest):
    return {channel: ReferenceState(value, ReferenceOrigin('initial', channel))
            for channel, value in request.initial_references}


def advance_reference(state: ReferenceState, occurrence: MeasurementOccurrence):
    if state.origin.channel_id != occurrence.channel_id or occurrence.supplement is None:
        raise ValueError('reference can advance only with a supplement from its own channel')
    supplement = occurrence.supplement
    return ReferenceState(supplement.value, ReferenceOrigin(
        'supplement', occurrence.channel_id, occurrence.occurrence_id, supplement.source,
    ))


def reference_is_determined(state):
    return isinstance(state, ReferenceState)
