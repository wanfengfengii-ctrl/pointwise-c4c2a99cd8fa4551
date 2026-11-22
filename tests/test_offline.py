from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import json
import sqlite3

from lab import PacketRejected, ReceiveStore, ReportStore, read_report, receive_packet, sign_review
from receive.inventory import get_accepted_packet, list_acceptances
from record.measurements import MeasurementOccurrence, MeasurementSequence, ReadingCandidate, SourceRef
from tests import LabCase, emit_scenario


def independent_delivery(manifest, version=1):
    def wire(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')

    content_digest = sha256(wire(manifest)).hexdigest()
    outbound_id = 'OUT-' + content_digest
    payload = wire({'version': version, 'outbound_id': outbound_id, 'content_digest': content_digest,
                    'manifest': manifest})
    return payload, sha256(payload).hexdigest(), outbound_id


class OfflineTests(LabCase):
    def test_offline_threshold_switch(self):
        packet = self.issue_sample()
        self.source_path.unlink()
        self.outbound_path.unlink()
        with ReceiveStore(self.receive_path) as inventory:
            accepted = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            threshold_10 = sign_review(inventory, reports, accepted.acceptance_id, {'A': 0}, 10)
            rows_10 = threshold_10.report['rows']
            self.assertEqual([row['delta'] for row in rows_10], ['7', '12', '4'], 'REVIEW_REFERENCE_MISMATCH')
            threshold_11 = sign_review(inventory, reports, accepted.acceptance_id, {'A': 0}, 11)
            rows_11 = threshold_11.report['rows']
            self.assertEqual([row['delta'] for row in rows_11], ['7', '11', '30'])
            self.assertEqual([row['selected_kind'] for row in rows_10], ['original', 'supplement', 'original'])
            self.assertEqual([row['selected_kind'] for row in rows_11], ['original', 'original', 'supplement'])
            self.assertEqual(rows_10[1]['selected'], {'value': '12', 'source': {
                'artifact': 'run-17.range', 'start': 0, 'end': 3,
            }})
            self.assertEqual(rows_10[2]['original'], {'value': '16', 'source': {
                'artifact': 'run-17.raw', 'start': 5, 'end': 8,
            }})
            self.assertEqual(rows_10[2]['reference_before'], {'value': '12', 'origin': {
                'kind': 'supplement', 'channel_id': 'A', 'occurrence_id': 'm2',
                'source': {'artifact': 'run-17.range', 'start': 0, 'end': 3},
            }})
            self.assertEqual(rows_10[1]['reference_after'], rows_10[2]['reference_before'])
            self.assertEqual(rows_11[1]['reference_before'], rows_11[1]['reference_after'])
            self.assertEqual(rows_11[2]['reference_before']['value'], '0')
            self.assertEqual(rows_11[2]['selected']['source'], {'artifact': 'run-17.range', 'start': 3, 'end': 6})
            self.assertEqual(rows_11[2]['reference_after']['origin']['occurrence_id'], 'm3')
            self.assertEqual(rows_11[2]['reference_after']['value'], '30')
            replayed = read_report(reports, threshold_10.receipt.report_id)
            self.assertEqual(replayed, threshold_10)
        actual = {'10': [row['delta'] for row in rows_10], '11': [row['delta'] for row in rows_11]}
        downstream = {'threshold': replayed.report['request']['threshold'],
                      'last_reference_occurrence': replayed.report['rows'][2]['reference_before']['origin']['occurrence_id'],
                      'receipt_status': replayed.receipt.status}
        emit_scenario('V3', {'original_mV': [7, 11, 16], 'supplement_mV': [None, 12, 30],
                            'initial_reference_mV': 0, 'thresholds_mV': [10, 11]},
                      {'10': ['7', '12', '4'], '11': ['7', '11', '30']}, actual,
                      {'threshold': '10', 'last_reference_occurrence': 'm2', 'receipt_status': 'signed'}, downstream,
                      ['receive/inventory.py', 'review/replay.py', 'review/references.py', 'report/history.py'],
                      '手算先比较原读与入行参考，再给采用值减旧参考。门槛 11 时第二次正好相等。')

    def test_independent_legal_packet(self):
        manifest = dict(self.sample['sequence'], recording_id='independent', work_order='recheck',
                        batch_id='T1', instrument_id='bench-2', revision_id='fixture-r1', parent_revision_id=None)
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            accepted = receive_packet(inventory, *independent_delivery(manifest))
            signed = sign_review(inventory, reports, accepted.acceptance_id, {'A': '0'}, '10')
        rows = signed.report['rows']
        self.assertEqual([row['delta'] for row in rows], ['7', '12', '4'])
        self.assertEqual(rows[2]['reference_before']['origin']['occurrence_id'], 'm2')
        self.assertEqual(rows[2]['reference_before']['origin']['source'],
                         {'artifact': 'run-17.range', 'start': 0, 'end': 3})

    def test_bad_packet_has_no_receipt(self):
        packet = self.issue_sample()
        corrupt = packet.payload + b' '
        base = json.loads(packet.payload)['manifest']
        bad_shape = deepcopy(base)
        bad_shape['occurrences'][2]['occurrence_id'] = 'm2'
        bad_rational = deepcopy(base)
        bad_rational['occurrences'][1]['supplement']['value'] = '12/0'
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            for expected_code, args in (
                ('digest', (corrupt, packet.digest, packet.outbound_id)),
                ('identity', (packet.payload, packet.digest, 'OUT-other')),
                ('version', independent_delivery(base, version=2)),
                ('manifest', independent_delivery(bad_shape)),
                ('manifest', independent_delivery(bad_rational)),
            ):
                with self.subTest(code=expected_code), self.assertRaises(PacketRejected) as rejection:
                    receive_packet(inventory, *args)
                self.assertEqual(rejection.exception.code, expected_code)
            self.assertEqual(list_acceptances(inventory), ())
            with self.assertRaises(KeyError):
                sign_review(inventory, reports, 1, {'A': 0}, 10)
            with self.assertRaises(KeyError):
                read_report(reports, 'unknown')
            counts = {'acceptances': len(list_acceptances(inventory)),
                      'reports': reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
                      'receipts': reports.connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]}
        self.assertEqual(counts, {'acceptances': 0, 'reports': 0, 'receipts': 0})
        emit_scenario('V4', {'invalid_cases': ['digest', 'identity', 'version', 'duplicate', 'rational']},
                      'manifest', rejection.exception.code, {'acceptances': 0, 'reports': 0, 'receipts': 0}, counts,
                      ['receive/validation.py', 'receive/decode.py', 'receive/intake.py', 'review/engine.py'],
                      '由交付单和独立构造的错件指定拒收类别，查询实际账册中下游行数。')

    def test_negative_exact_boundary(self):
        raw = ReadingCandidate(Fraction(9, 2), SourceRef('fraction.raw', 0, 3))
        supplement = ReadingCandidate(Fraction(18), SourceRef('fraction.range', 4, 6))
        occurrence = MeasurementOccurrence('edge', 0, 'A', 'bridge', raw, supplement)
        packet = self.issue_sample(MeasurementSequence(('A',), (occurrence,)))
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            accepted = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            signed = sign_review(inventory, reports, accepted.acceptance_id, {'A': 5}, '1/2')
            reloaded = read_report(reports, signed.receipt.report_id)
        row = reloaded.report['rows'][0]
        self.assertEqual(row['delta'], '-1/2')
        self.assertEqual(row['selected_kind'], 'original')
        self.assertEqual(row['selected']['source'], {'artifact': 'fraction.raw', 'start': 0, 'end': 3})
        self.assertEqual(row['reference_before'], row['reference_after'])
        self.assertEqual(row['reference_after']['value'], '5')
        emit_scenario('V5', {'original_mV': '9/2', 'initial_reference_mV': '5', 'threshold_mV': '1/2'},
                      '-1/2', row['delta'], {'selected': 'original', 'reference_mV': '5'},
                      {'selected': row['selected_kind'], 'reference_mV': row['reference_after']['value']},
                      ['review/request.py', 'review/replay.py', 'report/history.py'],
                      '手算 9/2 减 5 等于 -1/2，绝对值等于门槛。')

    def test_pending_stays_on_channel(self):
        m1, m2, m3 = self.sequence.occurrences
        b1 = MeasurementOccurrence('b1', 2, 'B', 'bridge',
                                   ReadingCandidate(Fraction(3), SourceRef('channel-b.raw', 0, 2)))
        m4 = MeasurementOccurrence('m4', 4, 'A', 'bridge',
                                   ReadingCandidate(Fraction(1), SourceRef('run-17.raw', 8, 10)))
        sequence = MeasurementSequence(('A', 'B'), (m1, replace(m2, supplement=None), b1, replace(m3, position=3), m4))
        packet = self.issue_sample(sequence)
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            accepted = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            signed = sign_review(inventory, reports, accepted.acceptance_id, {'A': 0, 'B': '1/2'}, 10)
            rows = read_report(reports, signed.receipt.report_id).report['rows']
        positions = [row['position'] for row in rows]
        occurrence_ids = [row['occurrence_id'] for row in rows]
        expected_ids = ['m1', 'm2', 'b1', 'm3', 'm4']
        actual = [row['delta'] for row in rows]
        expected = ['7', None, '5/2', None, None]
        self.assertEqual(positions, [0, 1, 2, 3, 4])
        self.assertEqual(occurrence_ids, expected_ids)
        self.assertEqual(actual, expected)
        self.assertEqual([row['status'] for row in rows], ['value', 'pending', 'value', 'pending', 'pending'])
        self.assertEqual(rows[1]['pending'], {'reason': 'missing_supplement', 'blocked_by': 'm2'})
        self.assertEqual(rows[1]['reference_before']['value'], '0')
        self.assertEqual(rows[2]['channel_id'], 'B')
        for row in (rows[1], rows[3], rows[4]):
            self.assertIsNone(row['selected'])
            self.assertIsNone(row['reference_after'])
            self.assertEqual(row['pending']['blocked_by'], 'm2')
        for row in (rows[3], rows[4]):
            self.assertIsNone(row['reference_before'])
            self.assertEqual(row['pending']['reason'], 'upstream_pending')
        self.assertEqual(rows[3]['original']['value'], '16')
        emit_scenario('V6', {'missing_supplement': 'm2', 'interleaved': 'b1',
                            'initial_reference_mV': {'A': '0', 'B': '1/2'}, 'threshold_mV': '10'},
                      expected, actual, expected_ids, occurrence_ids,
                      ['review/replay.py', 'review/pending.py', 'review/rows.py', 'report/history.py'],
                      '以 A 的第二次严格越界确定待核起点，B 独立手算 3 减 1/2。')

    def test_request_rejection_and_repeat_acceptance(self):
        packet = self.issue_sample()
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            first = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            second = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            self.assertNotEqual(first.acceptance_id, second.acceptance_id)
            self.assertEqual(get_accepted_packet(inventory, second.acceptance_id), second)
            for references, threshold in (({}, 10), ({'A': 0, 'Z': 0}, 10), ({'A': 0}, -1),
                                          ({'A': 'not a value'}, 10), ({'A': 0}, True)):
                with self.subTest(references=references, threshold=threshold), self.assertRaises(ValueError):
                    sign_review(inventory, reports, first.acceptance_id, references, threshold)
            with self.assertRaises(KeyError):
                sign_review(inventory, reports, second.acceptance_id + 1, {'A': 0}, 10)
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0], 0)
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 0)
            signed = sign_review(inventory, reports, second.acceptance_id, {'A': 0}, 10)
            self.assertEqual(signed.receipt.acceptance_id, second.acceptance_id)

    def test_acceptance_write_failure_leaves_existing_snapshot(self):
        packet = self.issue_sample()
        with ReceiveStore(self.receive_path) as inventory:
            first = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            inventory.connection.execute('''CREATE TRIGGER stop_acceptance BEFORE INSERT ON acceptances
                BEGIN SELECT RAISE(ABORT, 'inventory unavailable'); END''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'inventory unavailable'):
                receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
        with ReceiveStore(self.receive_path) as inventory:
            self.assertEqual(list_acceptances(inventory), (first,))
