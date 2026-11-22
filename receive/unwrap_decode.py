from dataclasses import dataclass

from issue.unwrap_manifest import UnwrapManifest, UnwrapSelected, unwrap_manifest_data
from receive.validation import PacketValidationError, validate_unwrap_packet_bytes
from record.measurements import SourceRef, require_fields
from record.validation import require_identifier


@dataclass(frozen=True)
class DecodedUnwrapPacket:
    version: int
    outbound_id: str
    digest: str
    manifest: UnwrapManifest


def _require_int(value, label):
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer (booleans are rejected)')
    return value


def _decode_selected(data, positions_seen):
    require_fields(data, 'position residue source', 'selected entry')
    position = _require_int(data['position'], 'position')
    residue = _require_int(data['residue'], 'residue')
    source_data = data['source']
    require_fields(source_data, 'artifact start end', 'source')
    require_identifier(source_data['artifact'], 'source artifact')
    start = _require_int(source_data['start'], 'source start')
    end = _require_int(source_data['end'], 'source end')
    if not 0 <= start < end:
        raise ValueError('source range must be a nonempty half-open byte range')
    if position < 0 or position in positions_seen:
        raise ValueError('selected positions must be distinct zero-based positions')
    if residue < 0:
        raise ValueError('residue must be nonnegative')
    positions_seen.add(position)
    return UnwrapSelected(position, residue, SourceRef(source_data['artifact'], start, end))


def decode_unwrap_packet(payload, digest, expected_outbound_id):
    envelope = validate_unwrap_packet_bytes(payload, digest, expected_outbound_id).require_envelope()
    data = envelope['manifest']
    try:
        fields = 'kind recording_id revision_id channel modulus bounds max_step selected evidence'
        require_fields(data, fields, 'unwrap manifest')
        if data['kind'] != 'unwrap':
            raise ValueError('unwrap manifest kind mismatch')
        require_identifier(data['recording_id'], 'recording id')
        require_identifier(data['revision_id'], 'revision id')
        require_identifier(data['channel'], 'channel')
        modulus = _require_int(data['modulus'], 'modulus')
        if modulus <= 0:
            raise ValueError('modulus must be a positive integer')
        if not isinstance(data['bounds'], list) or len(data['bounds']) != 2:
            raise ValueError('bounds must be a two-element array')
        low, high = (_require_int(point, 'bounds endpoint') for point in data['bounds'])
        if low > high:
            raise ValueError('bounds must satisfy lo <= hi')
        max_step = _require_int(data['max_step'], 'max_step')
        if max_step < 0:
            raise ValueError('max_step must be a nonnegative integer')
        if not isinstance(data['selected'], list) or not data['selected']:
            raise ValueError('selected must be a nonempty array')
        positions_seen = set()
        selected = tuple(_decode_selected(entry, positions_seen) for entry in data['selected'])
        if [entry.position for entry in selected] != sorted(entry.position for entry in selected):
            raise ValueError('selected entries must be ordered by position')
        if any(not 0 <= entry.residue < modulus for entry in selected):
            raise ValueError('each residue must lie in [0, modulus)')
        evidence = _decode_evidence(data['evidence'], selected, modulus, low, high)
        manifest = UnwrapManifest(data['recording_id'], data['revision_id'], data['channel'], modulus,
                                  (low, high), max_step, selected, evidence)
        if unwrap_manifest_data(manifest) != data:
            raise ValueError('unwrap manifest must use the canonical evidence representation')
    except ValueError as error:
        raise PacketValidationError('manifest', str(error)) from error
    return DecodedUnwrapPacket(envelope['version'], envelope['outbound_id'], digest, manifest)


def _decode_evidence(data, selected, modulus, low, high):
    width = len(selected)
    if not isinstance(data, list) or not data:
        raise ValueError('evidence must be a nonempty array of joint value combinations')
    combos = []
    seen = set()
    for combo in data:
        if not isinstance(combo, list) or len(combo) != width:
            raise ValueError('each evidence combination must align with the selected positions')
        values = tuple(_require_int(value, 'evidence value') for value in combo)
        if any(not low <= value <= high for value in values):
            raise ValueError('evidence values must lie inside the closed bounds')
        if any(value % modulus != entry.residue for value, entry in zip(values, selected)):
            raise ValueError('evidence values must share the residue of their selected position')
        if values in seen:
            raise ValueError('evidence combinations must be distinct')
        seen.add(values)
        combos.append(values)
    if combos != sorted(combos):
        raise ValueError('evidence combinations must be sorted')
    return tuple(combos)
