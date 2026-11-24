import json
from dataclasses import asdict, dataclass
from uuid import uuid4

from values import canonical_json


@dataclass(frozen=True)
class StationReceipt:
    receipt_id: int
    issue_id: str
    fingerprint: str
    token: str


def make_first_receipt(receipt_id, station):
    return StationReceipt(receipt_id, station.envelope.issue_id, station.fingerprint, uuid4().hex)


def encode_receipt(receipt):
    return canonical_json(asdict(receipt))


def decode_receipt(payload):
    return StationReceipt(**json.loads(payload))
