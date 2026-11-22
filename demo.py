import json
from pathlib import Path
from tempfile import TemporaryDirectory

from lab import IssueRegistry, ReceiveStore, RecordStore, ReportStore, issue_packet, read_report
from lab import receive_packet, record_revision, register_recording, reissue_packet, sign_review
from record.measurements import sequence_from_data


def main():
    sample_path = Path(__file__).resolve().parent / 'samples' / 'shift.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    sequence = sequence_from_data(sample['sequence'])
    with TemporaryDirectory(prefix='lab-shift-') as directory:
        root = Path(directory)
        with RecordStore(root / 'record.sqlite') as source, IssueRegistry(root / 'outbound.sqlite') as registry:
            recording = register_recording(source, sample['recording_id'], sample['work_order'],
                                           sample['batch_id'], sample['instrument_id'], sequence.channels)
            revision = record_revision(source, recording.recording_id, 'shift-draft',
                                       sample['revision_id'], sequence.occurrences)
            issued = issue_packet(source, registry, revision.revision_id)
            delivery = reissue_packet(registry, issued.outbound_id)
            if delivery != issued:
                raise RuntimeError('reissue changed the fixed packet')
        report_ids = []
        with ReceiveStore(root / 'night.sqlite') as inventory, ReportStore(root / 'reports.sqlite') as reports:
            accepted = receive_packet(inventory, delivery.payload, delivery.digest, delivery.outbound_id)
            for threshold in (10, 11):
                signed = sign_review(inventory, reports, accepted.acceptance_id, {'A': 0}, threshold)
                report_ids.append(signed.receipt.report_id)
        with ReportStore(root / 'reports.sqlite') as reports:
            for report_id in report_ids:
                signed = read_report(reports, report_id)
                report = signed.report
                print(json.dumps({
                    'report_id': report_id,
                    'receipt_id': signed.receipt.receipt_id,
                    'outbound_id': report['packet']['outbound_id'],
                    'revision_id': report['packet']['revision_id'],
                    'acceptance_id': report['request']['acceptance_id'],
                    'threshold_mV': report['request']['threshold'],
                    'deltas_mV': [row['delta'] for row in report['rows']],
                    'selected': [row['selected'] for row in report['rows']],
                    'last_reference': report['rows'][-1]['reference_before'],
                }, sort_keys=True))


if __name__ == '__main__':
    main()
