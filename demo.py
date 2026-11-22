import json
from pathlib import Path
from tempfile import TemporaryDirectory

from lab import (IssueRegistry, ReceiveStore, RecordStore, ReportStore, issue_packet, issue_unwrap,
                 read_report, receive_packet, record_revision, register_recording, reissue_packet,
                 sign_review, sign_unwrap)
from record.measurements import sequence_from_data
from unwrap_examples import EXAMPLES, freeze_example


def run_shift_demo(root):
    sample_path = Path(__file__).resolve().parent / 'samples' / 'shift.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    sequence = sequence_from_data(sample['sequence'])
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


def run_unwrap_demo(root):
    """Issue V2 unwrap packets while the white-shift libraries are open, then close them."""
    names = ('middle-five', 'middle-zero')
    deliveries = {}
    with RecordStore(root / 'unwrap-record.sqlite') as source, \
            IssueRegistry(root / 'unwrap-outbound.sqlite') as registry:
        for name in names:
            revision = freeze_example(source, name)
            example = EXAMPLES[name]
            packet = issue_unwrap(source, registry, revision.revision_id, example.channel, example.modulus,
                                  example.bounds, example.max_step, list(example.positions))
            if reissue_packet(registry, packet.outbound_id) != packet:
                raise RuntimeError(f'{name}: V2 reissue changed the fixed packet')
            deliveries[name] = packet
    # White shift is closed: source and registry files stay untouched from here on.
    report_ids = {}
    with ReceiveStore(root / 'unwrap-night.sqlite') as inventory, \
            ReportStore(root / 'unwrap-reports.sqlite') as reports:
        acceptances = {}
        for name in names:
            packet = deliveries[name]
            acceptances[name] = receive_packet(inventory, packet.payload, packet.digest, packet.outbound_id)
        # One late calibration sheet (0 at the head, 10 at the tail) applied to the same trajectory
        # on each roll; the rolls share no legal track under the sheet in the same way.
        sheet = {0: 0, 2: 10}
        for name in names:
            signed = sign_unwrap(inventory, reports, acceptances[name].acceptance_id, sheet)
            report_ids[name] = signed.receipt.report_id
            print(json.dumps({
                'roll': name,
                'acceptance_id': acceptances[name].acceptance_id,
                'outbound_id': deliveries[name].outbound_id,
                'anchors': [[position, value] for position, value in sorted(sheet.items())],
                'outcome': signed.report['outcome'],
                'rows': signed.report['rows'],
            }, sort_keys=True))
        # Re-issuing the same request returns the original signed report before the library reopens.
        repeat = sign_unwrap(inventory, reports, acceptances['middle-five'].acceptance_id, sheet)
        if repeat.receipt.report_id != report_ids['middle-five']:
            raise RuntimeError('repeat calibration did not return the original signed report')
    # Reopen with only the report library; receipts and reports remain claimable as fixed bytes.
    with ReportStore(root / 'unwrap-reports.sqlite') as reports:
        for name in names:
            signed = read_report(reports, report_ids[name])
            print(json.dumps({
                'reopen': True,
                'roll': name,
                'report_id': signed.report['report_id'],
                'receipt_id': signed.receipt.receipt_id,
                'outcome': signed.report['outcome'],
                'packet': signed.report['packet'],
            }, sort_keys=True))


def main():
    with TemporaryDirectory(prefix='lab-shift-') as directory:
        root = Path(directory)
        run_shift_demo(root)
        run_unwrap_demo(root)


if __name__ == '__main__':
    main()
