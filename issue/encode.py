from dataclasses import dataclass
from hashlib import sha256
import json

from issue.evidence import attach_occurrence_provenance, validate_evidence_completeness
from issue.manifest import PacketManifest, manifest_schema_version


@dataclass(frozen=True)
class FixedPacket:
    outbound_id: str
    digest: str
    payload: bytes


def canonical_packet_bytes(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def compute_packet_digest(payload):
    return sha256(payload).hexdigest()


def outbound_id_for(content_digest):
    return f'OUT-{content_digest}'


def _manifest_data(manifest):
    recording = manifest.recording
    return {
        'recording_id': recording.recording_id,
        'work_order': recording.work_order,
        'batch_id': recording.batch_id,
        'instrument_id': recording.instrument_id,
        'revision_id': manifest.revision_id,
        'parent_revision_id': manifest.parent_revision_id,
        'channels': list(recording.channels),
        'occurrences': [attach_occurrence_provenance(row) for row in manifest.occurrences],
    }


def encode_packet(manifest: PacketManifest):
    validate_evidence_completeness(manifest)
    body = _manifest_data(manifest)
    content_digest = compute_packet_digest(canonical_packet_bytes(body))
    outbound_id = outbound_id_for(content_digest)
    payload = canonical_packet_bytes({
        'version': manifest_schema_version,
        'outbound_id': outbound_id,
        'content_digest': content_digest,
        'manifest': body,
    })
    return FixedPacket(outbound_id, compute_packet_digest(payload), payload)
