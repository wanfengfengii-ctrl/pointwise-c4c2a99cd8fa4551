from issue.manifest import PacketManifest
from review.pending import mark_pending, propagate_pending
from review.references import advance_reference, initial_reference_state, reference_is_determined
from review.request import ReviewRequest
from review.rows import build_pending_row, build_value_row


def select_candidate_for_occurrence(occurrence, reference, threshold):
    if abs(occurrence.original.value - reference.value) <= threshold:
        return 'original', occurrence.original
    if occurrence.supplement is not None:
        return 'supplement', occurrence.supplement
    return None


def replay_channel(occurrence, state, threshold):
    """Apply one occurrence to the state of its own channel."""
    if not reference_is_determined(state):
        pending = propagate_pending(state, occurrence)
        return build_pending_row(occurrence, pending), pending
    choice = select_candidate_for_occurrence(occurrence, state, threshold)
    if choice is None:
        pending = mark_pending(state, occurrence)
        return build_pending_row(occurrence, pending, state), pending
    kind, candidate = choice
    after = advance_reference(state, occurrence) if kind == 'supplement' else state
    return build_value_row(occurrence, kind, candidate, state, after), after


def replay_measurements(manifest: PacketManifest, request: ReviewRequest):
    states = initial_reference_state(request)
    rows = []
    for occurrence in manifest.occurrences:
        channel = occurrence.channel_id
        row, states[channel] = replay_channel(occurrence, states[channel], request.threshold)
        rows.append(row)
    return tuple(rows)
