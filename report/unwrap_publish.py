from dataclasses import asdict

from report.history import unpack_bundle
from report.publish import ReportCommitError, commit_report_and_receipt
from report.receipts import build_receipt
from report.serialization import compute_report_digest, serialize_report
from report.store import StoredBundle
from review.unwrap_engine import UnwrapResult


def publish_unwrap(store, result: UnwrapResult):
    acceptance = result.acceptance
    request = result.request.as_data()
    packet = {
        'outbound_id': acceptance.outbound_id,
        'revision_id': acceptance.revision_id,
        'digest': acceptance.digest,
    }
    request_digest = compute_report_digest(serialize_report({'packet': packet, 'request': request}))
    report_id = 'R-' + request_digest
    report = {
        'report_id': report_id,
        'request_digest': request_digest,
        'packet': packet,
        'request': request,
        'outcome': result.outcome,
        'rows': list(result.rows),
    }
    payload = serialize_report(report)
    digest = compute_report_digest(payload)
    receipt = build_receipt(report_id, acceptance.acceptance_id, request_digest, digest)
    bundle = StoredBundle(report_id, acceptance.acceptance_id, digest, payload,
                          receipt.receipt_id, serialize_report(asdict(receipt)))
    return unpack_bundle(commit_report_and_receipt(store, bundle))
