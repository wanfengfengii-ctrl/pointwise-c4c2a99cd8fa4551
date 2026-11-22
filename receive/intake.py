import json

from receive.decode import decode_packet
from receive.inventory import register_acceptance
from receive.store import ReceiveStore
from receive.unwrap_decode import decode_unwrap_packet
from receive.validation import PacketValidationError


class PacketRejected(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def reject_packet(error: PacketValidationError):
    raise PacketRejected(error.code, str(error)) from error


def accept_packet(store: ReceiveStore, payload, digest, expected_outbound_id):
    try:
        envelope = json.loads(payload.decode('utf-8'))
        version = envelope.get('version') if isinstance(envelope, dict) else None
        if version == 2:
            decoded = decode_unwrap_packet(payload, digest, expected_outbound_id)
        else:
            decoded = decode_packet(payload, digest, expected_outbound_id)
    except PacketValidationError as error:
        reject_packet(error)
    return register_acceptance(store, decoded, payload)


receive_packet = accept_packet
