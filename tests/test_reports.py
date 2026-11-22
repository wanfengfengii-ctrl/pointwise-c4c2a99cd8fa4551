from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import sqlite3

from lab import IssueRegistry, ReceiveStore, RecordStore, ReportCommitError, ReportStore
from lab import create_correction_revision, issue_packet, read_receipt, read_report, receive_packet, sign_review
from record.measurements import ReadingCandidate, SourceRef
from report.history import list_reports_for_acceptance
from tests import LabCase, emit_scenario


class ReportTests(LabCase):
    def test_report_commit_failure(self):
        packet = self.issue_sample()
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            accepted = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            old = sign_review(inventory, reports, accepted.acceptance_id, {'A': 0}, 10)
            original_bytes = reports.load_bundle(old.receipt.report_id)
            reports.connection.executescript('''
                CREATE TABLE permitted_test_receipts (receipt_id TEXT PRIMARY KEY);
                CREATE TABLE deferred_test_receipts (
                    receipt_id TEXT REFERENCES permitted_test_receipts(receipt_id) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER check_test_receipt AFTER INSERT ON receipts
                BEGIN INSERT INTO deferred_test_receipts VALUES (NEW.receipt_id); END;
            ''')
            with self.assertRaises(ReportCommitError) as failure:
                sign_review(inventory, reports, accepted.acceptance_id, {'A': 0}, 11)
            self.assertIsInstance(failure.exception.__cause__, sqlite3.IntegrityError)
            self.assertIn('FOREIGN KEY', str(failure.exception.__cause__))
            self.assertFalse(reports.connection.in_transaction)
            counts = {'reports': reports.connection.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
                      'receipts': reports.connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]}
            self.assertEqual(counts, {'reports': 1, 'receipts': 1})
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM deferred_test_receipts').fetchone()[0], 0)
            self.assertEqual(list_reports_for_acceptance(reports, accepted.acceptance_id), (old,))
            self.assertEqual(reports.load_bundle(old.receipt.report_id), original_bytes)
            self.assertEqual(read_receipt(reports, old.receipt.report_id), old.receipt)
        with ReportStore(self.report_path) as reports:
            reloaded = read_report(reports, old.receipt.report_id)
            self.assertEqual(reloaded, old)
        emit_scenario('V7', {'existing_threshold_mV': 10, 'new_threshold_mV': 11,
                            'database_condition': 'deferred foreign key fails at commit'},
                      {'reports': 1, 'receipts': 1}, counts, {'same_old_bundle': True},
                      {'same_old_bundle': reloaded == old},
                      ['report/publish.py', 'report/store.py', 'labdb.py', 'report/history.py'],
                      '用 SQLite 延迟约束触发真实提交失败，分别查询报告表和回执表并重开复领。')

    def test_revision_and_reopen(self):
        old_packet = self.issue_sample()
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            old_accepted = receive_packet(inventory, old_packet.payload, old_packet.digest, old_packet.outbound_id)
            references = {'A': '0'}
            old = sign_review(inventory, reports, old_accepted.acceptance_id, references, '10')
            references['A'] = '9'
            old_bundle = reports.load_bundle(old.receipt.report_id)
        with RecordStore(self.source_path) as source, IssueRegistry(self.outbound_path) as registry:
            first, second, third = self.sequence.occurrences
            corrected = replace(first, original=ReadingCandidate(Fraction(8), SourceRef('correction.raw', 0, 2)))
            revision = create_correction_revision(source, 'shift-17-r1', 'shift-17-r2', (corrected, second, third))
            self.assertEqual(source.revision_status('shift-17-r1'), 'superseded')
            self.assertEqual(source.revision_status('shift-17-r2'), 'frozen')
            new_packet = issue_packet(source, registry, revision.revision_id)
            self.assertNotEqual(new_packet.outbound_id, old_packet.outbound_id)
            self.assertEqual(issue_packet(source, registry, 'shift-17-r1'), old_packet)
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            new_accepted = receive_packet(inventory, new_packet.payload, new_packet.digest, new_packet.outbound_id)
            self.assertNotEqual(new_accepted.acceptance_id, old_accepted.acceptance_id)
            new = sign_review(inventory, reports, new_accepted.acceptance_id, {'A': '0'}, '11')
            self.assertNotEqual(new.receipt, old.receipt)
            self.assertEqual(new.report['packet']['revision_id'], 'shift-17-r2')
            self.assertEqual(new.report['rows'][0]['original']['source']['artifact'], 'correction.raw')
            self.assertEqual(new.receipt.report_digest, sha256(reports.load_bundle(new.receipt.report_id).report_bytes).hexdigest())
        with ReportStore(self.report_path) as reports:
            old_reloaded = read_report(reports, old.receipt.report_id)
            new_reloaded = read_report(reports, new.receipt.report_id)
            self.assertEqual(old_reloaded, old)
            self.assertEqual(reports.load_bundle(old.receipt.report_id), old_bundle)
            self.assertEqual(read_receipt(reports, old.receipt.report_id), old.receipt)
            self.assertEqual(new_reloaded, new)
            self.assertEqual(list_reports_for_acceptance(reports, old_accepted.acceptance_id), (old,))
        expected = {'old': ['7', '12', '4'], 'new': ['8', '11', '30']}
        actual = {'old': [row['delta'] for row in old_reloaded.report['rows']],
                  'new': [row['delta'] for row in new_reloaded.report['rows']]}
        self.assertEqual(actual, expected)
        self.assertEqual(old_reloaded.report['request']['initial_references'], {'A': '0'})
        self.assertEqual(old_reloaded.report['rows'][0]['original']['source']['artifact'], 'run-17.raw')
        emit_scenario('V8', {'correction_m1_mV': 8, 'old_threshold_mV': 10, 'new_threshold_mV': 11},
                      expected, actual, {'old_revision': 'shift-17-r1', 'same_receipt': True},
                      {'old_revision': old_reloaded.report['packet']['revision_id'],
                       'same_receipt': old_reloaded.receipt == old.receipt},
                      ['record/revisions.py', 'issue/registry.py', 'receive/inventory.py', 'report/history.py'],
                      '分别手算原卷与勘误卷差值，重开只读历史库并比较原报告与原首执。')

    def test_same_request_keeps_receipt_and_caller_cannot_edit_snapshot(self):
        packet = self.issue_sample()
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            accepted = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
            first = sign_review(inventory, reports, accepted.acceptance_id, {'A': '0/3'}, '20/2')
            first.report['rows'][0]['delta'] = '999'
        with ReceiveStore(self.receive_path) as inventory, ReportStore(self.report_path) as reports:
            second = sign_review(inventory, reports, accepted.acceptance_id, {'A': 0}, 10)
            self.assertEqual(first.receipt, second.receipt)
            self.assertEqual(second.report['rows'][0]['delta'], '7')
            self.assertEqual(list_reports_for_acceptance(reports, accepted.acceptance_id), (second,))
            self.assertEqual(reports.connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
