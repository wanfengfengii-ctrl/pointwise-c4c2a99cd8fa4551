from dataclasses import replace
from fractions import Fraction
import json
import sqlite3

from issue.encode import compute_packet_digest
from lab import IssueRegistry, RecordStore, accept_recording, append_occurrence, create_correction_revision
from lab import freeze_revision, issue_packet, reissue_packet
from receive.decode import decode_packet
from record.measurements import MeasurementSequence, ReadingCandidate
from record.revisions import get_frozen_revision
from tests import LabCase, emit_scenario


class IssueTests(LabCase):
    def test_issue_preserves_occurrences(self):
        m1, m2, m3 = self.sequence.occurrences
        m3 = replace(m3, original=ReadingCandidate(Fraction(11), m3.original.source),
                     supplement=ReadingCandidate(Fraction(12), m3.supplement.source))
        sequence = MeasurementSequence(('A',), (m1, m2, m3))
        packet = self.issue_sample(sequence)
        body = json.loads(packet.payload)['manifest']
        columns = ['occurrence_id', 'position', 'channel_id', 'template_id', 'original', 'supplement']
        actual = [[row[column] for column in columns] for row in body['occurrences']]
        expected = [
            ['m1', 0, 'A', 'bridge', {'value': '7', 'source': {'artifact': 'run-17.raw', 'start': 0, 'end': 2}}, None],
            ['m2', 1, 'A', 'bridge', {'value': '11', 'source': {'artifact': 'run-17.raw', 'start': 2, 'end': 5}},
             {'value': '12', 'source': {'artifact': 'run-17.range', 'start': 0, 'end': 3}}],
            ['m3', 2, 'A', 'bridge', {'value': '11', 'source': {'artifact': 'run-17.raw', 'start': 5, 'end': 8}},
             {'value': '12', 'source': {'artifact': 'run-17.range', 'start': 3, 'end': 6}}],
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(packet.digest, compute_packet_digest(packet.payload))
        self.assertEqual(decode_packet(packet.payload, packet.digest, packet.outbound_id).manifest.occurrences,
                         sequence.occurrences)
        with IssueRegistry(self.outbound_path) as registry:
            replayed = reissue_packet(registry, packet.outbound_id)
            events = registry.connection.execute('SELECT outbound_id FROM reissues ORDER BY reissue_id').fetchall()
        self.assertEqual(replayed, packet)
        self.assertEqual([row[0] for row in events], [packet.outbound_id])
        downstream = {'same_packet': replayed == packet, 'recorded_reissues': len(events)}
        emit_scenario('V1', {'template': 'bridge', 'raw_mV': [7, 11, 11], 'supplement_mV': [None, 12, 12]},
                      expected, actual, {'same_packet': True, 'recorded_reissues': 1}, downstream,
                      ['issue/evidence.py', 'issue/encode.py', 'issue/registry.py', 'receive/decode.py'],
                      '逐次比对人工列出的原卷范围，重新领取后直接比较编码字节及登记记录。')

    def test_duplicate_occurrence_rejected(self):
        m1, m2, m3 = self.sequence.occurrences
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            base = self.freeze(source, self.sequence)
            with self.assertRaisesRegex(ValueError, 'duplicate occurrence') as rejection:
                create_correction_revision(source, base.revision_id, 'bad-r2',
                                           (m1, replace(m2, occurrence_id='m1'), m3))
            with self.assertRaises(KeyError):
                issue_packet(source, registry, 'bad-r2')
            self.assertEqual(source.revision_status(base.revision_id), 'frozen')
            packet = issue_packet(source, registry, base.revision_id)
        chosen_revision = json.loads(packet.payload)['manifest']['revision_id']
        self.assertEqual(chosen_revision, 'shift-17-r1')
        emit_scenario('V2', {'correction_ids': ['m1', 'm1', 'm3']}, 'duplicate occurrence',
                      str(rejection.exception).split(" '", 1)[0], 'shift-17-r1', chosen_revision,
                      ['record/validation.py', 'record/revisions.py', 'issue/selection.py'],
                      '人工检查两次出现的 m1，并从成功发行件读取仍可用的原修订编号。')

    def test_draft_append_validation_and_freeze_retry(self):
        m1, m2, _ = self.sequence.occurrences
        with RecordStore(self.source_path) as source:
            recording = self.register(source, self.sequence)
            accept_recording(source, recording.recording_id, 'draft', ())
            with self.assertRaisesRegex(ValueError, 'at least one occurrence'):
                freeze_revision(source, 'draft', 'r1')
            append_occurrence(source, 'draft', m1)
            invalid_rows = (
                (replace(m2, channel_id='missing'), 'unknown channel'),
                (replace(m2, position=8), 'original order'),
                (replace(m2, original=replace(m2.original, value=11.0)), 'Fraction'),
                (replace(m2, original=replace(m2.original, source=replace(m2.original.source, end=2))), 'source range'),
            )
            for invalid, detail in invalid_rows:
                with self.subTest(detail=detail), self.assertRaisesRegex(ValueError, detail):
                    append_occurrence(source, 'draft', invalid)
            with self.assertRaisesRegex(ValueError, 'duplicate occurrence'):
                append_occurrence(source, 'draft', replace(m2, occurrence_id=m1.occurrence_id))
            self.assertEqual(append_occurrence(source, 'draft', m2).sequence.occurrences, (m1, m2))
            revision = freeze_revision(source, 'draft', 'r1')
            self.assertEqual(revision.sequence.occurrences, (m1, m2))
            with self.assertRaisesRegex(ValueError, 'already frozen'):
                append_occurrence(source, 'draft', self.sequence.occurrences[2])
        with RecordStore(self.source_path) as source:
            self.assertEqual(get_frozen_revision(source, 'r1'), revision)

    def test_outbound_write_failure_preserves_old_packet(self):
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            base = self.freeze(source, self.sequence)
            old = issue_packet(source, registry, base.revision_id)
            successor = create_correction_revision(source, base.revision_id, 'r2', self.sequence.occurrences)
            registry.connection.execute('''CREATE TRIGGER stop_outbound BEFORE INSERT ON outbound_packets
                BEGIN SELECT RAISE(ABORT, 'outbound unavailable'); END''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'outbound unavailable'):
                issue_packet(source, registry, successor.revision_id)
            rows = registry.connection.execute('SELECT outbound_id FROM outbound_packets').fetchall()
            self.assertEqual([row[0] for row in rows], [old.outbound_id])
            self.assertEqual(reissue_packet(registry, old.outbound_id), old)
            with self.assertRaises(KeyError):
                reissue_packet(registry, 'missing')
            registry.connection.execute('DROP TRIGGER stop_outbound')
            new = issue_packet(source, registry, successor.revision_id)
            self.assertNotEqual(new.outbound_id, old.outbound_id)
