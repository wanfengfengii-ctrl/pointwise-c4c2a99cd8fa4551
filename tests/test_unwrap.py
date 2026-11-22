import json
import sqlite3
from hashlib import sha256

from lab import (IssueRegistry, PacketRejected, ReceiveStore, RecordStore, ReportCommitError, ReportStore,
                 issue_packet, issue_unwrap, read_receipt, read_report, receive_packet, reissue_packet,
                 sign_review, sign_unwrap)
from receive.inventory import list_acceptances
from tests import LabCase, emit_scenario
from unwrap_examples import EXAMPLES, freeze_example


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')


class UnwrapCase(LabCase):
    def freeze_named(self, source, name):
        return freeze_example(source, name)

    def issue_named(self, source, registry, name, *, max_step=None, positions=None):
        example = EXAMPLES[name]
        revision = self.freeze_named(source, name)
        return issue_unwrap(source, registry, revision.revision_id, example.channel, example.modulus,
                            example.bounds, example.max_step if max_step is None else max_step,
                            list(example.positions) if positions is None else list(positions))

    def deliver(self, registry, packet):
        return reissue_packet(registry, packet.outbound_id)


class UnwrapIssueTests(UnwrapCase):
    def test_manifest_shape_and_exact_joint_evidence(self):
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            packet = self.issue_named(source, registry, 'middle-five')
            replayed = self.deliver(registry, packet)
            self.assertEqual(replayed, packet)
        envelope = json.loads(packet.payload)
        self.assertEqual(envelope['version'], 2)
        manifest = envelope['manifest']
        self.assertEqual(manifest['kind'], 'unwrap')
        self.assertEqual(manifest['recording_id'], 'middle-five')
        self.assertEqual(manifest['revision_id'], 'middle-five-r1')
        self.assertEqual(manifest['channel'], 'A')
        self.assertEqual(manifest['modulus'], 10)
        self.assertEqual(manifest['bounds'], [0, 20])
        self.assertEqual(manifest['max_step'], 6)
        self.assertEqual(manifest['selected'], [
            {'position': 0, 'residue': 0,
             'source': {'artifact': 'middle-five-0.raw', 'start': 0, 'end': 2}},
            {'position': 2, 'residue': 0,
             'source': {'artifact': 'middle-five-2.raw', 'start': 0, 'end': 2}},
        ])
        expected_evidence = [[0, 0], [0, 10], [10, 0], [10, 10], [10, 20], [20, 10], [20, 20]]
        self.assertEqual(manifest['evidence'], expected_evidence)
        self.assertEqual(envelope['outbound_id'], 'OUT-' + sha256(wire(manifest)).hexdigest())
        self.assertEqual(envelope['content_digest'], sha256(wire(manifest)).hexdigest())
        self.assertEqual(sha256(packet.payload).hexdigest(), packet.digest)
        # unselected beats stay at the station: no per-beat residues in the packet.
        self.assertNotIn('occurrences', manifest)
        emit_scenario('U1', {'residues': [0, 5, 0], 'selected': [0, 2]}, expected_evidence,
                      manifest['evidence'], {'version': 2, 'kind': 'unwrap'},
                      {'version': envelope['version'], 'kind': manifest['kind']},
                      ['unwrap/tracks.py', 'issue/unwrap_issue.py', 'issue/encode.py'],
                      '手算三拍候选值并按相邻拍差不超过 6 枚举整轨，只投影两个选中位。')

    def test_hidden_prefix_and_step_limit_rejection(self):
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            packet = self.issue_named(source, registry, 'hidden-prefix')
            self.assertEqual(json.loads(packet.payload)['manifest']['evidence'], [[0]])
            with self.assertRaisesRegex(ValueError, 'no legal full track'):
                issue_unwrap(source, registry, 'hidden-prefix-r1', 'A', 10, (0, 10), 3, [1])

    def test_parameter_validation_and_boolean_rejection(self):
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            revision = self.freeze_named(source, 'middle-five')
            kwargs = dict(revision_id=revision.revision_id, channel='A', modulus=10,
                          bounds=(0, 20), max_step=6, positions=[0, 2])
            bad_kwargs = [
                ({'modulus': 0}, 'positive'),
                ({'modulus': True}, 'boolean'),
                ({'bounds': (20, 0)}, 'lo <= hi'),
                ({'bounds': [0]}, 'closed'),
                ({'bounds': (True, 20)}, 'boolean'),
                ({'max_step': -1}, 'nonnegative'),
                ({'max_step': False}, 'boolean'),
                ({'positions': []}, 'nonempty'),
                ({'positions': [0, 0]}, 'distinct'),
                ({'positions': [0, 7]}, 'do not belong'),
                ({'positions': [True, 2]}, 'boolean'),
                ({'channel': 'B'}, 'unknown channel'),
                ({'revision_id': 'missing-r9'}, 'missing-r9'),
            ]
            for changes, detail in bad_kwargs:
                merged = dict(kwargs)
                merged.update(changes)
                with self.subTest(detail=detail):
                    with self.assertRaises((ValueError, KeyError)):
                        issue_unwrap(source, registry, **merged)
            self.assertEqual(registry.connection.execute('SELECT COUNT(*) FROM outbound_packets').fetchone()[0], 0)

    def test_non_integer_residue_and_supplement_ignored(self):
        from fractions import Fraction
        from record.measurements import MeasurementOccurrence, ReadingCandidate, SourceRef
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            revision = self.freeze_named(source, 'middle-five')
            half = MeasurementOccurrence(
                'middle-five-m1', 1, 'A', 'bridge',
                ReadingCandidate(Fraction(5, 2), SourceRef('half.raw', 0, 2)),
                ReadingCandidate(Fraction(99), SourceRef('supp.raw', 0, 2)),
            )
            from record.revisions import create_correction_revision
            corrected = create_correction_revision(
                source, revision.revision_id, 'half-r2',
                (revision.sequence.occurrences[0], half, revision.sequence.occurrences[2]),
            )
            with self.assertRaisesRegex(ValueError, 'integer residues'):
                issue_unwrap(source, registry, corrected.revision_id, 'A', 10, (0, 20), 6, [0, 2])
            # supplements never participate; a fractional supplement on an integer original still issues.
            with_supplement = MeasurementOccurrence(
                'middle-five-m1', 1, 'A', 'bridge',
                ReadingCandidate(Fraction(5), SourceRef('middle-five-1.raw', 0, 2)),
                ReadingCandidate(Fraction(99, 2), SourceRef('supp.raw', 0, 2)),
            )
            revision2 = create_correction_revision(
                source, revision.revision_id, 'supp-r2',
                (revision.sequence.occurrences[0], with_supplement, revision.sequence.occurrences[2]),
            )
            packet = issue_unwrap(source, registry, revision2.revision_id, 'A', 10, (0, 20), 6, [0, 2])
            self.assertEqual(json.loads(packet.payload)['manifest']['evidence'],
                             [[0, 0], [0, 10], [10, 0], [10, 10], [10, 20], [20, 10], [20, 20]])

    def test_interleaved_channels_share_adjacency(self):
        from fractions import Fraction
        from record.measurements import MeasurementOccurrence, ReadingCandidate, SourceRef, MeasurementSequence
        with RecordStore(self.source_path) as source:
            from lab import register_recording, record_revision
            register_recording(source, 'interleave', 'w', 'b', 'i', ('A', 'B'))
            rows = (
                MeasurementOccurrence('a0', 0, 'A', 't', ReadingCandidate(Fraction(4), SourceRef('a0.raw', 0, 1))),
                MeasurementOccurrence('b0', 1, 'B', 't', ReadingCandidate(Fraction(0), SourceRef('b0.raw', 0, 1))),
                MeasurementOccurrence('a1', 2, 'A', 't', ReadingCandidate(Fraction(0), SourceRef('a1.raw', 0, 1))),
            )
            revision = record_revision(source, 'interleave', 'd1', 'interleave-r1', rows)
            with IssueRegistry(self.outbound_path) as registry:
                packet = issue_unwrap(source, registry, revision.revision_id, 'A', 10, (0, 10), 4, [2])
                self.assertEqual(json.loads(packet.payload)['manifest']['evidence'], [[0]])
                with self.assertRaisesRegex(ValueError, 'no legal full track'):
                    issue_unwrap(source, registry, revision.revision_id, 'A', 10, (0, 10), 3, [2])

    def test_reissue_is_byte_identical_and_recorded(self):
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            packet = self.issue_named(source, registry, 'middle-five')
            first = reissue_packet(registry, packet.outbound_id)
            second = reissue_packet(registry, packet.outbound_id)
            self.assertEqual((first, second), (packet, packet))
            count = registry.connection.execute('SELECT COUNT(*) FROM reissues').fetchone()[0]
            self.assertEqual(count, 2)

    def test_outbound_write_failure_leaves_no_new_packet(self):
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            old = self.issue_named(source, registry, 'middle-zero')
            registry.connection.execute('''CREATE TRIGGER stop_outbound BEFORE INSERT ON outbound_packets
                BEGIN SELECT RAISE(ABORT, 'outbound unavailable'); END''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'outbound unavailable'):
                self.issue_named(source, registry, 'middle-five')
            rows = registry.connection.execute('SELECT outbound_id FROM outbound_packets').fetchall()
            self.assertEqual([row[0] for row in rows], [old.outbound_id])


class UnwrapReceiveAndSignTests(UnwrapCase):
    def _deliveries(self, names):
        packets = {}
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            for name in names:
                packets[name] = self.issue_named(source, registry, name)
        return packets

    def test_same_sheet_different_verdicts_and_reopen(self):
        packets = self._deliveries(('middle-five', 'middle-zero'))
        report_ids = []
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            accepted_five = receive_packet(inventory, packets['middle-five'].payload,
                                           packets['middle-five'].digest, packets['middle-five'].outbound_id)
            accepted_zero = receive_packet(inventory, packets['middle-zero'].payload,
                                           packets['middle-zero'].digest, packets['middle-zero'].outbound_id)
            self.assertNotEqual(accepted_five.acceptance_id, accepted_zero.acceptance_id)
            sheet = {0: 0, 2: 10}
            five = sign_unwrap(inventory, reports, accepted_five.acceptance_id, sheet)
            zero = sign_unwrap(inventory, reports, accepted_zero.acceptance_id, sheet)
            report_ids = [five.receipt.report_id, zero.receipt.report_id]
            self.assertEqual(five.report['outcome'], 'consistent')
            self.assertEqual([(row['status'], row['value']) for row in five.report['rows']],
                             [('unique', 0), ('unique', 10)])
            self.assertEqual(five.report['request'],
                             {'kind': 'unwrap', 'acceptance_id': accepted_five.acceptance_id,
                              'anchors': [[0, 0], [2, 10]]})
            self.assertEqual(zero.report['outcome'], 'conflict')
            self.assertEqual(zero.report['rows'], [])
            for signed in (five, zero):
                self.assertEqual(signed.report['packet'], {
                    'outbound_id': packets['middle-five' if signed is five else 'middle-zero'].outbound_id,
                    'revision_id': signed.report['packet']['revision_id'],
                    'digest': signed.report['packet']['digest'],
                })
        # white-shift libraries are gone; reopen only the report library.
        self.source_path.unlink()
        self.outbound_path.unlink()
        with ReportStore(self.report_path) as reports:
            reloaded_five = read_report(reports, report_ids[0])
            reloaded_zero = read_receipt(reports, report_ids[1])
            self.assertEqual(reloaded_five.report['rows'], five.report['rows'])
            self.assertEqual(reloaded_zero, zero.receipt)
        emit_scenario('U2', {'sheet': {0: 0, 2: 10}, 'rolls': ['middle-five', 'middle-zero']},
                      {'five': 'consistent', 'zero': 'conflict'},
                      {'five': five.report['outcome'], 'zero': zero.report['outcome']},
                      {'reopen': True}, {'reopen': reloaded_five.report['outcome'] == 'consistent'},
                      ['unwrap/tracks.py', 'review/unwrap_engine.py', 'report/unwrap_publish.py'],
                      '同一张标定单分别投影到两卷的精确联合证据，重开只开报告库领取原签报。')

    def test_partial_and_empty_anchors(self):
        packets = self._deliveries(('middle-five', 'middle-zero', 'hidden-prefix'))
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            ids = {}
            for name, packet in packets.items():
                ids[name] = receive_packet(inventory, packet.payload, packet.digest,
                                           packet.outbound_id).acceptance_id
            five_partial = sign_unwrap(inventory, reports, ids['middle-five'], {0: 0})
            self.assertEqual([(row['status'], row['value']) for row in five_partial.report['rows']],
                             [('unique', 0), ('ambiguous', None)])
            zero_partial = sign_unwrap(inventory, reports, ids['middle-zero'], {0: 0})
            self.assertEqual([(row['status'], row['value']) for row in zero_partial.report['rows']],
                             [('unique', 0), ('unique', 0)])
            five_empty = sign_unwrap(inventory, reports, ids['middle-five'], {})
            self.assertEqual([row['status'] for row in five_empty.report['rows']], ['ambiguous', 'ambiguous'])
            zero_empty = sign_unwrap(inventory, reports, ids['middle-zero'], {})
            self.assertEqual([row['status'] for row in zero_empty.report['rows']], ['ambiguous', 'ambiguous'])
            hidden = sign_unwrap(inventory, reports, ids['hidden-prefix'], {})
            self.assertEqual(hidden.report['outcome'], 'consistent')
            self.assertEqual([(row['status'], row['value']) for row in hidden.report['rows']],
                             [('unique', 0)])
            conflict_tail = sign_unwrap(inventory, reports, ids['middle-five'], {0: 0, 2: 20})
            self.assertEqual(conflict_tail.report['outcome'], 'conflict')

    def test_repeat_request_returns_original_signed_report(self):
        packets = self._deliveries(('middle-five',))
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            acceptance = receive_packet(inventory, packets['middle-five'].payload,
                                        packets['middle-five'].digest, packets['middle-five'].outbound_id)
            first = sign_unwrap(inventory, reports, acceptance.acceptance_id, {0: 0, 2: 10})
            # equivalent anchors in a different order must be the same request
            second = sign_unwrap(inventory, reports, acceptance.acceptance_id, {2: 10, 0: 0})
            self.assertEqual(first, second)
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0], 1)
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
            # same packet accepted again gets a new acceptance id and its own report
            again = receive_packet(inventory, packets['middle-five'].payload,
                                   packets['middle-five'].digest, packets['middle-five'].outbound_id)
            self.assertNotEqual(again.acceptance_id, acceptance.acceptance_id)
            other = sign_unwrap(inventory, reports, again.acceptance_id, {0: 0, 2: 10})
            self.assertNotEqual(other.receipt, first.receipt)
            self.assertEqual(other.report['rows'], first.report['rows'])

    def test_anchor_validation(self):
        packets = self._deliveries(('middle-five',))
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            acceptance = receive_packet(inventory, packets['middle-five'].payload,
                                        packets['middle-five'].digest, packets['middle-five'].outbound_id)
            for anchors in ({1: 5}, {0: 21}, {0: -1}, {True: 0}, {0: True}, [('0', 0)]):
                with self.subTest(anchors=anchors):
                    with self.assertRaises(ValueError):
                        sign_unwrap(inventory, reports, acceptance.acceptance_id, anchors)
            with self.assertRaises(KeyError):
                sign_unwrap(inventory, reports, acceptance.acceptance_id + 99, {0: 0})
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0], 0)

    def test_entry_mixing_rejected(self):
        packets = self._deliveries(('middle-five',))
        from fractions import Fraction
        from record.measurements import MeasurementOccurrence, ReadingCandidate, SourceRef
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as v1_registry:
            # the V2 roll already used recording id 'middle-five'; register a separate V1 roll
            from lab import register_recording, record_revision
            register_recording(source, 'middle-five-v1', 'unwrap-check', 'steel-K4', 'wrap-meter', ('A',))
            occurrences = tuple(
                MeasurementOccurrence(
                    f"v1-m{position}", position, 'A', 'bridge',
                    ReadingCandidate(Fraction(residue), SourceRef(f"v1-{position}.raw", 0, 2)),
                )
                for position, residue in enumerate(EXAMPLES['middle-five'].residues)
            )
            v1_revision = record_revision(source, 'middle-five-v1', 'v1-draft', 'v1-r1', occurrences)
            v1_packet = issue_packet(source, v1_registry, v1_revision.revision_id)
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            v2_acceptance = receive_packet(inventory, packets['middle-five'].payload,
                                           packets['middle-five'].digest, packets['middle-five'].outbound_id)
            v1_acceptance = receive_packet(inventory, v1_packet.payload, v1_packet.digest, v1_packet.outbound_id)
            with self.assertRaisesRegex(ValueError, 'V1'):
                sign_review(inventory, reports, v2_acceptance.acceptance_id, {'A': 0}, 10)
            with self.assertRaisesRegex(ValueError, 'V2'):
                sign_unwrap(inventory, reports, v1_acceptance.acceptance_id, {})
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0], 0)

    def test_bad_v2_packets_are_rejected_with_no_acceptance(self):
        packet = self._deliveries(('middle-five',))['middle-five']
        envelope = json.loads(packet.payload)
        valid_manifest = envelope['manifest']

        def independent(manifest, version=2):
            content_digest = sha256(wire(manifest)).hexdigest()
            outbound_id = 'OUT-' + content_digest
            payload = wire({'version': version, 'outbound_id': outbound_id,
                            'content_digest': content_digest, 'manifest': manifest})
            return payload, sha256(payload).hexdigest(), outbound_id

        spoofed_manifest = {
            'recording_id': 'middle-five', 'work_order': 'w', 'batch_id': 'b', 'instrument_id': 'i',
            'revision_id': 'middle-five-r1', 'parent_revision_id': None,
            'channels': ['A'], 'occurrences': [],
        }
        duplicate_evidence = json.loads(json.dumps(valid_manifest))
        duplicate_evidence['evidence'].append([0, 0])
        wrong_width = json.loads(json.dumps(valid_manifest))
        wrong_width['evidence'] = [[0], [10]]
        out_of_bounds = json.loads(json.dumps(valid_manifest))
        out_of_bounds['evidence'] = [[0, 30]]
        wrong_residue = json.loads(json.dumps(valid_manifest))
        wrong_residue['evidence'] = [[0, 5]]  # 5 mod 10 != residue 0 at the tail position
        unsorted = json.loads(json.dumps(valid_manifest))
        unsorted['evidence'] = list(reversed(unsorted['evidence']))
        with ReceiveStore(self.receive_path) as inventory:
            cases = (
                ('digest', (packet.payload + b' ', packet.digest, packet.outbound_id)),
                ('identity', (packet.payload, packet.digest, 'OUT-other')),
                ('version', independent(spoofed_manifest)),
                ('manifest', independent(duplicate_evidence)),
                ('manifest', independent(wrong_width)),
                ('manifest', independent(out_of_bounds)),
                ('manifest', independent(wrong_residue)),
                ('manifest', independent(unsorted)),
            )
            for code, args in cases:
                with self.subTest(code=code):
                    with self.assertRaises(PacketRejected) as rejection:
                        receive_packet(inventory, *args)
                    self.assertEqual(rejection.exception.code, code)
            # non-canonical but parseable bytes (a space after a separator)
            raw = packet.payload.replace(b'{"content_digest":"', b'{"content_digest": "', 1)
            self.assertNotEqual(raw, packet.payload)
            with self.assertRaises(PacketRejected) as rejection:
                receive_packet(inventory, raw, sha256(raw).hexdigest(), envelope['outbound_id'])
            self.assertEqual(rejection.exception.code, 'encoding')
            self.assertEqual(list_acceptances(inventory), ())

    def test_commit_failure_leaves_no_partial_unwrap_report(self):
        packets = self._deliveries(('middle-five',))
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            acceptance = receive_packet(inventory, packets['middle-five'].payload,
                                        packets['middle-five'].digest, packets['middle-five'].outbound_id)
            old = sign_unwrap(inventory, reports, acceptance.acceptance_id, {})
            reports.connection.executescript('''
                CREATE TABLE permitted_test_receipts (receipt_id TEXT PRIMARY KEY);
                CREATE TABLE deferred_test_receipts (
                    receipt_id TEXT REFERENCES permitted_test_receipts(receipt_id) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER check_test_receipt AFTER INSERT ON receipts
                BEGIN INSERT INTO deferred_test_receipts VALUES (NEW.receipt_id); END;
            ''')
            with self.assertRaises(ReportCommitError):
                sign_unwrap(inventory, reports, acceptance.acceptance_id, {0: 0, 2: 10})
            self.assertFalse(reports.connection.in_transaction)
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0], 1)
            self.assertEqual(read_report(reports, old.receipt.report_id), old)
