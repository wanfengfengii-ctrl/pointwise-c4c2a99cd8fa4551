from dataclasses import asdict
import sqlite3

from report.history import unpack_bundle
from report.receipts import build_receipt
from report.serialization import compute_report_digest, serialize_report
from report.store import ReportStore, StoredBundle
from review.engine import ReviewResult


class ReportCommitError(RuntimeError):
    pass


def commit_report_and_receipt(store: ReportStore, bundle: StoredBundle):
    try:
        return store.commit_bundle(bundle)
    except sqlite3.Error as error:
        raise ReportCommitError('report and receipt could not be committed') from error


def publish_review(store: ReportStore, result: ReviewResult):
    acceptance = result.acceptance
    request = result.request.as_data()
    packet = {
        'outbound_id': acceptance.outbound_id,
        'revision_id': acceptance.revision_id,
        'digest': acceptance.digest,
    }
    request_digest = compute_report_digest(serialize_report({'packet': packet, 'request': request}))
    report_id = 'R-' + request_digest
    recording = result.manifest.recording
    report = {
        'report_id': report_id,
        'request_digest': request_digest,
        'packet': packet,
        'request': request,
        'recording': {
            'recording_id': recording.recording_id,
            'work_order': recording.work_order,
            'batch_id': recording.batch_id,
            'instrument_id': recording.instrument_id,
        },
        'rows': [row.as_data() for row in result.rows],
    }
    payload = serialize_report(report)
    digest = compute_report_digest(payload)
    receipt = build_receipt(report_id, acceptance.acceptance_id, request_digest, digest)
    bundle = StoredBundle(report_id, acceptance.acceptance_id, digest, payload,
                          receipt.receipt_id, serialize_report(asdict(receipt)))
    return unpack_bundle(commit_report_and_receipt(store, bundle))
