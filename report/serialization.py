from hashlib import sha256
import json


def serialize_report(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def deserialize_report(payload):
    data = json.loads(payload)
    if not isinstance(data, dict) or serialize_report(data) != payload:
        raise ValueError('invalid signed snapshot encoding')
    return data


def compute_report_digest(payload):
    return sha256(payload).hexdigest()
