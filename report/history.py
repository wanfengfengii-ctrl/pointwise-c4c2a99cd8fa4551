from dataclasses import dataclass

from report.receipts import Receipt, verify_receipt
from report.serialization import compute_report_digest, deserialize_report, serialize_report
from report.store import ReportStore, StoredBundle


@dataclass(frozen=True)
class SignedReport:
    report: dict
    receipt: Receipt


def unpack_bundle(bundle: StoredBundle):
    digest = compute_report_digest(bundle.report_bytes)
    if digest != bundle.report_digest:
        raise ValueError('stored report digest mismatch')
    report = deserialize_report(bundle.report_bytes)
    receipt = Receipt(**deserialize_report(bundle.receipt_bytes))
    request = report['request']
    request_digest = compute_report_digest(serialize_report({'packet': report['packet'], 'request': request}))
    if (report['report_id'] != bundle.report_id or bundle.report_id != 'R-' + request_digest
            or report['request_digest'] != request_digest or request['acceptance_id'] != bundle.acceptance_id
            or receipt.receipt_id != bundle.receipt_id
            or not verify_receipt(receipt, bundle.report_id, bundle.acceptance_id, request_digest, digest)):
        raise ValueError('stored report and receipt identity mismatch')
    return SignedReport(report, receipt)


def read_report(store: ReportStore, report_id):
    return unpack_bundle(store.load_bundle(report_id))


def read_receipt(store: ReportStore, report_id):
    return read_report(store, report_id).receipt


def list_reports_for_acceptance(store: ReportStore, acceptance_id):
    return tuple(read_report(store, report_id) for report_id in store.report_ids_for_acceptance(acceptance_id))
