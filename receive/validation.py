from dataclasses import dataclass
import json

from issue.encode import canonical_packet_bytes, compute_packet_digest, outbound_id_for
from issue.manifest import PacketManifest, manifest_schema_version
from issue.unwrap_manifest import unwrap_schema_version
from record.measurements import require_fields
from record.validation import validate_revision_shape


class PacketValidationError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class PacketValidationResult:
    envelope: dict | None
    code: str | None = None
    detail: str = ''

    def require_envelope(self):
        if self.envelope is None:
            raise PacketValidationError(self.code, self.detail)
        return self.envelope


def validate_packet_bytes(payload, digest, expected_outbound_id):
    envelope_result = _load_envelope(payload, digest, expected_outbound_id)
    if envelope_result.envelope is None:
        return envelope_result
    envelope = envelope_result.envelope
    if type(envelope['version']) is not int or envelope['version'] != manifest_schema_version:
        return PacketValidationResult(None, 'version', 'unsupported packet version')
    if not isinstance(envelope['manifest'], dict):
        return PacketValidationResult(None, 'manifest', 'packet manifest must be an object')
    actual = compute_packet_digest(canonical_packet_bytes(envelope['manifest']))
    if envelope['content_digest'] != actual or envelope['outbound_id'] != outbound_id_for(actual):
        return PacketValidationResult(None, 'identity', 'outbound id and content digest do not bind the manifest')
    return PacketValidationResult(envelope)


def validate_unwrap_packet_bytes(payload, digest, expected_outbound_id):
    envelope_result = _load_envelope(payload, digest, expected_outbound_id)
    if envelope_result.envelope is None:
        return envelope_result
    envelope = envelope_result.envelope
    if type(envelope['version']) is not int or envelope['version'] != unwrap_schema_version:
        return PacketValidationResult(None, 'version', 'unsupported packet version')
    manifest = envelope['manifest']
    if not isinstance(manifest, dict):
        return PacketValidationResult(None, 'manifest', 'packet manifest must be an object')
    if manifest.get('kind') != 'unwrap':
        return PacketValidationResult(None, 'version', 'V2 packet must carry an unwrap manifest')
    actual = compute_packet_digest(canonical_packet_bytes(manifest))
    if envelope['content_digest'] != actual or envelope['outbound_id'] != outbound_id_for(actual):
        return PacketValidationResult(None, 'identity', 'outbound id and content digest do not bind the manifest')
    return PacketValidationResult(envelope)


def _load_envelope(payload, digest, expected_outbound_id):
    if type(payload) is not bytes or type(digest) is not str or compute_packet_digest(payload) != digest:
        return PacketValidationResult(None, 'digest', 'packet byte digest does not match the delivery slip')
    try:
        envelope = json.loads(payload.decode('utf-8'))
        require_fields(envelope, 'version outbound_id content_digest manifest', 'packet envelope')
        if type(envelope['version']) is not int:
            raise ValueError('packet version must be an integer')
        if canonical_packet_bytes(envelope) != payload:
            raise ValueError('packet bytes are not canonical')
    except (ValueError, RecursionError) as error:
        return PacketValidationResult(None, 'encoding', str(error))
    if type(expected_outbound_id) is not str or envelope['outbound_id'] != expected_outbound_id:
        return PacketValidationResult(None, 'identity', 'packet outbound id does not match the delivery slip')
    return PacketValidationResult(envelope)


def validate_packet_manifest(manifest: PacketManifest):
    try:
        validate_revision_shape(manifest.recording, manifest.revision_id,
                                manifest.parent_revision_id, manifest.sequence())
    except ValueError as error:
        raise PacketValidationError('manifest', str(error)) from error
