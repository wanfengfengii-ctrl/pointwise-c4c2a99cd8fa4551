from issue.evidence import build_packet_evidence
from issue.registry import IssueRegistry as IssueRegistry
from issue.selection import select_packet_for_reissue, select_revision_for_issue
from receive.intake import PacketRejected as PacketRejected
from receive.intake import receive_packet as receive_packet
from receive.store import ReceiveStore as ReceiveStore
from record.intake import accept_recording as accept_recording
from record.intake import append_occurrence as append_occurrence
from record.intake import register_recording as register_recording
from record.revisions import create_correction_revision as create_correction_revision
from record.revisions import freeze_revision as freeze_revision
from record.store import RecordStore as RecordStore
from report.history import read_receipt as read_receipt
from report.history import read_report as read_report
from report.publish import ReportCommitError as ReportCommitError
from report.publish import publish_review
from report.store import ReportStore as ReportStore
from review.engine import run_review
from review.request import make_review_request


def record_revision(source, recording_id, draft_id, revision_id, occurrences):
    accept_recording(source, recording_id, draft_id, occurrences)
    return freeze_revision(source, draft_id, revision_id)


def issue_packet(source, registry, revision_id):
    selection = select_revision_for_issue(source, revision_id)
    return registry.register_packet(build_packet_evidence(selection.revision))


def reissue_packet(registry, outbound_id):
    return registry.record_reissue(select_packet_for_reissue(registry, outbound_id))


def sign_review(inventory, reports, acceptance_id, initial_references, threshold):
    request = make_review_request(acceptance_id, initial_references, threshold)
    return publish_review(reports, run_review(inventory, request))
