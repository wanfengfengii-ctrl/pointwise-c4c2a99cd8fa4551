from receive.decode import decode_packet
from receive.inventory import register_acceptance
from receive.store import ReceiveStore
from receive.validation import PacketValidationError


class PacketRejected(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def reject_packet(error: PacketValidationError):
    raise PacketRejected(error.code, str(error)) from error


def accept_packet(store: ReceiveStore, payload, digest, expected_outbound_id):
    try:
        decoded = decode_packet(payload, digest, expected_outbound_id)
    except PacketValidationError as error:
        reject_packet(error)
    return register_acceptance(store, decoded, payload)


receive_packet = accept_packet
