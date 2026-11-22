from dataclasses import dataclass

from issue.manifest import PacketManifest
from receive.validation import PacketValidationError, validate_packet_bytes, validate_packet_manifest
from record.measurements import Recording, occurrence_data, occurrence_from_data, require_fields


@dataclass(frozen=True)
class DecodedPacket:
    outbound_id: str
    digest: str
    manifest: PacketManifest


def decode_occurrence(data):
    occurrence = occurrence_from_data(data)
    if occurrence_data(occurrence) != data:
        raise ValueError('occurrence values must use canonical evidence representation')
    return occurrence


def decode_packet(payload, digest, expected_outbound_id):
    envelope = validate_packet_bytes(payload, digest, expected_outbound_id).require_envelope()
    data = envelope['manifest']
    fields = 'recording_id work_order batch_id instrument_id revision_id parent_revision_id channels occurrences'
    try:
        require_fields(data, fields, 'manifest')
        if not isinstance(data['channels'], list) or not isinstance(data['occurrences'], list):
            raise ValueError('manifest channels and occurrences must be arrays')
        recording = Recording(data['recording_id'], data['work_order'], data['batch_id'],
                              data['instrument_id'], tuple(data['channels']))
        manifest = PacketManifest(recording, data['revision_id'], data['parent_revision_id'],
                                  tuple(decode_occurrence(row) for row in data['occurrences']))
    except ValueError as error:
        raise PacketValidationError('manifest', str(error)) from error
    validate_packet_manifest(manifest)
    return DecodedPacket(envelope['outbound_id'], digest, manifest)
