from collections.abc import Mapping
from dataclasses import dataclass

from receive.inventory import AcceptanceRecord, load_accepted_envelope
from receive.store import ReceiveStore, valid_acceptance_id
from receive.unwrap_decode import decode_unwrap_packet
from unwrap.tracks import adjudicate


@dataclass(frozen=True)
class UnwrapRequest:
    acceptance_id: int
    anchors: tuple[tuple[int, int], ...]

    def as_data(self):
        return {
            'kind': 'unwrap',
            'acceptance_id': self.acceptance_id,
            'anchors': [[position, value] for position, value in self.anchors],
        }


@dataclass(frozen=True)
class UnwrapResult:
    acceptance: AcceptanceRecord
    manifest: object
    request: UnwrapRequest
    outcome: str
    rows: tuple[dict, ...]


def _require_int(value, label):
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer (booleans are rejected)')
    return value


def make_unwrap_request(acceptance_id, anchors):
    if not valid_acceptance_id(acceptance_id):
        raise ValueError('invalid unwrap acceptance id')
    if not isinstance(anchors, Mapping):
        raise ValueError('anchors must map selected positions to integer real values')
    pairs = []
    for position, value in anchors.items():
        _require_int(position, 'anchor position')
        _require_int(value, 'anchor value')
        pairs.append((position, value))
    return UnwrapRequest(acceptance_id, tuple(sorted(pairs)))


def run_unwrap_review(store: ReceiveStore, request: UnwrapRequest):
    if not isinstance(request, UnwrapRequest) or not valid_acceptance_id(request.acceptance_id):
        raise ValueError('invalid unwrap request')
    acceptance, envelope = load_accepted_envelope(store, request.acceptance_id)
    if envelope.get('version') != 2:
        raise ValueError('sign_unwrap only accepts V2 unwrap packets')
    packet = decode_unwrap_packet(acceptance.payload, acceptance.digest, acceptance.outbound_id)
    manifest = packet.manifest
    if manifest.revision_id != acceptance.revision_id:
        raise ValueError('stored acceptance revision does not match its packet')
    low, high = manifest.bounds
    anchor_indexes = {}
    for index, entry in enumerate(manifest.selected):
        anchor_indexes[entry.position] = index
    anchor_map = dict(request.anchors)
    for position, value in request.anchors:
        if position not in anchor_indexes:
            raise ValueError(f'anchor position {position} is not among the selected positions')
        if not low <= value <= high:
            raise ValueError(f'anchor at position {position} lies outside the closed bounds')
    anchor_indexes_in_evidence = {position: index for index, position in enumerate(
        entry.position for entry in manifest.selected
    )}
    outcome, verdicts = adjudicate(manifest.evidence, anchor_indexes_in_evidence, anchor_map)
    if outcome == 'conflict':
        rows = ()
    else:
        rows = tuple(
            {
                'position': entry.position,
                'residue': entry.residue,
                'source': {
                    'artifact': entry.source.artifact,
                    'start': entry.source.start,
                    'end': entry.source.end,
                },
                'status': verdict[1],
                'value': verdict[2],
            }
            for entry, verdict in zip(manifest.selected, verdicts)
        )
    return UnwrapResult(acceptance, manifest, request, outcome, rows)
