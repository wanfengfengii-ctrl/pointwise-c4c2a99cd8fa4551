from dataclasses import dataclass

from issue.manifest import PacketManifest
from receive.decode import decode_packet
from receive.inventory import AcceptanceRecord, get_accepted_packet
from receive.store import ReceiveStore
from review.replay import replay_measurements
from review.request import ReviewRequest, validate_review_request
from review.rows import ReviewRow


@dataclass(frozen=True)
class ReviewResult:
    acceptance: AcceptanceRecord
    manifest: PacketManifest
    request: ReviewRequest
    rows: tuple[ReviewRow, ...]


def validate_review_input(store: ReceiveStore, request: ReviewRequest):
    validate_review_request(request)
    acceptance = get_accepted_packet(store, request.acceptance_id)
    packet = decode_packet(acceptance.payload, acceptance.digest, acceptance.outbound_id)
    manifest = packet.manifest
    if manifest.revision_id != acceptance.revision_id:
        raise ValueError('stored acceptance revision does not match its packet')
    active_channels = {row.channel_id for row in manifest.occurrences}
    validate_review_request(request, manifest.recording.channels, active_channels)
    return acceptance, manifest


def run_review(store: ReceiveStore, request: ReviewRequest):
    acceptance, manifest = validate_review_input(store, request)
    rows = replay_measurements(manifest, request)
    return ReviewResult(acceptance, manifest, request, rows)
