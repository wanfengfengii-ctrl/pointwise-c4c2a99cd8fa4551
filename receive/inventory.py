from dataclasses import dataclass
import json

from receive.decode import DecodedPacket
from receive.store import ReceiveStore


@dataclass(frozen=True)
class AcceptanceRecord:
    acceptance_id: int
    outbound_id: str
    revision_id: str
    digest: str
    payload: bytes


def _make_record(row):
    return AcceptanceRecord(row['acceptance_id'], row['outbound_id'], row['revision_id'],
                            row['digest'], row['payload'])


def register_acceptance(store: ReceiveStore, decoded: DecodedPacket, payload):
    revision_id = decoded.manifest.revision_id
    acceptance_id = store.save_acceptance(decoded.outbound_id, revision_id, decoded.digest, payload)
    return AcceptanceRecord(acceptance_id, decoded.outbound_id, revision_id, decoded.digest, payload)


def get_accepted_packet(store: ReceiveStore, acceptance_id):
    return _make_record(store.load_acceptance(acceptance_id))


def load_accepted_envelope(store: ReceiveStore, acceptance_id):
    """Load an accepted delivery and split it by envelope version."""
    acceptance = get_accepted_packet(store, acceptance_id)
    envelope = json.loads(acceptance.payload.decode('utf-8'))
    return acceptance, envelope


def list_acceptances(store: ReceiveStore):
    return tuple(_make_record(row) for row in store.acceptance_rows())
