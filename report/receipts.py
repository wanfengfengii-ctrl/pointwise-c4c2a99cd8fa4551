from dataclasses import dataclass

from report.serialization import compute_report_digest, serialize_report


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    report_id: str
    acceptance_id: int
    request_digest: str
    report_digest: str
    status: str


def build_receipt(report_id, acceptance_id, request_digest, report_digest):
    fields = {
        'report_id': report_id,
        'acceptance_id': acceptance_id,
        'request_digest': request_digest,
        'report_digest': report_digest,
        'status': 'signed',
    }
    receipt_id = 'OK-' + compute_report_digest(serialize_report(fields))
    return Receipt(receipt_id=receipt_id, **fields)


def verify_receipt(receipt: Receipt, report_id, acceptance_id, request_digest, report_digest):
    return receipt == build_receipt(report_id, acceptance_id, request_digest, report_digest)
