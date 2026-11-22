from record.measurements import MeasurementSequence
from record.store import FrozenRevision, RecordStore
from record.validation import validate_revision_shape


def freeze_revision(store: RecordStore, draft_id, revision_id):
    with store.write():
        draft = store.load_open_draft(draft_id)
        validate_revision_shape(draft.recording, revision_id, None, draft.sequence)
        revision = FrozenRevision(revision_id, draft.recording, None, draft.sequence)
        store.insert_revision(revision)
        store.mark_draft_frozen(draft_id, revision_id)
    return revision


def create_correction_revision(store: RecordStore, base_revision_id, revision_id, occurrences):
    with store.write():
        base = get_frozen_revision(store, base_revision_id)
        sequence = MeasurementSequence(base.recording.channels, tuple(occurrences))
        validate_revision_shape(base.recording, revision_id, base_revision_id, sequence)
        revision = FrozenRevision(revision_id, base.recording, base_revision_id, sequence)
        store.insert_revision(revision)
    return revision


def get_frozen_revision(store: RecordStore, revision_id):
    revision = store.load_revision(revision_id)
    validate_revision_shape(revision.recording, revision_id, revision.parent_revision_id, revision.sequence)
    return revision
