from dataclasses import dataclass
from hashlib import sha256
import json

from labdb import SQLiteStore
from record.measurements import MeasurementSequence, Recording, sequence_data, sequence_from_data


@dataclass(frozen=True)
class Draft:
    draft_id: str
    recording: Recording
    sequence: MeasurementSequence


@dataclass(frozen=True)
class FrozenRevision:
    revision_id: str
    recording: Recording
    parent_revision_id: str | None
    sequence: MeasurementSequence


def initialize_record_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS recordings (
        recording_id TEXT PRIMARY KEY, work_order TEXT NOT NULL, batch_id TEXT NOT NULL,
        instrument_id TEXT NOT NULL, channels TEXT NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS revisions (
        revision_id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
        parent_revision_id TEXT REFERENCES revisions(revision_id),
        snapshot TEXT NOT NULL, snapshot_digest TEXT NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS drafts (
        draft_id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
        snapshot TEXT NOT NULL, snapshot_digest TEXT NOT NULL,
        frozen_revision_id TEXT REFERENCES revisions(revision_id)
    )''')
    connection.execute('CREATE INDEX IF NOT EXISTS revision_parent ON revisions(parent_revision_id)')


def _snapshot(sequence):
    text = json.dumps(sequence_data(sequence), sort_keys=True, separators=(',', ':'))
    return text, sha256(text.encode('utf-8')).hexdigest()


def _load_snapshot(row):
    text = row['snapshot']
    if sha256(text.encode('utf-8')).hexdigest() != row['snapshot_digest']:
        raise ValueError('recording snapshot digest mismatch')
    return sequence_from_data(json.loads(text))


class RecordStore(SQLiteStore):
    def _initialize(self):
        initialize_record_schema(self.connection)

    def save_recording(self, recording):
        with self.write() as connection:
            if connection.execute('SELECT 1 FROM recordings WHERE recording_id = ?', (recording.recording_id,)).fetchone():
                raise ValueError(f'recording already exists: {recording.recording_id}')
            connection.execute('INSERT INTO recordings VALUES (?, ?, ?, ?, ?)', (
                recording.recording_id, recording.work_order, recording.batch_id,
                recording.instrument_id, json.dumps(recording.channels),
            ))

    def load_recording(self, recording_id):
        row = self.connection.execute('SELECT * FROM recordings WHERE recording_id = ?', (recording_id,)).fetchone()
        if row is None:
            raise KeyError(recording_id)
        return Recording(row['recording_id'], row['work_order'], row['batch_id'],
                         row['instrument_id'], tuple(json.loads(row['channels'])))

    def save_draft(self, draft):
        text, digest = _snapshot(draft.sequence)
        with self.write() as connection:
            if connection.execute('SELECT 1 FROM drafts WHERE draft_id = ?', (draft.draft_id,)).fetchone():
                raise ValueError(f'draft already exists: {draft.draft_id}')
            connection.execute('''INSERT INTO drafts(draft_id, recording_id, snapshot, snapshot_digest)
                                  VALUES (?, ?, ?, ?)''',
                               (draft.draft_id, draft.recording.recording_id, text, digest))

    def load_open_draft(self, draft_id):
        row = self.connection.execute('SELECT * FROM drafts WHERE draft_id = ?', (draft_id,)).fetchone()
        if row is None:
            raise KeyError(draft_id)
        if row['frozen_revision_id'] is not None:
            raise ValueError(f'draft already frozen: {draft_id}')
        return Draft(draft_id, self.load_recording(row['recording_id']), _load_snapshot(row))

    def replace_draft_sequence(self, draft_id, sequence):
        text, digest = _snapshot(sequence)
        result = self.connection.execute('''UPDATE drafts SET snapshot = ?, snapshot_digest = ?
                                            WHERE draft_id = ? AND frozen_revision_id IS NULL''',
                                         (text, digest, draft_id))
        if result.rowcount != 1:
            raise ValueError(f'draft is unavailable for editing: {draft_id}')

    def insert_revision(self, revision):
        existing = self.connection.execute('SELECT 1 FROM revisions WHERE revision_id = ?',
                                           (revision.revision_id,)).fetchone()
        if existing is not None:
            raise ValueError(f'revision already exists: {revision.revision_id}')
        text, digest = _snapshot(revision.sequence)
        self.connection.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)', (
            revision.revision_id, revision.recording.recording_id, revision.parent_revision_id, text, digest,
        ))

    def mark_draft_frozen(self, draft_id, revision_id):
        result = self.connection.execute('''UPDATE drafts SET frozen_revision_id = ?
                                            WHERE draft_id = ? AND frozen_revision_id IS NULL''',
                                         (revision_id, draft_id))
        if result.rowcount != 1:
            raise ValueError(f'draft is unavailable for freezing: {draft_id}')

    def load_revision(self, revision_id):
        row = self.connection.execute('SELECT * FROM revisions WHERE revision_id = ?', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return FrozenRevision(revision_id, self.load_recording(row['recording_id']),
                              row['parent_revision_id'], _load_snapshot(row))

    def revision_status(self, revision_id):
        row = self.connection.execute('''SELECT EXISTS (
            SELECT 1 FROM revisions AS successor WHERE successor.parent_revision_id = base.revision_id
        ) FROM revisions AS base WHERE base.revision_id = ?''', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return 'superseded' if row[0] else 'frozen'
