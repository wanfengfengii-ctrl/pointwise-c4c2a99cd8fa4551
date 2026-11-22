from record.measurements import MeasurementSequence, Recording
from record.store import Draft, RecordStore
from record.validation import reject_duplicate_occurrence as reject_duplicate_occurrence
from record.validation import require_identifier, validate_recording, validate_sequence


def register_recording(store: RecordStore, recording_id, work_order, batch_id, instrument_id, channels):
    if isinstance(channels, (str, bytes)):
        raise ValueError('channels must be a sequence of names')
    recording = Recording(recording_id, work_order, batch_id, instrument_id, tuple(channels))
    validate_recording(recording)
    store.save_recording(recording)
    return recording


def accept_recording(store: RecordStore, recording_id, draft_id, occurrences):
    require_identifier(draft_id, 'draft id')
    recording = store.load_recording(recording_id)
    sequence = MeasurementSequence(recording.channels, tuple(occurrences))
    validate_sequence(sequence)
    draft = Draft(draft_id, recording, sequence)
    store.save_draft(draft)
    return draft


def append_occurrence(store: RecordStore, draft_id, occurrence):
    with store.write():
        draft = store.load_open_draft(draft_id)
        sequence = MeasurementSequence(draft.sequence.channels, draft.sequence.occurrences + (occurrence,))
        validate_sequence(sequence)
        store.replace_draft_sequence(draft_id, sequence)
    return Draft(draft_id, draft.recording, sequence)
